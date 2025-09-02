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
    
    def handle_order_execution_from_websocket(self, execution_data: Dict[str, Any]) -> None:
        """
        Gère les exécutions d'ordres reçues via WebSocket User Data Stream
        
        Args:
            execution_data: Données d'exécution du WebSocket
        """
        self.logger.debug("handle_order_execution_from_websocket called")
        
        try:
            order_id = str(execution_data.get("i"))  # Order ID
            symbol = execution_data.get("s")         # Symbol
            side = execution_data.get("S")           # Side (BUY/SELL)
            executed_qty = float(execution_data.get("z", "0"))  # Executed quantity (cumulative)
            execution_price = float(execution_data.get("L", "0"))  # Last executed price
            order_status = execution_data.get("X", "UNKNOWN")  # Order status
            position_side = execution_data.get("ps", "BOTH")  # Position side
            
            self.logger.info(f"📨 WebSocket: Ordre {order_status} {symbol} {side} {executed_qty} @ {execution_price} ID:{order_id}")
            self.logger.info(f"🎯 État cascade actuel: {self.state}, Hedge order: {self.initial_hedge_order}")
            
            # Vérifier si c'est notre symbole
            if symbol != config.SYMBOL:
                self.logger.debug(f"Ordre non concerné (symbole différent): {symbol}")
                return
                
            # Ne traiter que les ordres FILLED
            if order_status != "FILLED":
                self.logger.debug(f"Ordre non FILLED ignoré: {order_status} ID:{order_id}")
                return
            
            # Vérifier que les données critiques ne sont pas None
            if not side or executed_qty is None or execution_price is None:
                self.logger.error(f"Données d'exécution incomplètes: side={side}, qty={executed_qty}, price={execution_price}")
                return
            
            # Traiter selon le type d'ordre
            if self._is_hedge_order(order_id):
                self.logger.info("🎯 Ordre hedge initial détecté - Traitement en cours...")
                self.logger.info(f"State cascade: {self.state}")
                self.logger.info(f"Hedge order défini: {self.initial_hedge_order}")
                
                # Traitement immédiat du hedge en mode async
                asyncio.create_task(self._process_hedge_execution_async(side, executed_qty, execution_price))
                
            elif self._is_cascade_order(order_id):
                self.logger.info("🔄 Ordre cascade détecté")
                
                # Traitement immédiat du cascade en mode async
                asyncio.create_task(self._process_cascade_execution_async(side, executed_qty, execution_price, order_id))
                
            else:
                self.logger.info(f"❓ Ordre non suivi par le système cascade: {order_id}")
                self.logger.info(f"📊 État cascade: {self.state}")
                self.logger.info(f"📋 Hedge order: {self.initial_hedge_order}")
                self.logger.info(f"📋 Pending orders count: {len(self.pending_orders)}")
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement exécution WebSocket: {e}", exc_info=True)
    
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
            
            self.logger.info("✅ Cascade initialisée - En attente d'exécution via WebSocket")
            self.logger.info(f"🔄 Prix de référence: LONG={self.initial_long_price}, SHORT={self.initial_short_price}")
            self.logger.info(f"Positions: LONG={self.current_long_quantity}, SHORT={self.current_short_quantity}")
            
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
    
    async def _retrieve_initial_order_price_async(self) -> None:
        """Récupère le prix d'exécution de l'ordre initial (version async)"""
        if not self.initial_order_info:
            return

        # Vérifier si les prix sont déjà définis
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
    
    def _update_tp_after_cascade(self, executed_side: str) -> None:
        """
        Met à jour TOUS les TP actifs avec +0.1% après l'exécution d'un ordre cascade
        
        Args:
            executed_side: Côté de l'ordre cascade exécuté (BUY ou SELL)
        """
        self.logger.debug(f"_update_tp_after_cascade called: {executed_side}")
        
        if not self.tp_service:
            self.logger.debug("Service TP non disponible")
            return
        
        try:
            from core.tp_service import TPSide
            
            self.logger.info(f"🔄 Cascade {executed_side} exécutée - Mise à jour TOUS les TP avec +0.1%")
            
            # Mettre à jour TP LONG s'il existe et qu'on a une position LONG
            if self.current_long_quantity > 0:
                success_long = self.tp_service.create_or_update_tp(
                    side=TPSide.LONG,
                    quantity=self.current_long_quantity,
                    is_initial=False  # False = avec incrément +0.1%
                )
                
                if success_long:
                    self.logger.info(f"✅ TP LONG mis à jour avec +0.1% après cascade (quantité: {self.current_long_quantity})")
                else:
                    self.logger.warning(f"⚠️ Échec mise à jour TP LONG après cascade")
            
            # Mettre à jour TP SHORT s'il existe et qu'on a une position SHORT
            if self.current_short_quantity > 0:
                success_short = self.tp_service.create_or_update_tp(
                    side=TPSide.SHORT,
                    quantity=self.current_short_quantity,
                    is_initial=False  # False = avec décrémentation -0.1%
                )
                
                if success_short:
                    self.logger.info(f"✅ TP SHORT mis à jour avec -0.1% après cascade (quantité: {self.current_short_quantity})")
                else:
                    self.logger.warning(f"⚠️ Échec mise à jour TP SHORT après cascade")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour TP après cascade: {e}", exc_info=True)
    
    def _create_tp_for_hedge_execution(self, side: str, quantity: float) -> None:
        """
        Met à jour les TP quand le hedge s'exécute : TP existant +0.1% et nouveau TP hedge
        
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
            
            self.logger.info(f"🔄 Hedge {side} exécuté - Mise à jour TP avec increment +0.1%")
            
            if side == "BUY":
                # Hedge BUY exécuté → position LONG augmentée
                existing_tp_side = TPSide.SHORT  # TP existant (si on avait SHORT initial)
                new_tp_side = TPSide.LONG        # Nouveau TP pour position LONG du hedge
                existing_quantity = self.current_short_quantity
                new_quantity = self.current_long_quantity
                
            else:
                # Hedge SELL exécuté → position SHORT augmentée  
                existing_tp_side = TPSide.LONG   # TP existant (si on avait LONG initial)
                new_tp_side = TPSide.SHORT       # Nouveau TP pour position SHORT du hedge
                existing_quantity = self.current_long_quantity
                new_quantity = self.current_short_quantity
            
            # 1. Mettre à jour le TP existant avec +0.1% (incrément)
            if existing_quantity > 0:
                success_existing = self.tp_service.create_or_update_tp(
                    side=existing_tp_side,
                    quantity=existing_quantity,
                    is_initial=False  # False = avec incrément +0.1%
                )
                
                if success_existing:
                    self.logger.info(f"✅ TP {existing_tp_side.value} existant mis à jour avec +0.1% (quantité: {existing_quantity})")
                else:
                    self.logger.warning(f"⚠️ Échec mise à jour TP {existing_tp_side.value} existant")
            
            # 2. Créer TP pour le nouveau côté hedge avec -0.1% 
            if new_quantity > 0:
                success_new = self.tp_service.create_or_update_tp(
                    side=new_tp_side,
                    quantity=new_quantity,
                    is_initial=False  # False = avec décrémentation -0.1% pour le côté opposé
                )
                
                if success_new:
                    self.logger.info(f"✅ TP {new_tp_side.value} créé pour hedge avec -0.1% (quantité: {new_quantity})")
                else:
                    self.logger.warning(f"⚠️ Échec création TP {new_tp_side.value} pour hedge")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour TP pour hedge: {e}", exc_info=True)
    
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
        Gère les échecs de création d'ordres cascade - Arrête juste les cascades sans reset complet
        
        Args:
            side: Côté de l'ordre (BUY/SELL)
            quantity: Quantité formatée
            stop_price: Prix de stop utilisé
        """
        self.logger.debug(f"_handle_cascade_order_failure called: {side} {quantity} @ {stop_price}")
        self.logger.warning(f"⚠️ Échec création ordre cascade {side} - Arrêt des cascades uniquement")
        
        # Ajouter des métriques pour debugging
        self.logger.info(f"État au moment de l'échec:")
        self.logger.info(f"  Ordres créés: {self.cascade_orders_count}/{config.CASCADE_CONFIG['MAX_ORDERS']}")
        self.logger.info(f"  Positions: LONG={self.current_long_quantity} SHORT={self.current_short_quantity}")
        self.logger.info(f"  Prix références: LONG={self.initial_long_price} SHORT={self.initial_short_price}")
        
        # Simplement arrêter la cascade - LES POSITIONS ET TP RESTENT ACTIFS
        self.state = CascadeState.STOPPED
        
        self.logger.info("🔄 Cascade arrêtée - Positions et TP restent actifs pour atteindre les TP")
    
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
    
    def _is_hedge_order(self, order_id: str) -> bool:
        """
        Vérifie si un ordre ID correspond au hedge initial
        
        Args:
            order_id: ID de l'ordre à vérifier
            
        Returns:
            True si c'est le hedge, False sinon
        """
        if not self.initial_hedge_order:
            self.logger.debug(f"❌ _is_hedge_order: pas de hedge initial défini (order_id={order_id})")
            return False
        
        hedge_id = str(self.initial_hedge_order.get("orderId", ""))
        is_hedge = hedge_id == order_id
        
        self.logger.info(f"🔍 _is_hedge_order: hedge_id={hedge_id}, order_id={order_id}, is_hedge={is_hedge}, state={self.state}")
        
        return is_hedge
    
    def _is_cascade_order(self, order_id: str) -> bool:
        """
        Vérifie si un ordre ID correspond à un ordre cascade
        
        Args:
            order_id: ID de l'ordre à vérifier
            
        Returns:
            True si c'est un ordre cascade, False sinon
        """
        for order in self.pending_orders:
            if str(order.get("orderId", "")) == order_id:
                return True
        return False
    
    def _process_hedge_execution_sync(self, side: str, quantity: float, price: float) -> None:
        """
        Traite l'exécution du hedge initial via WebSocket (version synchrone)
        
        Args:
            side: Côté de l'ordre (BUY/SELL)
            quantity: Quantité exécutée
            price: Prix d'exécution
        """
        try:
            self.logger.info(f"🎯 Traitement exécution hedge WebSocket: {side} {quantity} @ {price}")
            
            # Mettre à jour les prix et quantités
            if side == "BUY":
                self.initial_long_price = price
                self.current_long_quantity += quantity
            else:
                self.initial_short_price = price
                self.current_short_quantity += quantity
            
            # Créer/mettre à jour les TP pour hedge
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._create_tp_for_hedge_execution(side, quantity)
            
            # Passer en mode cascade active
            self.state = CascadeState.ACTIVE
            self.initial_hedge_order = None
            
            # Créer le premier ordre cascade (sera créé lors de la prochaine opportunité async)
            self.logger.info("🔄 Cascade prête - Premier ordre cascade sera créé")
            
            self.logger.info(f"✅ Hedge traité via WebSocket - Cascade active")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement hedge WebSocket: {e}", exc_info=True)
    
    async def _process_hedge_execution_async(self, side: str, quantity: float, price: float) -> None:
        """
        Traite l'exécution du hedge initial via WebSocket (version async)
        
        Args:
            side: Côté de l'ordre (BUY/SELL)
            quantity: Quantité exécutée
            price: Prix d'exécution
        """
        try:
            self.logger.info(f"🎯 Traitement exécution hedge WebSocket ASYNC: {side} {quantity} @ {price}")
            
            # Récupérer d'abord le prix de l'ordre initial si pas encore défini
            await self._retrieve_initial_order_price_async()
            
            # Mettre à jour les prix et quantités du hedge
            if side == "BUY":
                # Hedge BUY exécuté → définir le prix LONG de référence 
                if self.initial_long_price is None:
                    self.initial_long_price = price
                    self.logger.info(f"Prix LONG hedge défini: {price}")
                self.current_long_quantity += quantity
            else:
                # Hedge SELL exécuté → définir le prix SHORT de référence
                if self.initial_short_price is None:
                    self.initial_short_price = price
                    self.logger.info(f"Prix SHORT hedge défini: {price}")
                self.current_short_quantity += quantity
            
            # Créer/mettre à jour les TP pour hedge
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._create_tp_for_hedge_execution(side, quantity)
                # Mettre à jour TOUS les TP avec +0.1% après exécution hedge
                self._update_tp_after_cascade(side)
            
            # Passer en mode cascade active
            self.state = CascadeState.ACTIVE
            self.initial_hedge_order = None
            
            # Vérifier que les prix sont bien initialisés avant de créer l'ordre cascade
            self.logger.info(f"📊 Prix avant création cascade: LONG={self.initial_long_price}, SHORT={self.initial_short_price}")
            
            if self.initial_long_price is None or self.initial_short_price is None:
                self.logger.error("❌ Prix de référence manquants - impossible de créer l'ordre cascade")
                self.logger.error(f"   LONG: {self.initial_long_price}, SHORT: {self.initial_short_price}")
                return
            
            # Créer le premier ordre cascade immédiatement (version async)
            self.logger.info("🔄 Création du premier ordre cascade...")
            await self._create_next_cascade_order()
            
            self.logger.info(f"✅ Hedge traité via WebSocket ASYNC - Cascade active avec premier ordre créé")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement hedge WebSocket ASYNC: {e}", exc_info=True)
            
    def _process_cascade_execution_sync(self, side: str, quantity: float, price: float, order_id: str) -> None:
        """
        Traite l'exécution d'un ordre cascade via WebSocket (version synchrone)
        
        Args:
            side: Côté de l'ordre (BUY/SELL) 
            quantity: Quantité exécutée
            price: Prix d'exécution
            order_id: ID de l'ordre exécuté
        """
        try:
            self.logger.info(f"🔄 Traitement exécution cascade WebSocket: {side} {quantity} @ {price}")
            
            # Retirer l'ordre de la liste pending
            self.pending_orders = [order for order in self.pending_orders if str(order.get("orderId", "")) != order_id]
            
            # Mettre à jour les quantités
            if side == "BUY":
                self.current_long_quantity += quantity
            else:
                self.current_short_quantity += quantity
            
            self.cascade_orders_count += 1
            
            # Mettre à jour les TP
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._update_tp_after_cascade(side)
            
            # Créer l'ordre cascade suivant si sous la limite
            if self.cascade_orders_count < config.CASCADE_CONFIG["MAX_ORDERS"]:
                self.logger.info("🔄 Prochain ordre cascade sera créé lors de la prochaine bougie")
            else:
                self.logger.info("Limite d'ordres cascade atteinte")
                self.state = CascadeState.STOPPED
            
            self.logger.info(f"✅ Cascade {side} traitée via WebSocket - Total ordres: {self.cascade_orders_count}")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement cascade WebSocket: {e}", exc_info=True)
            
    async def _process_cascade_execution_async(self, side: str, quantity: float, price: float, order_id: str) -> None:
        """
        Traite l'exécution d'un ordre cascade via WebSocket (version async)
        
        Args:
            side: Côté de l'ordre (BUY/SELL) 
            quantity: Quantité exécutée
            price: Prix d'exécution
            order_id: ID de l'ordre exécuté
        """
        try:
            self.logger.info(f"🔄 Traitement exécution cascade WebSocket ASYNC: {side} {quantity} @ {price}")
            
            # Retirer l'ordre de la liste pending
            self.pending_orders = [order for order in self.pending_orders if str(order.get("orderId", "")) != order_id]
            
            # Mettre à jour les quantités
            if side == "BUY":
                self.current_long_quantity += quantity
            else:
                self.current_short_quantity += quantity
            
            self.cascade_orders_count += 1
            
            # Mettre à jour les TP
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._update_tp_after_cascade(side)
            
            # Créer l'ordre cascade suivant si sous la limite
            if self.cascade_orders_count < config.CASCADE_CONFIG["MAX_ORDERS"]:
                self.logger.info("🔄 Création ordre cascade suivant...")
                await self._create_next_cascade_order()
            else:
                self.logger.info("Limite d'ordres cascade atteinte")
                self.state = CascadeState.STOPPED
            
            self.logger.info(f"✅ Cascade {side} traitée via WebSocket ASYNC - Total ordres: {self.cascade_orders_count}")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement cascade WebSocket ASYNC: {e}", exc_info=True)

    async def _process_hedge_execution_websocket(self, side: str, quantity: float, price: float) -> None:
        """
        Traite l'exécution du hedge initial via WebSocket
        
        Args:
            side: Côté de l'ordre (BUY/SELL)
            quantity: Quantité exécutée
            price: Prix d'exécution
        """
        try:
            self.logger.info(f"🎯 Traitement exécution hedge WebSocket: {side} {quantity} @ {price}")
            
            # Mettre à jour les prix et quantités
            if side == "BUY":
                self.initial_long_price = price
                self.current_long_quantity += quantity
            else:
                self.initial_short_price = price
                self.current_short_quantity += quantity
            
            # Créer/mettre à jour les TP pour hedge
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._create_tp_for_hedge_execution(side, quantity)
            
            # Passer en mode cascade active
            self.state = CascadeState.ACTIVE
            self.initial_hedge_order = None
            
            # Créer le premier ordre cascade
            await self._create_next_cascade_order()
            
            self.logger.info(f"✅ Hedge traité via WebSocket - Cascade active")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement hedge WebSocket: {e}", exc_info=True)
    
    async def _process_cascade_execution_websocket(self, side: str, quantity: float, price: float, order_id: str) -> None:
        """
        Traite l'exécution d'un ordre cascade via WebSocket
        
        Args:
            side: Côté de l'ordre (BUY/SELL) 
            quantity: Quantité exécutée
            price: Prix d'exécution
            order_id: ID de l'ordre exécuté
        """
        try:
            self.logger.info(f"🔄 Traitement exécution cascade WebSocket: {side} {quantity} @ {price}")
            
            # Retirer l'ordre de la liste pending
            self.pending_orders = [order for order in self.pending_orders if str(order.get("orderId", "")) != order_id]
            
            # Mettre à jour les quantités
            if side == "BUY":
                self.current_long_quantity += quantity
            else:
                self.current_short_quantity += quantity
            
            self.orders_executed_count += 1
            
            # Mettre à jour les TP
            if self.tp_service and config.TP_CONFIG["ENABLED"]:
                self._update_tp_after_cascade(side)
            
            # Créer l'ordre cascade suivant si sous la limite
            if self.orders_executed_count < config.CASCADE_CONFIG["MAX_ORDERS"]:
                await self._create_next_cascade_order()
            else:
                self.logger.info("Limite d'ordres cascade atteinte")
                self.state = CascadeState.STOPPED
            
            self.logger.info(f"✅ Cascade {side} traitée via WebSocket - Total ordres: {self.orders_executed_count}")
            
        except Exception as e:
            self.logger.error(f"Erreur traitement cascade WebSocket: {e}", exc_info=True)
    
    def handle_tp_execution(self, executed_side: str) -> None:
        """
        Gère l'exécution d'un TP avec reset complet du système pour nouveau cycle
        
        Args:
            executed_side: Côté du TP exécuté ("LONG" ou "SHORT")
        """
        self.logger.debug(f"handle_tp_execution called: {executed_side}")
        self.logger.info(f"🎯 TP {executed_side} exécuté - Démarrage du reset complet du système")
        
        try:
            # 1. Fermer TOUTES les positions ouvertes (pas seulement le côté du TP exécuté)
            self._close_all_positions()
            
            # 2. Annuler TOUS les ordres en attente (LONG et SHORT)
            self._cancel_all_pending_orders()
            
            # 3. Annuler l'ordre hedge initial s'il existe encore
            if self.initial_hedge_order:
                hedge_order_id = self.initial_hedge_order.get("orderId")
                if hedge_order_id:
                    cancel_result = self.binance_client.cancel_order(config.SYMBOL, int(hedge_order_id))
                    if cancel_result:
                        self.logger.info(f"Ordre hedge initial {hedge_order_id} annulé")
                    self.initial_hedge_order = None
            
            # 4. Reset complet des variables du système cascade
            self.current_long_quantity = 0.0
            self.current_short_quantity = 0.0
            self.initial_long_price = None
            self.initial_short_price = None
            self.pending_orders.clear()
            self.cascade_orders_count = 0
            
            # 5. Passer en état STOPPED pour permettre nouveau signal
            self.state = CascadeState.STOPPED
            
            self.logger.info("✅ Reset complet terminé - Système prêt pour nouveau signal")
            
        except Exception as e:
            self.logger.error(f"Erreur lors du reset complet système: {e}", exc_info=True)
    
    def _close_all_positions(self) -> None:
        """
        Ferme toutes les positions ouvertes (LONG et SHORT) après vérification des positions réelles
        """
        self.logger.info("Vérification et fermeture des positions réelles ouvertes")
        
        try:
            # Récupérer les positions réelles depuis Binance
            positions = self.binance_client.get_position_info(config.SYMBOL)
            if not positions:
                self.logger.warning("Impossible de récupérer les positions - abandon fermeture")
                return
            
            # Parcourir les positions et fermer celles qui ont une quantité > 0
            for position in positions:
                position_side = position.get("positionSide", "")
                position_amt = float(position.get("positionAmt", "0"))
                
                # Ignorer les positions avec quantité nulle
                if abs(position_amt) == 0:
                    continue
                
                self.logger.info(f"Position {position_side} détectée: {position_amt}")
                
                # Déterminer l'ordre de fermeture
                if position_side == "LONG" and position_amt > 0:
                    side = "SELL"
                    quantity = position_amt
                elif position_side == "SHORT" and position_amt < 0:
                    side = "BUY"
                    quantity = abs(position_amt)  # Convertir en positif
                else:
                    continue
                
                # Formatter et placer l'ordre de fermeture
                formatted_quantity = self._format_cascade_quantity(quantity)
                if formatted_quantity:
                    order = self.binance_client.place_order(
                        symbol=config.SYMBOL,
                        side=side,
                        quantity=formatted_quantity,
                        order_type="MARKET",
                        position_side=position_side
                    )
                    if order:
                        self.logger.info(f"✅ Position {position_side} fermée: {formatted_quantity}")
                    else:
                        self.logger.error(f"❌ Échec fermeture position {position_side}")
                else:
                    self.logger.error(f"Erreur formatage quantité {position_side}: {quantity}")
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de la fermeture des positions: {e}", exc_info=True)
    
    def _cancel_all_pending_orders(self) -> None:
        """
        Annule tous les ordres en attente (LONG et SHORT)
        """
        self.logger.info(f"Annulation de tous les ordres en attente ({len(self.pending_orders)})")
        
        try:
            orders_to_cancel = self.pending_orders.copy()  # Copie pour éviter modification pendant itération
            
            for order in orders_to_cancel:
                order_id = order.get("orderId")
                if order_id:
                    cancel_result = self.binance_client.cancel_order(config.SYMBOL, int(order_id))
                    if cancel_result:
                        self.pending_orders.remove(order)
                        self.logger.info(f"Ordre cascade {order_id} annulé")
                    else:
                        self.logger.warning(f"Échec annulation ordre {order_id}")
                        
        except Exception as e:
            self.logger.error(f"Erreur lors de l'annulation des ordres: {e}", exc_info=True)
    
    def _cancel_pending_order(self, order: Dict[str, Any]) -> None:
        """
        Annule un ordre en attente
        
        Args:
            order: Ordre à annuler
        """
        try:
            order_id = order.get("orderId")
            if order_id:
                cancel_result = self.binance_client.cancel_order(config.SYMBOL, int(order_id))
                if cancel_result:
                    self.pending_orders.remove(order)
                    self.logger.info(f"Ordre cascade {order_id} annulé suite à l'exécution TP")
                else:
                    self.logger.warning(f"Échec annulation ordre cascade {order_id}")
        except Exception as e:
            self.logger.error(f"Erreur annulation ordre cascade: {e}", exc_info=True)