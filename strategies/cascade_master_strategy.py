"""
Stratégie CASCADE_MASTER - Stratégie actuelle avec hedge + cascade + TP avancé
Responsabilité unique : Logique de la stratégie cascade avancée
"""
from typing import Dict, Any, Optional

import config
from strategies.base_strategy import BaseStrategy


class CascadeMasterStrategy(BaseStrategy):
    """Implémentation de la stratégie CASCADE_MASTER (stratégie actuelle)"""
    
    def __init__(self) -> None:
        """Initialise la stratégie CASCADE_MASTER"""
        super().__init__()
        self.logger.info("Stratégie CASCADE_MASTER initialisée")
    
    def get_strategy_name(self) -> str:
        """Retourne le nom de la stratégie"""
        return "CASCADE_MASTER"
    
    def should_use_hedge(self) -> bool:
        """Cette stratégie utilise le hedging"""
        return config.HEDGING_CONFIG.get("ENABLED", True)
    
    def should_use_cascade(self) -> bool:
        """Cette stratégie utilise le système de cascade"""
        return config.CASCADE_CONFIG.get("ENABLED", True)
    
    def should_use_advanced_tp(self) -> bool:
        """Cette stratégie utilise le système TP avancé"""
        return config.TP_CONFIG.get("ENABLED", True)
    
    def execute_signal_strategy(
        self, 
        signal_data: Dict[str, Any], 
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute la logique CASCADE_MASTER pour un signal
        
        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading pour exécuter les ordres
            
        Returns:
            Résultat de l'exécution ou None si erreur
        """
        self.logger.info(f"Exécution signal CASCADE_MASTER: {signal_data['type']}")
        
        try:
            # Utiliser la logique existante du trading service (inchangée)
            # Le trading service gère déjà hedge + cascade + TP
            result = trading_service.execute_signal_trade(signal_data)
            
            if result:
                self.logger.info("✅ Signal CASCADE_MASTER exécuté avec succès")
                return result
            else:
                self.logger.error("❌ Échec de l'exécution CASCADE_MASTER")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur stratégie CASCADE_MASTER: {e}", exc_info=True)
            return None
    
    def get_strategy_config(self) -> Dict[str, Any]:
        """Retourne la configuration CASCADE_MASTER"""
        return {
            "hedging": config.HEDGING_CONFIG,
            "cascade": config.CASCADE_CONFIG, 
            "tp": config.TP_CONFIG
        }
    
    def cleanup(self) -> None:
        """Nettoie les ressources CASCADE_MASTER"""
        self.logger.info("Nettoyage stratégie CASCADE_MASTER")
        # La stratégie actuelle n'a pas de ressources spécifiques à nettoyer
        pass