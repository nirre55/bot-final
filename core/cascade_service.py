"""
Service de cascade trading
Responsabilité unique : Gestion du système de cascade avec alternance LONG/SHORT
"""
import asyncio
import time
from typing import Dict, Optional, Any, List
from enum import Enum
from decimal import Decimal, ROUND_DOWN

import config
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class CascadeState(Enum):
    """États possibles du système de cascade"""
    INACTIVE = "inactive"  # Pas de cascade active
    WAITING_HEDGE = "waiting_hedge"  # Attente exécution hedge initial
    ACTIVE = "active"  # Cascade active avec ordres en attente
    STOPPED = "stopped"  # Cascade arrêtée (limite atteinte ou erreur)


class CascadeService:
    """Service de gestion du système de cascade trading"""
    
    def __init__(self, binance_client: BinanceAPIClient, tp_service=None) -> None:
        """Initialise le service cascade"""
        self.logger = get_module_logger("CascadeService")
        self.binance_client = binance_client
        self.tp_service = tp_service
        self.trading_service = None  # Référence pour formatage dynamique
        
        # État du système cascade
        self.state: CascadeState = CascadeState.INACTIVE
        self.is_polling: bool = False
        
        # Prix de référence (définis lors du trade initial + hedge)
        self.initial_long_price: Optional[float] = None
        self.initial_short_price: Optional[float] = None
        
        # Quantités cumulatives des positions
        self.current_long_quantity: float = 0.0
        self.current_short_quantity: float = 0.0
        
        # Compteur d'ordres cascade créés
        self.cascade_orders_count: int = 0
        
        # Liste des ordres cascade en attente
        self.pending_orders: List[Dict[str, Any]] = []
        
        # Ordre hedge initial à surveiller
        self.initial_hedge_order: Optional[Dict[str, Any]] = None
        
        # Informations de l'ordre initial pour récupération du prix
        self.initial_order_info: Optional[Dict[str, Any]] = None
        
        # Cache des informations de formatage pour éviter appels répétés
        self._symbol_precision_cache: Optional[Dict[str, Any]] = None
        self._cached_symbol: Optional[str] = None
        
        self.logger.debug("CascadeService initialisé")
    
    def set_trading_service_reference(self, trading_service) -> None:
        """
        Définit la référence au TradingService après initialisation
        
        Args:
            trading_service: Instance du TradingService pour formatage dynamique
        """
        self.trading_service = trading_service
        self.logger.debug("Référence TradingService définie dans CascadeService")
        
        # Précharger le cache de précision pour le symbole actuel
        self._cache_symbol_precision()
    
    def is_cascade_active(self) -> bool:
        """
        Vérifie si une cascade est active
        
        Returns:
            True si cascade active, False sinon
        """
        return self.state in [CascadeState.WAITING_HEDGE, CascadeState.ACTIVE]
    
    def start_cascade(
        self, 
        initial_order: Dict[str, Any], 
        hedge_order: Dict[str, Any]
    ) -> None:
        """
        Démarre une nouvelle cascade avec le trade initial et son hedge
        
        Args:
            initial_order: Résultat de l'ordre initial (signal)
            hedge_order: Résultat de l'ordre hedge
        """
        self.logger.debug("start_cascade called")
        
        if not config.CASCADE_CONFIG["ENABLED"]:
            self.logger.info("Système cascade désactivé dans la configuration")
            return
        
        if self.is_cascade_active():
            self.logger.warning("Cascade déjà active - ignoré")
            return
        
        try:
            # Réinitialiser l'état
            self._reset_cascade_state()
            
            # Stocker les IDs d'ordres pour récupération ultérieure des prix
            initial_order_id = initial_order.get("orderId")
            initial_side = initial_order.get("side", "").upper()
            
            hedge_order_id = hedge_order.get("orderId")
            hedge_side = hedge_order.get("side", "").upper()
            
            self.logger.info(f"Cascade démarrée - Initial: {initial_side} ID:{initial_order_id}, Hedge: {hedge_side} ID:{hedge_order_id}")
            
            # Stocker les informations pour récupération des prix après exécution
            self.initial_order_info = {
                "id": initial_order_id,
                "side": initial_side,
                "symbol": config.SYMBOL
            }
            
            # Stocker l'ordre hedge à surveiller
            self.initial_hedge_order = hedge_order
            
            # Démarrer en mode attente hedge
            self.state = CascadeState.WAITING_HEDGE
            
            self.logger.info(f"🔄 Cascade démarrée - Prix ref: LONG={self.initial_long_price}, SHORT={self.initial_short_price}")
            self.logger.info(f"Positions: LONG={self.current_long_quantity}, SHORT={self.current_short_quantity}")
            
            # Démarrer le polling des ordres si pas déjà actif
            if not self.is_polling:
                asyncio.create_task(self._start_order_polling())
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage cascade: {e}", exc_info=True)
            self._reset_cascade_state()
    
    def _reset_cascade_state(self) -> None:
        """Remet à zéro l'état de la cascade"""
        self.logger.debug("_reset_cascade_state called")
        
        self.state = CascadeState.INACTIVE
        self.initial_long_price = None
        self.initial_short_price = None
        self.current_long_quantity = 0.0
        self.current_short_quantity = 0.0
        self.cascade_orders_count = 0
        self.pending_orders.clear()
        self.initial_hedge_order = None
        self.initial_order_info = None
        
        self.logger.info("État cascade réinitialisé")
    
    async def _start_order_polling(self) -> None:
        """Démarre le polling des ordres en arrière-plan"""
        self.logger.debug("_start_order_polling called")
        self.logger.info("Démarrage du polling des ordres cascade")
        
        self.is_polling = True
        polling_interval = config.CASCADE_CONFIG["POLLING_INTERVAL_SECONDS"]
        
        try:
            while self.is_cascade_active():
                await self._check_and_process_orders()
                await asyncio.sleep(polling_interval)
            
        except Exception as e:
            self.logger.error(f"Erreur dans le polling des ordres: {e}", exc_info=True)
        finally:
            self.is_polling = False
            self.logger.info("Polling des ordres cascade arrêté")
    
    async def _check_and_process_orders(self) -> None:
        """Vérifie les ordres en attente et traite les exécutions"""
        self.logger.debug("_check_and_process_orders called")
        
        try:
            if self.state == CascadeState.WAITING_HEDGE:
                await self._check_initial_hedge()
            elif self.state == CascadeState.ACTIVE:
                await self._check_cascade_orders()
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des ordres: {e}", exc_info=True)
    
    async def _retrieve_initial_order_price(self) -> None:
        """Récupère le prix d'exécution de l'ordre initial"""
        self.logger.debug("_retrieve_initial_order_price called")
        
        if not self.initial_order_info:
            return
        
        # Vérifier si le prix est déjà défini
        order_side = self.initial_order_info.get("side")
        if order_side == "BUY" and self.initial_long_price is not None:
            return  # Prix LONG déjà défini
        elif order_side == "SELL" and self.initial_short_price is not None:
            return  # Prix SHORT déjà défini
        
        try:
            order_id = self.initial_order_info.get("id")
            symbol = self.initial_order_info.get("symbol")
            
            if not order_id or not symbol:
                self.logger.error("Informations ordre initial manquantes")
                return
            
            # Récupérer le statut de l'ordre initial
            order_status = self.binance_client.get_order_status(symbol, int(order_id))
            
            if order_status and order_status.get("status") == "FILLED":
                executed_price = float(order_status.get("avgPrice", "0"))
                executed_qty = float(order_status.get("executedQty", "0"))
                
                self.logger.info(f"✅ Prix ordre initial récupéré: {order_side} {executed_qty} @ {executed_price}")
                
                # Définir le prix et la quantité selon le côté
                if order_side == "BUY":
                    self.initial_long_price = executed_price
                    self.current_long_quantity = executed_qty
                    self.logger.info(f"Prix LONG initial défini via API: {executed_price}")
                else:
                    self.initial_short_price = executed_price
                    self.current_short_quantity = executed_qty
                    self.logger.info(f"Prix SHORT initial défini via API: {executed_price}")
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du prix initial: {e}", exc_info=True)
    
    async def _check_initial_hedge(self) -> None:
        """Vérifie si l'ordre hedge initial s'est exécuté et récupère les prix"""
        self.logger.debug("_check_initial_hedge called")
        
        if not self.initial_hedge_order or not self.initial_order_info:
            return
        
        try:
            # D'abord récupérer le prix de l'ordre initial s'il n'est pas encore défini
            await self._retrieve_initial_order_price()
            
            # Puis vérifier le statut de l'ordre hedge
            order_id = self.initial_hedge_order.get("orderId")
            symbol = self.initial_hedge_order.get("symbol", config.SYMBOL)
            
            if not order_id:
                self.logger.error("ID d'ordre hedge manquant")
                return
            
            order_status = self.binance_client.get_order_status(symbol, int(order_id))
            
            if order_status and order_status.get("status") == "FILLED":
                # Hedge exécuté !
                executed_price = float(order_status.get("avgPrice", "0"))
                executed_qty = float(order_status.get("executedQty", "0"))
                side = order_status.get("side", "").upper()
                
                self.logger.info(f"✅ Hedge initial exécuté: {side} {executed_qty} @ {executed_price}")
                
                # Définir le prix de référence manquant et mettre à jour les quantités
                if side == "BUY":
                    # Hedge BUY exécuté → définir le prix LONG de référence 
                    if self.initial_long_price is None:
                        self.initial_long_price = executed_price
                        self.logger.info(f"Prix LONG hedge défini: {executed_price}")
                    self.current_long_quantity += executed_qty
                else:
                    # Hedge SELL exécuté → définir le prix SHORT de référence
                    if self.initial_short_price is None:
                        self.initial_short_price = executed_price
                        self.logger.info(f"Prix SHORT hedge défini: {executed_price}")
                    self.current_short_quantity += executed_qty
                
                # Créer le TP pour la position hedge si service TP disponible
                if self.tp_service and config.TP_CONFIG["ENABLED"]:
                    self._create_tp_for_hedge_execution(side, executed_qty)
                
                # Passer en mode cascade active
                self.state = CascadeState.ACTIVE
                self.initial_hedge_order = None
                
                # Créer le premier ordre cascade
                await self._create_next_cascade_order()
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification du hedge initial: {e}", exc_info=True)
    
    async def _check_cascade_orders(self) -> None:
        """Vérifie les ordres cascade en attente"""
        self.logger.debug("_check_cascade_orders called")
        
        if not self.pending_orders:
            return
        
        orders_to_remove = []
        
        for pending_order in self.pending_orders[:]:  # Copie pour itération sûre
            try:
                order_id = pending_order.get("orderId")
                symbol = pending_order.get("symbol", config.SYMBOL)
                
                if not order_id:
                    self.logger.error("ID d'ordre cascade manquant")
                    orders_to_remove.append(pending_order)
                    continue
                
                order_status = self.binance_client.get_order_status(symbol, int(order_id))
                
                if order_status and order_status.get("status") == "FILLED":
                    # Ordre exécuté !
                    await self._process_cascade_order_execution(pending_order, order_status)
                    orders_to_remove.append(pending_order)
                    
                elif order_status and order_status.get("status") in ["CANCELED", "REJECTED"]:
                    # Ordre annulé ou rejeté
                    self.logger.warning(f"Ordre cascade {order_id} annulé/rejeté: {order_status.get('status')}")
                    orders_to_remove.append(pending_order)
                    
            except Exception as e:
                order_id_str = str(order_id) if order_id else "inconnu"
                self.logger.error(f"Erreur lors de la vérification de l'ordre {order_id_str}: {e}", exc_info=True)
        
        # Supprimer les ordres traités
        for order in orders_to_remove:
            self.pending_orders.remove(order)
    
    async def _process_cascade_order_execution(
        self, 
        pending_order: Dict[str, Any], 
        executed_order: Dict[str, Any]
    ) -> None:
        """
        Traite l'exécution d'un ordre cascade
        
        Args:
            pending_order: Ordre en attente qui s'est exécuté
            executed_order: Détails de l'exécution
        """
        self.logger.debug("_process_cascade_order_execution called")
        
        try:
            side = executed_order.get("side", "").upper()
            executed_qty = float(executed_order.get("executedQty", "0"))
            executed_price = float(executed_order.get("avgPrice", "0"))
            
            # Mettre à jour les quantités
            if side == "BUY":
                self.current_long_quantity += executed_qty
            else:
                self.current_short_quantity += executed_qty
            
            self.logger.info(f"🔄 Ordre cascade exécuté: {side} {executed_qty} @ {executed_price}")
            self.logger.info(f"Positions totales: LONG={self.current_long_quantity}, SHORT={self.current_short_quantity}")
            
            # Mettre à jour les TP si le service TP est disponible
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._update_tp_after_cascade(side)
            
            # Créer le prochain ordre cascade si limite pas atteinte
            if self.cascade_orders_count < config.CASCADE_CONFIG["MAX_ORDERS"]:
                await self._create_next_cascade_order()
            else:
                self.logger.info(f"🛑 Limite cascade atteinte ({config.CASCADE_CONFIG['MAX_ORDERS']} ordres)")
                self.state = CascadeState.STOPPED
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'exécution cascade: {e}", exc_info=True)
    
    def _update_tp_after_cascade(self, executed_side: str) -> None:
        """
        Met à jour les ordres TP après l'exécution d'un ordre cascade
        
        Args:
            executed_side: Côté de l'ordre cascade exécuté (BUY ou SELL)
        """
        self.logger.debug(f"_update_tp_after_cascade called: {executed_side}")
        
        if not self.tp_service:
            self.logger.debug("Service TP non disponible")
            return
        
        try:
            from core.tp_service import TPSide
            
            # Déterminer quel côté TP mettre à jour
            if executed_side == "BUY":
                # Ordre BUY exécuté → position LONG augmentée → mettre à jour TP LONG
                tp_side = TPSide.LONG
                current_quantity = self.current_long_quantity
                self.logger.info(f"Mise à jour TP LONG avec quantité: {current_quantity}")
            else:
                # Ordre SELL exécuté → position SHORT augmentée → mettre à jour TP SHORT
                tp_side = TPSide.SHORT
                current_quantity = self.current_short_quantity
                self.logger.info(f"Mise à jour TP SHORT avec quantité: {current_quantity}")
            
            # Mettre à jour le TP avec la nouvelle quantité (pas initial = incrément)
            success = self.tp_service.create_or_update_tp(
                side=tp_side,
                quantity=current_quantity,
                is_initial=False  # Pas initial → incrément du prix TP
            )
            
            if success:
                self.logger.info(f"✅ TP {tp_side.value} mis à jour après cascade")
            else:
                self.logger.warning(f"⚠️ Échec mise à jour TP {tp_side.value}")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour TP après cascade: {e}", exc_info=True)
    
    def _create_tp_for_hedge_execution(self, side: str, quantity: float) -> None:
        """
        Crée un TP pour la position hedge qui vient de s'exécuter
        
        Args:
            side: Côté de l'ordre hedge exécuté (BUY ou SELL)
            quantity: Quantité de l'ordre hedge exécuté
        """
        self.logger.debug(f"_create_tp_for_hedge_execution called: {side} {quantity}")
        
        if not self.tp_service:
            self.logger.debug("Service TP non disponible")
            return
        
        try:
            from core.tp_service import TPSide
            
            # Déterminer le côté TP à mettre à jour
            if side == "BUY":
                # Hedge BUY exécuté → position LONG augmentée → mettre à jour TP LONG
                tp_side = TPSide.LONG
                self.logger.info(f"Mise à jour TP LONG après hedge BUY exécuté: {quantity}")
            else:
                # Hedge SELL exécuté → position SHORT augmentée → mettre à jour TP SHORT
                tp_side = TPSide.SHORT
                self.logger.info(f"Mise à jour TP SHORT après hedge SELL exécuté: {quantity}")
            
            # Déterminer si c'est le premier hedge ou une cascade
            is_first_hedge = self.state == CascadeState.WAITING_HEDGE
            
            # Mettre à jour le TP avec la quantité totale actuelle du côté
            total_quantity = self.current_long_quantity if side == "BUY" else self.current_short_quantity
            
            success = self.tp_service.create_or_update_tp(
                side=tp_side,
                quantity=total_quantity,
                is_initial=is_first_hedge  # True pour premier hedge, False pour cascades
            )
            
            if success:
                action_type = "créé (niveau de base)" if is_first_hedge else "mis à jour (avec incrément)"
                self.logger.info(f"✅ TP {tp_side.value} {action_type} après exécution hedge (total: {total_quantity})")
            else:
                action_type = "création" if is_first_hedge else "mise à jour"
                self.logger.warning(f"⚠️ Échec {action_type} TP {tp_side.value} après hedge")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la création TP pour hedge: {e}", exc_info=True)
    
    async def _create_next_cascade_order(self) -> None:
        """Crée le prochain ordre cascade selon la logique d'alternance"""
        self.logger.debug("_create_next_cascade_order called")
        
        try:
            # Déterminer quel type d'ordre créer (alternance)
            if self.current_long_quantity > self.current_short_quantity:
                # Plus de LONG → Créer SHORT
                next_side = "SELL"
                next_position_side = "SHORT"
                stop_price = self.initial_short_price
                # Quantité = 2 * current_long_quantity - current_short_quantity
                next_quantity = (2 * self.current_long_quantity) - self.current_short_quantity
            else:
                # Plus de SHORT → Créer LONG
                next_side = "BUY"
                next_position_side = "LONG"
                stop_price = self.initial_long_price
                # Quantité = 2 * current_short_quantity - current_long_quantity
                next_quantity = (2 * self.current_short_quantity) - self.current_long_quantity
            
            
            if next_quantity <= 0:
                self.logger.error(f"Quantité cascade invalide: {next_quantity}")
                return
            
            # Vérifier que stop_price est valide
            if stop_price is None or stop_price <= 0:
                self.logger.error(f"Prix de stop invalide: {stop_price}")
                self.logger.error("Les prix de référence ne sont pas correctement initialisés")
                return
            
            # Formater la quantité selon les règles du symbole
            formatted_quantity = self._format_cascade_quantity(next_quantity)
            
            if not formatted_quantity:
                self.logger.error("Impossible de formater la quantité cascade")
                return
            
            # Formater le prix selon les règles du symbole
            formatted_stop_price = self._format_cascade_price(stop_price)
            
            # Créer l'ordre STOP_MARKET
            self.logger.info(f"📋 Création ordre cascade: {next_side} {formatted_quantity} @ {formatted_stop_price}")
            
            cascade_order = self.binance_client.place_stop_market_order(
                symbol=config.SYMBOL,
                side=next_side,
                quantity=formatted_quantity,
                stop_price=formatted_stop_price,  # Utiliser prix formaté
                position_side=next_position_side
            )
            
            if cascade_order:
                # Ajouter à la liste des ordres en attente
                self.pending_orders.append(cascade_order)
                self.cascade_orders_count += 1
                
                self.logger.info(f"✅ Ordre cascade créé - ID: {cascade_order.get('orderId')}")
            else:
                self.logger.error("❌ Échec de création de l'ordre cascade")
                self._handle_cascade_order_failure(next_side, formatted_quantity, stop_price)
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'ordre cascade: {e}", exc_info=True)
    
    def _handle_cascade_order_failure(self, side: str, quantity: str, stop_price: float) -> None:
        """
        Gère les échecs de création d'ordres cascade
        
        Args:
            side: Côté de l'ordre (BUY/SELL)
            quantity: Quantité formatée
            stop_price: Prix de stop utilisé
        """
        self.logger.debug(f"_handle_cascade_order_failure called: {side} {quantity} @ {stop_price}")
        
        # Pour l'instant, arrêter la cascade en cas d'échec
        # Dans le futur, on pourrait implémenter des retry selon le type d'erreur
        self.logger.warning(f"Arrêt de la cascade suite à l'échec de création d'ordre {side}")
        self.state = CascadeState.STOPPED
        
        # Ajouter des métriques pour debugging
        self.logger.info(f"État au moment de l'échec:")
        self.logger.info(f"  Ordres créés: {self.cascade_orders_count}/{config.CASCADE_CONFIG['MAX_ORDERS']}")
        self.logger.info(f"  Positions: LONG={self.current_long_quantity} SHORT={self.current_short_quantity}")
        self.logger.info(f"  Prix références: LONG={self.initial_long_price} SHORT={self.initial_short_price}")
    
    def _cache_symbol_precision(self) -> None:
        """
        Met en cache les informations de précision pour éviter appels répétés
        """
        if not self.trading_service:
            return
            
        symbol = config.SYMBOL
        
        # Vérifier si déjà en cache pour ce symbole
        if self._cached_symbol == symbol and self._symbol_precision_cache:
            return
        
        self.logger.debug(f"Mise en cache des informations de précision pour {symbol}")
        
        # Récupérer et mettre en cache
        precision_info = self.trading_service.get_symbol_precision(symbol)
        if precision_info:
            self._symbol_precision_cache = precision_info
            self._cached_symbol = symbol
            
            tick_size = precision_info["price_filter"]["tick_size"]
            step_size = precision_info["lot_size"]["step_size"]
            
            self.logger.info(f"Cache formatage Cascade: tick_size={tick_size}, step_size={step_size}")
        else:
            self.logger.warning("Impossible de mettre en cache les informations de précision")
    
    def _format_cascade_quantity(self, quantity: float) -> Optional[str]:
        """
        Formate la quantité cascade avec cache optimisé
        
        Args:
            quantity: Quantité à formater
            
        Returns:
            Quantité formatée ou None
        """
        self.logger.debug(f"_format_cascade_quantity called: {quantity}")
        
        try:
            # Utiliser le cache optimisé
            if self._symbol_precision_cache and self.trading_service:
                step_size = self._symbol_precision_cache["lot_size"]["step_size"]
                formatted = self.trading_service._format_quantity(quantity, step_size)
                
                if float(formatted) <= 0:
                    return None
                return formatted
            
            # Fallback : formatage fixe
            formatted = f"{quantity:.3f}".rstrip('0').rstrip('.')
            
            if float(formatted) <= 0:
                return None
                
            return formatted
            
        except Exception as e:
            self.logger.error(f"Erreur formatage quantité cascade: {e}", exc_info=True)
            return None
    
    def _format_cascade_price(self, price: float) -> str:
        """
        Formate un prix avec cache optimisé
        
        Args:
            price: Prix à formater
            
        Returns:
            Prix formaté
        """
        self.logger.debug(f"_format_cascade_price called: {price}")
        
        try:
            # Utiliser le cache optimisé
            if self._symbol_precision_cache and self.trading_service:
                tick_size = self._symbol_precision_cache["price_filter"]["tick_size"]
                return self.trading_service._format_price(price, tick_size)
            
            # Fallback : formatage fixe avec 2 décimales
            return f"{price:.2f}"
            
        except Exception as e:
            self.logger.error(f"Erreur formatage prix cascade: {e}", exc_info=True)
            return f"{price:.2f}"
    
    def get_cascade_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel du système cascade
        
        Returns:
            Dictionnaire avec l'état de la cascade
        """
        return {
            "state": self.state.value,
            "is_active": self.is_cascade_active(),
            "orders_count": self.cascade_orders_count,
            "max_orders": config.CASCADE_CONFIG["MAX_ORDERS"],
            "current_long_quantity": self.current_long_quantity,
            "current_short_quantity": self.current_short_quantity,
            "initial_long_price": self.initial_long_price,
            "initial_short_price": self.initial_short_price,
            "pending_orders_count": len(self.pending_orders)
        }
    
    def stop_cascade(self, reason: str = "Manual stop") -> None:
        """
        Arrête la cascade manuellement
        
        Args:
            reason: Raison de l'arrêt
        """
        self.logger.info(f"Arrêt cascade demandé: {reason}")
        
        if self.is_cascade_active():
            self.state = CascadeState.STOPPED
            
            # Annuler les ordres en attente si nécessaire
            # TODO: Implémenter annulation des ordres
            
        self.logger.info("Cascade arrêtée")
    
    def format_cascade_display(self) -> str:
        """
        Formate l'affichage de l'état cascade
        
        Returns:
            Chaîne formatée pour l'affichage
        """
        if not self.is_cascade_active():
            return ""
        
        status = self.get_cascade_status()
        
        if self.state == CascadeState.WAITING_HEDGE:
            return "CASCADE: 🔄 Attente exécution hedge initial"
        elif self.state == CascadeState.ACTIVE:
            pending_info = f"En attente: {len(self.pending_orders)}" if self.pending_orders else ""
            return (f"CASCADE: 🔄 Actif ({status['orders_count']}/{status['max_orders']}) "
                   f"| LONG:{status['current_long_quantity']:.3f} "
                   f"SHORT:{status['current_short_quantity']:.3f} "
                   f"| {pending_info}")
        elif self.state == CascadeState.STOPPED:
            reason = "Limite atteinte" if status['orders_count'] >= status['max_orders'] else "Arrêté"
            return f"CASCADE: 🛑 {reason} ({status['orders_count']}/{status['max_orders']})"
        
        return "CASCADE: ❓ État inconnu"