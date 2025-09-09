"""
Stratégie ACCUMULATOR - Accumulation de positions avec prix moyen et TP dynamique
Responsabilité unique : Logique de la stratégie d'accumulation
"""
from typing import Dict, Any, Optional

import config
from strategies.base_strategy import BaseStrategy
from core.accumulator_service import AccumulatorService, AccumulatorSide


class AccumulatorStrategy(BaseStrategy):
    """Implémentation de la stratégie ACCUMULATOR (accumulation + prix moyen)"""
    
    def __init__(self, accumulator_service: AccumulatorService) -> None:
        """
        Initialise la stratégie ACCUMULATOR
        
        Args:
            accumulator_service: Service d'accumulation injecté
        """
        super().__init__()
        self.accumulator_service = accumulator_service
        self.logger.info("Stratégie ACCUMULATOR initialisée")
    
    def get_strategy_name(self) -> str:
        """Retourne le nom de la stratégie"""
        return "ACCUMULATOR"
    
    def should_use_hedge(self) -> bool:
        """Cette stratégie n'utilise pas de hedging"""
        return False
    
    def should_use_cascade(self) -> bool:
        """Cette stratégie n'utilise pas le système de cascade"""
        return False
    
    def should_use_advanced_tp(self) -> bool:
        """Cette stratégie n'utilise pas le système TP avancé"""
        return False
    
    def execute_signal_strategy(
        self, 
        signal_data: Dict[str, Any], 
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute la logique ACCUMULATOR pour un signal
        
        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading pour exécuter les ordres
            
        Returns:
            Résultat de l'exécution ou None si erreur
        """
        self.logger.info(f"Exécution signal ACCUMULATOR: {signal_data['type']}")
        
        try:
            # Déterminer le côté de l'accumulation
            signal_type = signal_data.get("type", "").upper()
            if signal_type == "LONG":
                side = AccumulatorSide.LONG
            elif signal_type == "SHORT":
                side = AccumulatorSide.SHORT
            else:
                self.logger.error(f"Type de signal invalide: {signal_type}")
                return None
            
            # Vérifier si on peut encore accumuler
            if not self.accumulator_service.can_accumulate(side):
                self.logger.warning(f"Limite d'accumulation atteinte pour {side.value} - Signal ignoré")
                return None
            
            # Obtenir la quantité pour le signal
            quantity = trading_service.get_initial_trade_quantity(config.SYMBOL, signal_data)
            if not quantity or float(quantity) == 0:
                self.logger.error("Impossible d'obtenir la quantité de trade")
                return None
            
            self.logger.info(f"Placement ordre {signal_type} {quantity} BTCUSDC")
            
            # Exécuter seulement l'ordre de base (sans hedge, sans cascade, sans TP avancé)
            order_result = self._execute_simple_order(signal_data, trading_service)
            
            if not order_result:
                self.logger.error("❌ Échec de l'exécution de l'ordre ACCUMULATOR")
                return None
            
            # Traiter l'accumulation après l'exécution
            success = self.accumulator_service.process_signal_accumulation(signal_data, order_result)
            
            if success:
                self.logger.info("✅ Signal ACCUMULATOR traité avec succès")
                return order_result
            else:
                self.logger.error("❌ Échec du traitement accumulation")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur stratégie ACCUMULATOR: {e}", exc_info=True)
            return None
    
    def _execute_simple_order(
        self, 
        signal_data: Dict[str, Any], 
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute un ordre simple sans hedge/cascade/TP
        
        Args:
            signal_data: Données du signal
            trading_service: Service de trading
            
        Returns:
            Résultat de l'ordre ou None
        """
        self.logger.debug("_execute_simple_order called")
        
        try:
            # Obtenir les paramètres de base
            signal_type = signal_data["type"].upper()
            quantity = trading_service.get_initial_trade_quantity(config.SYMBOL, signal_data)
            
            # Déterminer le side et position side
            if signal_type == "LONG":
                side = "BUY"
                position_side = "LONG"
            else:
                side = "SELL"
                position_side = "SHORT"
            
            self.logger.info(f"Placement ordre {side} {quantity} {config.SYMBOL} (position: {position_side})")
            
            # Placer l'ordre MARKET simple
            order_result = trading_service.binance_client.place_order(
                symbol=config.SYMBOL,
                side=side,
                order_type="MARKET",
                quantity=quantity,
                position_side=position_side
            )
            
            if order_result:
                self.logger.info(f"✅ Ordre ACCUMULATOR exécuté - ID: {order_result.get('orderId')}")
                return order_result
            else:
                self.logger.error("❌ Échec placement ordre ACCUMULATOR")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur placement ordre simple: {e}", exc_info=True)
            return None
    
    def get_strategy_config(self) -> Dict[str, Any]:
        """Retourne la configuration ACCUMULATOR"""
        return {
            "accumulator": config.ACCUMULATOR_CONFIG
        }
    
    def cleanup(self) -> None:
        """Nettoie les ressources ACCUMULATOR"""
        self.logger.info("Nettoyage stratégie ACCUMULATOR")
        if self.accumulator_service:
            self.accumulator_service.cleanup()
    
    def get_accumulator_service(self) -> AccumulatorService:
        """
        Retourne le service accumulator pour accès externe
        
        Returns:
            Service accumulator
        """
        return self.accumulator_service