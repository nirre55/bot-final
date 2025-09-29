"""
Manager principal pour gérer les stratégies de trading
Responsabilité unique : Orchestration et coordination des stratégies
"""
from typing import Optional, Dict, Any

import config
from strategies.base_strategy import BaseStrategy
from strategies.strategy_factory import StrategyFactory
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class StrategyManager:
    """Manager principal pour la gestion des stratégies de trading"""
    
    def __init__(self, binance_client: BinanceAPIClient) -> None:
        """
        Initialise le manager des stratégies
        
        Args:
            binance_client: Client Binance pour les services
        """
        self.logger = get_module_logger("StrategyManager")
        self.binance_client = binance_client
        
        # Factory pour créer les stratégies
        self.strategy_factory = StrategyFactory(binance_client)
        
        # Stratégie courante
        self.current_strategy: Optional[BaseStrategy] = None
        self.current_strategy_type: Optional[str] = None
        
        self.logger.debug("StrategyManager initialisé")
    
    def initialize_strategy(self, trading_service: Optional[Any] = None) -> bool:
        """
        Initialise la stratégie selon la configuration
        
        Args:
            trading_service: Service de trading pour injection de dépendance
            
        Returns:
            True si initialisation réussie, False sinon
        """
        self.logger.debug("initialize_strategy called")
        
        try:
            # Obtenir le type de stratégie depuis la config
            strategy_type = config.STRATEGY_CONFIG.get("STRATEGY_TYPE", "CASCADE_MASTER")
            
            self.logger.info(f"Initialisation de la stratégie: {strategy_type}")
            
            # Valider la configuration
            if not self.strategy_factory.validate_strategy_config(strategy_type):
                self.logger.error(f"Configuration invalide pour {strategy_type}")
                return False
            
            # Créer la stratégie
            strategy = self.strategy_factory.create_strategy(strategy_type, trading_service)
            
            if not strategy:
                self.logger.error(f"Échec création stratégie {strategy_type}")
                return False
            
            # Nettoyer l'ancienne stratégie si elle existe
            if self.current_strategy:
                self.logger.info(f"Nettoyage de l'ancienne stratégie: {self.current_strategy_type}")
                self.current_strategy.cleanup()
            
            # Définir la nouvelle stratégie
            self.current_strategy = strategy
            self.current_strategy_type = strategy_type

            # Logger les informations de la stratégie
            self.strategy_factory.log_strategy_info(strategy)
            
            self.logger.info(f"✅ Stratégie {strategy_type} initialisée avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation stratégie: {e}", exc_info=True)
            return False

    def set_user_data_manager(self, user_data_manager) -> None:
        """
        Configure le user_data_manager pour la stratégie courante

        Args:
            user_data_manager: Manager User Data Stream
        """
        try:
            if self.current_strategy and hasattr(self.current_strategy, 'user_data_manager'):
                self.current_strategy.user_data_manager = user_data_manager
                if user_data_manager:
                    user_data_manager.trading_bot_reference = self.current_strategy
                self.logger.debug(f"User Data Manager configuré pour {self.current_strategy_type}")

        except Exception as e:
            self.logger.error(f"Erreur configuration User Data Manager: {e}", exc_info=True)
    
    def execute_signal(
        self, 
        signal_data: Dict[str, Any], 
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute un signal selon la stratégie courante
        
        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading
            
        Returns:
            Résultat de l'exécution ou None
        """
        self.logger.debug("execute_signal called")
        
        if not self.current_strategy:
            self.logger.error("Aucune stratégie initialisée pour exécuter le signal")
            return None
        
        try:
            self.logger.info(f"Exécution signal via stratégie {self.current_strategy_type}")
            
            result = self.current_strategy.execute_signal_strategy(signal_data, trading_service)
            
            if result:
                self.logger.info(f"✅ Signal exécuté avec succès via {self.current_strategy_type}")
                return result
            else:
                self.logger.error(f"❌ Échec exécution signal via {self.current_strategy_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur exécution signal: {e}", exc_info=True)
            return None
    
    def should_use_hedge(self) -> bool:
        """
        Vérifie si la stratégie courante utilise le hedging
        
        Returns:
            True si hedge utilisé, False sinon
        """
        if self.current_strategy:
            return self.current_strategy.should_use_hedge()
        return False
    
    def should_use_cascade(self) -> bool:
        """
        Vérifie si la stratégie courante utilise le cascade
        
        Returns:
            True si cascade utilisé, False sinon
        """
        if self.current_strategy:
            return self.current_strategy.should_use_cascade()
        return False
    
    def should_use_advanced_tp(self) -> bool:
        """
        Vérifie si la stratégie courante utilise le TP avancé
        
        Returns:
            True si TP avancé utilisé, False sinon
        """
        if self.current_strategy:
            return self.current_strategy.should_use_advanced_tp()
        return False
    
    def get_current_strategy_name(self) -> Optional[str]:
        """
        Retourne le nom de la stratégie courante
        
        Returns:
            Nom de la stratégie ou None
        """
        if self.current_strategy:
            return self.current_strategy.get_strategy_name()
        return None
    
    def get_current_strategy_config(self) -> Optional[Dict[str, Any]]:
        """
        Retourne la configuration de la stratégie courante
        
        Returns:
            Configuration ou None
        """
        if self.current_strategy:
            return self.current_strategy.get_strategy_config()
        return None
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Retourne l'état du manager de stratégies
        
        Returns:
            Dictionnaire avec l'état actuel
        """
        return {
            "strategy_initialized": self.current_strategy is not None,
            "current_strategy_type": self.current_strategy_type,
            "current_strategy_name": self.get_current_strategy_name(),
            "uses_hedge": self.should_use_hedge(),
            "uses_cascade": self.should_use_cascade(),
            "uses_advanced_tp": self.should_use_advanced_tp(),
            "available_strategies": self.strategy_factory.get_available_strategies()
        }
    
    def reload_strategy(self, trading_service: Optional[Any] = None) -> bool:
        """
        Recharge la stratégie depuis la configuration
        
        Args:
            trading_service: Service de trading pour injection
            
        Returns:
            True si rechargement réussi, False sinon
        """
        self.logger.info("Rechargement de la stratégie depuis la configuration")
        return self.initialize_strategy(trading_service)
    
    def switch_strategy(
        self, 
        new_strategy_type: str, 
        trading_service: Optional[Any] = None
    ) -> bool:
        """
        Change de stratégie manuellement
        
        Args:
            new_strategy_type: Nouveau type de stratégie
            trading_service: Service de trading
            
        Returns:
            True si changement réussi, False sinon
        """
        self.logger.info(f"Changement manuel de stratégie vers: {new_strategy_type}")
        
        # Temporairement changer la config
        old_strategy_type = config.STRATEGY_CONFIG.get("STRATEGY_TYPE")
        config.STRATEGY_CONFIG["STRATEGY_TYPE"] = new_strategy_type
        
        success = self.initialize_strategy(trading_service)
        
        if not success:
            # Restaurer l'ancienne config en cas d'échec
            self.logger.warning("Échec changement stratégie - restauration ancienne config")
            config.STRATEGY_CONFIG["STRATEGY_TYPE"] = old_strategy_type
            self.initialize_strategy(trading_service)
            return False
        
        return True
    
    def cleanup(self) -> None:
        """Nettoie les ressources du manager"""
        self.logger.info("Nettoyage du StrategyManager")
        
        if self.current_strategy:
            self.logger.info(f"Nettoyage stratégie {self.current_strategy_type}")
            self.current_strategy.cleanup()
            self.current_strategy = None
            self.current_strategy_type = None