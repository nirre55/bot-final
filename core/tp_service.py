"""
Service de gestion des Take Profit
Responsabilité unique : Gestion des ordres TP avec mise à jour automatique
"""
from typing import Dict, Optional, Any
from enum import Enum

import config
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class TPSide(Enum):
    """Côtés des TP"""
    LONG = "LONG"
    SHORT = "SHORT"


class TPService:
    """Service de gestion des ordres Take Profit"""
    
    def __init__(self, binance_client: BinanceAPIClient, trading_service=None) -> None:
        """Initialise le service TP"""
        self.logger = get_module_logger("TPService")
        self.binance_client = binance_client
        self.trading_service = trading_service  # Référence pour formatage dynamique
        
        # Prix de référence pour calculs TP (définis une seule fois)
        self.initial_price: Optional[float] = None
        self.hedge_stop_price: Optional[float] = None
        self.tp_distance: Optional[float] = None
        
        # Niveaux TP de base (avant incréments)
        self.tp_long_base: Optional[float] = None
        self.tp_short_base: Optional[float] = None
        
        # Compteurs d'incréments pour chaque côté
        self.long_increment_count: int = 0
        self.short_increment_count: int = 0
        
        # Ordres TP actifs (un par côté maximum)
        self.active_tp_long: Optional[Dict[str, Any]] = None
        self.active_tp_short: Optional[Dict[str, Any]] = None
        
        # Quantités actuelles par côté
        self.current_long_quantity: float = 0.0
        self.current_short_quantity: float = 0.0
        
        # Cache des informations de formatage pour éviter appels répétés
        self._symbol_precision_cache: Optional[Dict[str, Any]] = None
        self._cached_symbol: Optional[str] = None
        
        self.logger.debug("TPService initialisé")
    
    def set_trading_service_reference(self, trading_service) -> None:
        """
        Définit la référence au TradingService après initialisation
        
        Args:
            trading_service: Instance du TradingService pour formatage dynamique
        """
        self.trading_service = trading_service
        self.logger.debug("Référence TradingService définie pour formatage dynamique")
        
        # Précharger le cache de précision pour le symbole actuel
        self._cache_symbol_precision()
    
    def initialize_tp_levels(
        self, 
        initial_price: float, 
        hedge_stop_price: float
    ) -> None:
        """
        Initialise les niveaux TP de base
        
        Args:
            initial_price: Prix d'exécution de l'ordre initial (signal)
            hedge_stop_price: Prix de stop de l'ordre hedge
        """
        self.logger.debug(f"initialize_tp_levels called: initial={initial_price}, hedge_stop={hedge_stop_price}")
        
        if not config.TP_CONFIG["ENABLED"]:
            self.logger.info("Système TP désactivé dans la configuration")
            return
        
        # Sauvegarder les prix de référence
        self.initial_price = initial_price
        self.hedge_stop_price = hedge_stop_price
        
        # Calculer la distance TP (une seule fois) avec arrondi pour éviter erreurs de précision
        distance_raw: float = abs(initial_price - hedge_stop_price) * config.TP_CONFIG["MULTIPLIER"]
        distance: float = round(distance_raw, 2)  # Arrondir à 2 décimales
        self.tp_distance = distance
        
        # Calculer les niveaux TP de base avec arrondi
        self.tp_long_base = round(initial_price + distance, 2)
        self.tp_short_base = round(hedge_stop_price - distance, 2)
        
        self.logger.info(f"Niveaux TP initialisés:")
        self.logger.info(f"  Distance TP: {self.tp_distance}")
        self.logger.info(f"  TP LONG base: {self.tp_long_base}")
        self.logger.info(f"  TP SHORT base: {self.tp_short_base}")
    
    def create_or_update_tp(
        self, 
        side: TPSide, 
        quantity: float, 
        is_initial: bool = False
    ) -> bool:
        """
        Crée ou met à jour un ordre TP
        
        Args:
            side: Côté du TP (LONG ou SHORT)
            quantity: Quantité totale de la position
            is_initial: True si c'est le premier TP (pas d'incrément)
            
        Returns:
            True si succès, False sinon
        """
        self.logger.debug(f"create_or_update_tp called: {side.value} {quantity} initial={is_initial}")
        
        if not config.TP_CONFIG["ENABLED"] or not self.tp_distance:
            self.logger.debug("TP désactivé ou pas encore initialisé")
            return False
        
        try:
            # Annuler l'ancien TP s'il existe
            if side == TPSide.LONG and self.active_tp_long:
                self._cancel_tp_order(self.active_tp_long)
                self.active_tp_long = None
            elif side == TPSide.SHORT and self.active_tp_short:
                self._cancel_tp_order(self.active_tp_short)
                self.active_tp_short = None
            
            # Calculer le niveau TP avec incréments
            tp_level = self._calculate_tp_level(side, is_initial)
            
            if tp_level is None:
                self.logger.error(f"Impossible de calculer le niveau TP pour {side.value}")
                return False
            
            # Créer le nouvel ordre TP
            tp_order = self._place_tp_order(side, quantity, tp_level)
            
            if tp_order:
                # Sauvegarder l'ordre TP actif
                if side == TPSide.LONG:
                    self.active_tp_long = tp_order
                    self.current_long_quantity = quantity
                    if not is_initial:
                        self.long_increment_count += 1
                else:
                    self.active_tp_short = tp_order
                    self.current_short_quantity = quantity
                    if not is_initial:
                        self.short_increment_count += 1
                
                self.logger.info(f"✅ TP {side.value} créé/mis à jour - ID: {tp_order.get('orderId')} @ {tp_level}")
                return True
            else:
                self.logger.error(f"❌ Échec de création du TP {side.value}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la gestion TP {side.value}: {e}", exc_info=True)
            return False
    
    def _calculate_tp_level(self, side: TPSide, is_initial: bool) -> Optional[float]:
        """
        Calcule le niveau TP avec incréments
        
        Args:
            side: Côté du TP
            is_initial: True si c'est le premier TP
            
        Returns:
            Niveau TP calculé
        """
        self.logger.debug(f"_calculate_tp_level called: {side.value} initial={is_initial}")
        
        if side == TPSide.LONG:
            base_level = self.tp_long_base
            increment_count = self.long_increment_count if not is_initial else 0
        else:
            base_level = self.tp_short_base
            increment_count = self.short_increment_count if not is_initial else 0
        
        if base_level is None:
            return None
        
        # Calculer l'incrément total
        increment_percent = config.TP_CONFIG["INCREMENT_PERCENT"]
        total_increment = increment_count * increment_percent
        
        if side == TPSide.LONG:
            # LONG : prix monte avec les incréments
            tp_level_raw = base_level * (1 + total_increment)
        else:
            # SHORT : prix descend avec les incréments
            tp_level_raw = base_level * (1 - total_increment)
        
        # Arrondir le niveau TP final à 2 décimales
        tp_level = round(tp_level_raw, 2)
        
        self.logger.debug(f"TP {side.value}: base={base_level}, incréments={increment_count}, niveau={tp_level}")
        return tp_level
    
    def _place_tp_order(self, side: TPSide, quantity: float, tp_level: float) -> Optional[Dict[str, Any]]:
        """
        Place un ordre TAKE_PROFIT sur Binance
        
        Args:
            side: Côté du TP
            quantity: Quantité de l'ordre
            tp_level: Niveau de déclenchement TP
            
        Returns:
            Résultat de l'ordre ou None
        """
        self.logger.debug(f"_place_tp_order called: {side.value} {quantity} @ {tp_level}")
        
        try:
            # Configurer les paramètres selon le côté
            if side == TPSide.LONG:
                order_side = "SELL"  # Vendre la position LONG
                position_side = "LONG"
                # Prix limite légèrement au-dessus du stop pour meilleur remplissage
                limit_price = tp_level * (1 + config.TP_CONFIG["PRICE_OFFSET"])
            else:
                order_side = "BUY"  # Racheter la position SHORT
                position_side = "SHORT"
                # Prix limite légèrement en-dessous du stop
                limit_price = tp_level * (1 - config.TP_CONFIG["PRICE_OFFSET"])
            
            # Utiliser le formatage optimisé avec cache
            formatted_quantity = self._format_tp_quantity(quantity)
            formatted_stop_price = self._format_tp_price(tp_level)
            formatted_limit_price = self._format_tp_price(limit_price)
            
            self.logger.info(f"Placement TP {side.value}: {order_side} {formatted_quantity} @ stop:{formatted_stop_price} limit:{formatted_limit_price}")
            
            # Utiliser la méthode TP du client Binance (à implémenter)
            tp_order = self.binance_client.place_take_profit_order(
                symbol=config.SYMBOL,
                side=order_side,
                quantity=formatted_quantity,
                stop_price=formatted_stop_price,
                price=formatted_limit_price,
                position_side=position_side
            )
            
            return tp_order
            
        except Exception as e:
            self.logger.error(f"Erreur lors du placement TP: {e}", exc_info=True)
            return None
    
    def _cancel_tp_order(self, tp_order: Dict[str, Any]) -> bool:
        """
        Annule un ordre TP existant
        
        Args:
            tp_order: Ordre TP à annuler
            
        Returns:
            True si succès, False sinon
        """
        self.logger.debug("_cancel_tp_order called")
        
        try:
            order_id = tp_order.get("orderId")
            if not order_id:
                self.logger.error("ID d'ordre TP manquant pour annulation")
                return False
            
            # Annuler l'ordre
            cancel_result = self.binance_client.cancel_order(config.SYMBOL, int(order_id))
            
            if cancel_result:
                self.logger.info(f"Ordre TP {order_id} annulé avec succès")
                return True
            else:
                self.logger.warning(f"Échec de l'annulation de l'ordre TP {order_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'annulation TP: {e}", exc_info=True)
            return False
    
    def get_tp_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel du système TP
        
        Returns:
            Dictionnaire avec l'état des TP
        """
        return {
            "enabled": config.TP_CONFIG["ENABLED"],
            "initialized": self.tp_distance is not None,
            "tp_distance": self.tp_distance,
            "long_tp_active": self.active_tp_long is not None,
            "short_tp_active": self.active_tp_short is not None,
            "long_increment_count": self.long_increment_count,
            "short_increment_count": self.short_increment_count,
            "current_long_quantity": self.current_long_quantity,
            "current_short_quantity": self.current_short_quantity
        }
    
    def check_tp_execution_and_cleanup(self) -> Optional[str]:
        """
        Vérifie si un TP a été exécuté et annule l'autre TP si nécessaire
        
        Returns:
            Côté du TP exécuté ("LONG" ou "SHORT") ou None
        """
        self.logger.debug("check_tp_execution_and_cleanup called")
        
        if not config.TP_CONFIG["ENABLED"]:
            return None
        
        try:
            executed_side = None
            
            # Vérifier TP LONG
            if self.active_tp_long:
                long_order_id = self.active_tp_long.get("orderId")
                if long_order_id:
                    order_status = self.binance_client.get_order_status(config.SYMBOL, int(long_order_id))
                    if order_status and order_status.get("status") == "FILLED":
                        self.logger.info(f"TP LONG exécuté - ID: {long_order_id}")
                        executed_side = "LONG"
                        self.active_tp_long = None
                        self.current_long_quantity = 0.0
                        
                        # Annuler le TP SHORT s'il existe
                        if self.active_tp_short:
                            self._cancel_tp_order(self.active_tp_short)
                            self.active_tp_short = None
                            self.logger.info("TP SHORT annulé suite à l'exécution du TP LONG")
            
            # Vérifier TP SHORT
            if self.active_tp_short and executed_side is None:
                short_order_id = self.active_tp_short.get("orderId")
                if short_order_id:
                    order_status = self.binance_client.get_order_status(config.SYMBOL, int(short_order_id))
                    if order_status and order_status.get("status") == "FILLED":
                        self.logger.info(f"TP SHORT exécuté - ID: {short_order_id}")
                        executed_side = "SHORT"
                        self.active_tp_short = None
                        self.current_short_quantity = 0.0
                        
                        # Annuler le TP LONG s'il existe
                        if self.active_tp_long:
                            self._cancel_tp_order(self.active_tp_long)
                            self.active_tp_long = None
                            self.logger.info("TP LONG annulé suite à l'exécution du TP SHORT")
            
            if executed_side:
                self.logger.info(f"✅ TP {executed_side} exécuté avec succès - Nettoyage automatique effectué")
                # Reset complet du système TP pour permettre nouveau cycle
                self._reset_tp_system()
                
            return executed_side
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification TP: {e}", exc_info=True)
            return None
    
    def _reset_tp_system(self) -> None:
        """
        Reset complet du système TP pour nouveau cycle
        """
        self.logger.info("🔄 Reset complet du système TP")
        
        try:
            # Reset des prix de référence
            self.initial_price = None
            self.hedge_stop_price = None
            self.tp_distance = None
            
            # Reset des niveaux TP de base
            self.tp_long_base = None
            self.tp_short_base = None
            
            # Reset des compteurs d'incréments
            self.long_increment_count = 0
            self.short_increment_count = 0
            
            # Reset des ordres TP actifs (déjà fait dans check_tp_execution_and_cleanup)
            self.active_tp_long = None
            self.active_tp_short = None
            
            # Reset des quantités actuelles
            self.current_long_quantity = 0.0
            self.current_short_quantity = 0.0
            
            self.logger.info("✅ Système TP réinitialisé - Prêt pour nouveau signal")
            
        except Exception as e:
            self.logger.error(f"Erreur lors du reset TP: {e}", exc_info=True)
    
    def format_tp_display(self) -> str:
        """
        Formate l'affichage de l'état TP
        
        Returns:
            Chaîne formatée pour l'affichage
        """
        if not config.TP_CONFIG["ENABLED"] or not self.tp_distance:
            return ""
        
        status = self.get_tp_status()
        
        tp_info = []
        
        if status["long_tp_active"]:
            tp_info.append(f"LONG TP 🎯 (inc:{status['long_increment_count']})")
        
        if status["short_tp_active"]:
            tp_info.append(f"SHORT TP 🎯 (inc:{status['short_increment_count']})")
        
        if tp_info:
            return f"TP: {' | '.join(tp_info)}"
        else:
            return f"TP: Distance={status['tp_distance']:.2f} (prêt)"
    
    def cleanup(self) -> None:
        """Nettoie les ressources du service TP"""
        self.logger.info("Nettoyage du service TP")
        
        # Annuler les ordres TP actifs si nécessaire
        if self.active_tp_long:
            self._cancel_tp_order(self.active_tp_long)
        
        if self.active_tp_short:
            self._cancel_tp_order(self.active_tp_short)
        
        # Reset des variables
        self.active_tp_long = None
        self.active_tp_short = None
        self.current_long_quantity = 0.0
        self.current_short_quantity = 0.0
    
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
            
            self.logger.info(f"Cache formatage TP: tick_size={tick_size}, step_size={step_size}")
        else:
            self.logger.warning("Impossible de mettre en cache les informations de précision")
    
    def _format_tp_price(self, price: float) -> str:
        """
        Formate un prix TP avec cache optimisé
        
        Args:
            price: Prix à formater
            
        Returns:
            Prix formaté selon le symbole
        """
        if not self._symbol_precision_cache or not self.trading_service:
            # Fallback
            return f"{round(price, 2):.2f}"
        
        tick_size = self._symbol_precision_cache["price_filter"]["tick_size"]
        return self.trading_service._format_price(price, tick_size)
    
    def _format_tp_quantity(self, quantity: float) -> str:
        """
        Formate une quantité TP avec cache optimisé
        
        Args:
            quantity: Quantité à formater
            
        Returns:
            Quantité formatée selon le symbole
        """
        if not self._symbol_precision_cache or not self.trading_service:
            # Fallback
            return f"{quantity:.3f}".rstrip('0').rstrip('.')
        
        step_size = self._symbol_precision_cache["lot_size"]["step_size"]
        return self.trading_service._format_quantity(quantity, step_size)