"""
Service de gestion de la stratégie ACCUMULATOR
Responsabilité unique : Accumulation de positions avec prix moyen et TP dynamique
"""
from typing import Dict, Any, Optional
from enum import Enum

import config
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class AccumulatorSide(Enum):
    """Côtés d'accumulation"""
    LONG = "LONG"
    SHORT = "SHORT"


class AccumulatorService:
    """Service de gestion des accumulations de positions avec TP dynamique"""
    
    def __init__(self, binance_client: BinanceAPIClient, trading_service=None) -> None:
        """Initialise le service Accumulator"""
        self.logger = get_module_logger("AccumulatorService")
        self.binance_client = binance_client
        self.trading_service = trading_service  # Référence pour formatage dynamique
        
        # Compteurs d'accumulation par côté
        self.long_accumulation_count: int = 0
        self.short_accumulation_count: int = 0
        
        # TPs actifs (un par côté maximum)
        self.active_tp_long: Optional[Dict[str, Any]] = None
        self.active_tp_short: Optional[Dict[str, Any]] = None
        
        # Quantités actuelles par côté (pour calcul prix moyen)
        self.current_long_quantity: float = 0.0
        self.current_short_quantity: float = 0.0
        
        # Cache des informations de formatage pour éviter appels répétés
        self._symbol_precision_cache: Optional[Dict[str, Any]] = None
        self._cached_symbol: Optional[str] = None
        
        self.logger.debug("AccumulatorService initialisé")
    
    def set_trading_service_reference(self, trading_service) -> None:
        """
        Définit la référence au TradingService après initialisation
        
        Args:
            trading_service: Instance du TradingService pour formatage dynamique
        """
        self.trading_service = trading_service
        self.logger.debug("Référence TradingService définie pour AccumulatorService")
        
        # Précharger le cache de précision pour le symbole actuel
        self._cache_symbol_precision()
    
    def can_accumulate(self, side: AccumulatorSide) -> bool:
        """
        Vérifie si on peut encore accumuler sur un côté
        
        Args:
            side: Côté à vérifier
            
        Returns:
            True si accumulation possible, False sinon
        """
        max_accumulations = config.ACCUMULATOR_CONFIG.get("MAX_ACCUMULATIONS", 10)
        
        if side == AccumulatorSide.LONG:
            current_count = self.long_accumulation_count
        else:
            current_count = self.short_accumulation_count
        
        can_accumulate = current_count < max_accumulations
        self.logger.debug(f"Accumulation {side.value}: {current_count}/{max_accumulations} - {'✅' if can_accumulate else '❌'}")
        
        return can_accumulate
    
    def process_signal_accumulation(
        self, 
        signal_data: Dict[str, Any],
        order_result: Dict[str, Any]
    ) -> bool:
        """
        Traite l'accumulation après exécution d'un signal
        
        Args:
            signal_data: Données du signal original
            order_result: Résultat de l'exécution de l'ordre
            
        Returns:
            True si traitement réussi, False sinon
        """
        self.logger.debug("process_signal_accumulation called")
        
        try:
            # Déterminer le côté de l'accumulation
            signal_type = signal_data.get("type", "").upper()
            if signal_type == "LONG":
                side = AccumulatorSide.LONG
            elif signal_type == "SHORT":
                side = AccumulatorSide.SHORT
            else:
                self.logger.error(f"Type de signal invalide: {signal_type}")
                return False
            
            # Vérifier si on peut encore accumuler
            if not self.can_accumulate(side):
                self.logger.warning(f"Limite d'accumulation atteinte pour {side.value}")
                return False
            
            # Attendre et récupérer le prix moyen de la position via API
            avg_price = self._get_average_position_price(side)
            if avg_price is None:
                self.logger.error(f"Impossible de récupérer le prix moyen {side.value}")
                return False
            
            # Incrémenter le compteur d'accumulation
            if side == AccumulatorSide.LONG:
                self.long_accumulation_count += 1
                count = self.long_accumulation_count
            else:
                self.short_accumulation_count += 1
                count = self.short_accumulation_count
            
            self.logger.info(f"📊 Accumulation #{count} {side.value} - Prix moyen: {avg_price}")
            
            # Créer ou mettre à jour le TP basé sur le prix moyen
            success = self._create_or_update_accumulator_tp(side, avg_price)
            
            if success:
                self.logger.info(f"✅ TP {side.value} mis à jour pour accumulation #{count}")
                return True
            else:
                self.logger.error(f"❌ Échec mise à jour TP {side.value}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement accumulation: {e}", exc_info=True)
            return False
    
    def _get_average_position_price(self, side: AccumulatorSide) -> Optional[float]:
        """
        Récupère le prix moyen de la position via l'API Binance
        
        Args:
            side: Côté de la position
            
        Returns:
            Prix moyen ou None si erreur
        """
        self.logger.debug(f"_get_average_position_price called: {side.value}")
        
        try:
            # Récupérer les informations de position via API
            position_info = self.binance_client.get_position_info(config.SYMBOL)
            
            if not position_info:
                self.logger.error("Impossible de récupérer les informations de position")
                return None
            
            # Chercher la position correspondante au côté
            for position in position_info:
                pos_side = position.get("positionSide", "")
                if pos_side == side.value:
                    avg_price_str = position.get("entryPrice", "0")
                    position_amt = float(position.get("positionAmt", "0"))
                    
                    # Vérifier qu'on a bien une position ouverte
                    if position_amt == 0:
                        self.logger.warning(f"Aucune position {side.value} trouvée")
                        return None
                    
                    avg_price = float(avg_price_str)
                    self.logger.info(f"Prix moyen {side.value}: {avg_price} (quantité: {abs(position_amt)})")
                    
                    # Mettre à jour la quantité courante
                    if side == AccumulatorSide.LONG:
                        self.current_long_quantity = abs(position_amt)
                    else:
                        self.current_short_quantity = abs(position_amt)
                    
                    return avg_price
            
            self.logger.warning(f"Position {side.value} non trouvée dans les résultats API")
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du prix moyen: {e}", exc_info=True)
            return None
    
    def _create_or_update_accumulator_tp(self, side: AccumulatorSide, avg_price: float) -> bool:
        """
        Crée ou met à jour un TP basé sur le prix moyen d'accumulation
        
        Args:
            side: Côté du TP
            avg_price: Prix moyen de la position
            
        Returns:
            True si succès, False sinon
        """
        self.logger.debug(f"_create_or_update_accumulator_tp called: {side.value} @ {avg_price}")
        
        try:
            # Annuler l'ancien TP s'il existe
            if side == AccumulatorSide.LONG and self.active_tp_long:
                self._cancel_tp_order(self.active_tp_long)
                self.active_tp_long = None
            elif side == AccumulatorSide.SHORT and self.active_tp_short:
                self._cancel_tp_order(self.active_tp_short)
                self.active_tp_short = None
            
            # Calculer le niveau TP basé sur le prix moyen
            tp_percent = config.ACCUMULATOR_CONFIG.get("TP_PERCENT", 0.01)
            
            if side == AccumulatorSide.LONG:
                tp_level = avg_price * (1 + tp_percent)  # +1% au-dessus
                quantity = self.current_long_quantity
            else:
                tp_level = avg_price * (1 - tp_percent)  # -1% en-dessous
                quantity = self.current_short_quantity
            
            # Placer l'ordre TP
            tp_order = self._place_accumulator_tp_order(side, quantity, tp_level)
            
            if tp_order:
                # Sauvegarder l'ordre TP actif
                if side == AccumulatorSide.LONG:
                    self.active_tp_long = tp_order
                else:
                    self.active_tp_short = tp_order
                
                self.logger.info(f"✅ TP {side.value} créé - ID: {tp_order.get('orderId')} @ {tp_level}")
                return True
            else:
                self.logger.error(f"❌ Échec création TP {side.value}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la gestion TP accumulator: {e}", exc_info=True)
            return False
    
    def _place_accumulator_tp_order(
        self, 
        side: AccumulatorSide, 
        quantity: float, 
        tp_level: float
    ) -> Optional[Dict[str, Any]]:
        """
        Place un ordre TAKE_PROFIT pour l'accumulation
        
        Args:
            side: Côté du TP
            quantity: Quantité de l'ordre
            tp_level: Niveau de déclenchement TP
            
        Returns:
            Résultat de l'ordre ou None
        """
        self.logger.debug(f"_place_accumulator_tp_order called: {side.value} {quantity} @ {tp_level}")
        
        try:
            # Configurer les paramètres selon le côté (même logique que TP service)
            if side == AccumulatorSide.LONG:
                order_side = "SELL"  # Vendre la position LONG
                position_side = "LONG"
                # Limit price = valeur TP exacte
                limit_price = tp_level
                # Stop price = légèrement en dessous du limit pour trigger
                stop_price = tp_level * (1 - config.ACCUMULATOR_CONFIG.get("PRICE_OFFSET", 0.001))
            else:
                order_side = "BUY"  # Racheter la position SHORT
                position_side = "SHORT"
                # Limit price = valeur TP exacte
                limit_price = tp_level
                # Stop price = légèrement au-dessus du limit pour trigger
                stop_price = tp_level * (1 + config.ACCUMULATOR_CONFIG.get("PRICE_OFFSET", 0.001))
            
            # Utiliser le formatage optimisé avec cache
            formatted_quantity = self._format_quantity(quantity)
            formatted_stop_price = self._format_price(stop_price)
            formatted_limit_price = self._format_price(limit_price)
            
            self.logger.info(f"Placement TP {side.value}: {order_side} {formatted_quantity} @ stop:{formatted_stop_price} limit:{formatted_limit_price}")
            
            # Placer l'ordre TP via le client Binance
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
            self.logger.error(f"Erreur lors du placement TP accumulator: {e}", exc_info=True)
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
    
    def check_tp_execution_and_reset(self) -> Optional[str]:
        """
        Vérifie si un TP a été exécuté et reset le côté correspondant
        
        Returns:
            Côté du TP exécuté ("LONG" ou "SHORT") ou None
        """
        self.logger.debug("check_tp_execution_and_reset called")
        
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
                        self._reset_accumulation_side(AccumulatorSide.LONG)
            
            # Vérifier TP SHORT
            if self.active_tp_short and executed_side is None:
                short_order_id = self.active_tp_short.get("orderId")
                if short_order_id:
                    order_status = self.binance_client.get_order_status(config.SYMBOL, int(short_order_id))
                    if order_status and order_status.get("status") == "FILLED":
                        self.logger.info(f"TP SHORT exécuté - ID: {short_order_id}")
                        executed_side = "SHORT"
                        self._reset_accumulation_side(AccumulatorSide.SHORT)
            
            return executed_side
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification TP accumulator: {e}", exc_info=True)
            return None
    
    def _reset_accumulation_side(self, side: AccumulatorSide) -> None:
        """
        Reset l'accumulation pour un côté spécifique
        
        Args:
            side: Côté à reset
        """
        self.logger.info(f"🔄 Reset accumulation {side.value}")
        
        try:
            if side == AccumulatorSide.LONG:
                self.long_accumulation_count = 0
                self.active_tp_long = None
                self.current_long_quantity = 0.0
            else:
                self.short_accumulation_count = 0
                self.active_tp_short = None
                self.current_short_quantity = 0.0
            
            self.logger.info(f"✅ Accumulation {side.value} réinitialisée")
            
        except Exception as e:
            self.logger.error(f"Erreur lors du reset accumulation: {e}", exc_info=True)
    
    def get_accumulator_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel du système accumulator
        
        Returns:
            Dictionnaire avec l'état des accumulations
        """
        return {
            "enabled": config.ACCUMULATOR_CONFIG.get("ENABLED", True),
            "tp_percent": config.ACCUMULATOR_CONFIG.get("TP_PERCENT", 0.01),
            "max_accumulations": config.ACCUMULATOR_CONFIG.get("MAX_ACCUMULATIONS", 10),
            "long_count": self.long_accumulation_count,
            "short_count": self.short_accumulation_count,
            "long_tp_active": self.active_tp_long is not None,
            "short_tp_active": self.active_tp_short is not None,
            "current_long_quantity": self.current_long_quantity,
            "current_short_quantity": self.current_short_quantity
        }
    
    def format_accumulator_display(self) -> str:
        """
        Formate l'affichage de l'état accumulator
        
        Returns:
            Chaîne formatée pour l'affichage
        """
        status = self.get_accumulator_status()
        
        acc_info = []
        
        if status["long_count"] > 0:
            tp_status = "🎯" if status["long_tp_active"] else "⏳"
            acc_info.append(f"LONG: {status['long_count']}/{status['max_accumulations']} {tp_status}")
        
        if status["short_count"] > 0:
            tp_status = "🎯" if status["short_tp_active"] else "⏳"
            acc_info.append(f"SHORT: {status['short_count']}/{status['max_accumulations']} {tp_status}")
        
        if acc_info:
            return f"ACCUMULATOR: {' | '.join(acc_info)}"
        else:
            return f"ACCUMULATOR: Prêt (TP: ±{status['tp_percent']*100:.1f}%)"
    
    def cleanup(self) -> None:
        """Nettoie les ressources du service accumulator"""
        self.logger.info("Nettoyage du service AccumulatorService")
        
        # Annuler les ordres TP actifs si nécessaire
        if self.active_tp_long:
            self._cancel_tp_order(self.active_tp_long)
        
        if self.active_tp_short:
            self._cancel_tp_order(self.active_tp_short)
        
        # Reset des variables
        self._reset_accumulation_side(AccumulatorSide.LONG)
        self._reset_accumulation_side(AccumulatorSide.SHORT)
    
    def _cache_symbol_precision(self) -> None:
        """Met en cache les informations de précision pour éviter appels répétés"""
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
            
            self.logger.info(f"Cache formatage Accumulator: tick_size={tick_size}, step_size={step_size}")
        else:
            self.logger.warning("Impossible de mettre en cache les informations de précision")
    
    def _format_price(self, price: float) -> str:
        """
        Formate un prix avec cache optimisé
        
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
    
    def _format_quantity(self, quantity: float) -> str:
        """
        Formate une quantité avec cache optimisé
        
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