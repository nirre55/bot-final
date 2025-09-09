"""
Classe de base abstraite pour les stratégies de trading
Responsabilité unique : Interface commune pour toutes les stratégies
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum

from core.logger import get_module_logger


class StrategyType(Enum):
    """Types de stratégies disponibles"""
    ACCUMULATOR = "ACCUMULATOR"
    CASCADE_MASTER = "CASCADE_MASTER"


class BaseStrategy(ABC):
    """Classe abstraite définissant l'interface commune pour les stratégies de trading"""
    
    def __init__(self) -> None:
        """Initialise la stratégie de base"""
        self.logger = get_module_logger(self.__class__.__name__)
        self.logger.debug(f"Stratégie {self.__class__.__name__} initialisée")
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Retourne le nom de la stratégie
        
        Returns:
            Nom de la stratégie
        """
        pass
    
    @abstractmethod
    def should_use_hedge(self) -> bool:
        """
        Détermine si cette stratégie utilise des ordres de hedge
        
        Returns:
            True si hedge activé, False sinon
        """
        pass
    
    @abstractmethod
    def should_use_cascade(self) -> bool:
        """
        Détermine si cette stratégie utilise le système de cascade
        
        Returns:
            True si cascade activé, False sinon
        """
        pass
    
    @abstractmethod
    def should_use_advanced_tp(self) -> bool:
        """
        Détermine si cette stratégie utilise le système TP avancé
        
        Returns:
            True si TP avancé activé, False sinon
        """
        pass
    
    @abstractmethod
    def execute_signal_strategy(
        self, 
        signal_data: Dict[str, Any], 
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute la logique spécifique de la stratégie pour un signal
        
        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading pour exécuter les ordres
            
        Returns:
            Résultat de l'exécution ou None si erreur
        """
        pass
    
    @abstractmethod
    def get_strategy_config(self) -> Dict[str, Any]:
        """
        Retourne la configuration spécifique de la stratégie
        
        Returns:
            Configuration de la stratégie
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        Nettoie les ressources de la stratégie
        """
        pass
    
    def log_strategy_info(self) -> None:
        """Log des informations de la stratégie"""
        self.logger.info(f"🎯 Stratégie active: {self.get_strategy_name()}")
        self.logger.info(f"   Hedge: {'✅' if self.should_use_hedge() else '❌'}")
        self.logger.info(f"   Cascade: {'✅' if self.should_use_cascade() else '❌'}")
        self.logger.info(f"   TP avancé: {'✅' if self.should_use_advanced_tp() else '❌'}")