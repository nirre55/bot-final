"""
Factory pour créer et gérer les stratégies de trading
Responsabilité unique : Création et configuration des stratégies selon la configuration
"""
from typing import Optional, Any

import config
from strategies.base_strategy import BaseStrategy, StrategyType
from strategies.cascade_master_strategy import CascadeMasterStrategy
from strategies.accumulator_strategy import AccumulatorStrategy
from strategies.all_or_nothing_strategy import AllOrNothingStrategy
from strategies.one_or_more_strategy import OneOrMoreStrategy
from core.accumulator_service import AccumulatorService
from core.all_or_nothing_service import AllOrNothingService
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class StrategyFactory:
    """Factory pour créer les stratégies de trading"""
    
    def __init__(self, binance_client: BinanceAPIClient) -> None:
        """
        Initialise la factory des stratégies
        
        Args:
            binance_client: Client Binance pour les services
        """
        self.logger = get_module_logger("StrategyFactory")
        self.binance_client = binance_client
        self.logger.debug("StrategyFactory initialisée")
    
    def create_strategy(
        self, 
        strategy_type: Optional[str] = None,
        trading_service: Optional[Any] = None
    ) -> Optional[BaseStrategy]:
        """
        Crée une stratégie selon la configuration
        
        Args:
            strategy_type: Type de stratégie à créer (optionnel, utilise config si None)
            trading_service: Service de trading pour injection de dépendance
            
        Returns:
            Instance de stratégie ou None si erreur
        """
        self.logger.debug("create_strategy called")
        
        # Utiliser le type de config si non spécifié
        if strategy_type is None:
            strategy_type = config.STRATEGY_CONFIG.get("STRATEGY_TYPE", "CASCADE_MASTER")
        
        self.logger.info(f"Création de la stratégie: {strategy_type}")
        
        try:
            if strategy_type == StrategyType.CASCADE_MASTER.value:
                return self._create_cascade_master_strategy()

            elif strategy_type == StrategyType.ACCUMULATOR.value:
                return self._create_accumulator_strategy(trading_service)

            elif strategy_type == StrategyType.ALL_OR_NOTHING.value:
                return self._create_all_or_nothing_strategy(trading_service)

            elif strategy_type == StrategyType.ONE_OR_MORE.value:
                return self._create_one_or_more_strategy()

            else:
                self.logger.error(f"Type de stratégie inconnu: {strategy_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur création stratégie {strategy_type}: {e}", exc_info=True)
            return None
    
    def _create_cascade_master_strategy(self) -> Optional[CascadeMasterStrategy]:
        """
        Crée une stratégie CASCADE_MASTER
        
        Returns:
            Instance CASCADE_MASTER ou None
        """
        self.logger.debug("_create_cascade_master_strategy called")
        
        try:
            strategy = CascadeMasterStrategy()
            self.logger.info("✅ Stratégie CASCADE_MASTER créée avec succès")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Erreur création CASCADE_MASTER: {e}", exc_info=True)
            return None
    
    def _create_accumulator_strategy(
        self, 
        trading_service: Optional[Any]
    ) -> Optional[AccumulatorStrategy]:
        """
        Crée une stratégie ACCUMULATOR avec ses services
        
        Args:
            trading_service: Service de trading pour injection
            
        Returns:
            Instance ACCUMULATOR ou None
        """
        self.logger.debug("_create_accumulator_strategy called")
        
        try:
            # Créer le service accumulator
            accumulator_service = AccumulatorService(self.binance_client, trading_service)
            
            # Configurer la référence trading service
            if trading_service:
                accumulator_service.set_trading_service_reference(trading_service)
            
            # Créer la stratégie avec le service
            strategy = AccumulatorStrategy(accumulator_service)
            
            self.logger.info("✅ Stratégie ACCUMULATOR créée avec succès")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Erreur création ACCUMULATOR: {e}", exc_info=True)
            return None

    def _create_all_or_nothing_strategy(
        self,
        trading_service: Optional[Any]
    ) -> Optional[AllOrNothingStrategy]:
        """
        Crée une stratégie ALL_OR_NOTHING avec ses services

        Args:
            trading_service: Service de trading pour injection

        Returns:
            Instance ALL_OR_NOTHING ou None
        """
        self.logger.debug("_create_all_or_nothing_strategy called")

        try:
            # Créer le service all or nothing
            all_or_nothing_service = AllOrNothingService(self.binance_client, trading_service)

            # Configurer la référence trading service
            if trading_service:
                all_or_nothing_service.set_trading_service_reference(trading_service)

            # Créer la stratégie avec le service
            strategy = AllOrNothingStrategy(all_or_nothing_service)

            self.logger.info("Stratégie ALL_OR_NOTHING créée avec succès")
            return strategy

        except Exception as e:
            self.logger.error(f"Erreur création ALL_OR_NOTHING: {e}", exc_info=True)
            return None

    def _create_one_or_more_strategy(self) -> Optional[OneOrMoreStrategy]:
        """
        Crée une stratégie ONE_OR_MORE avec ses services

        Returns:
            Instance ONE_OR_MORE ou None
        """
        self.logger.debug("_create_one_or_more_strategy called")

        try:
            # Créer la stratégie avec le binance_client (pas de user_data_manager ici)
            strategy = OneOrMoreStrategy(self.binance_client, None)

            self.logger.info("✅ Stratégie ONE_OR_MORE créée avec succès")
            return strategy

        except Exception as e:
            self.logger.error(f"Erreur création ONE_OR_MORE: {e}", exc_info=True)
            return None

    def get_available_strategies(self) -> list[str]:
        """
        Retourne la liste des stratégies disponibles
        
        Returns:
            Liste des noms de stratégies
        """
        return [strategy.value for strategy in StrategyType]
    
    def validate_strategy_config(self, strategy_type: str) -> bool:
        """
        Valide la configuration pour un type de stratégie
        
        Args:
            strategy_type: Type de stratégie à valider
            
        Returns:
            True si configuration valide, False sinon
        """
        self.logger.debug(f"validate_strategy_config called: {strategy_type}")
        
        try:
            if strategy_type == StrategyType.CASCADE_MASTER.value:
                # Vérifier les configurations requises pour CASCADE_MASTER
                required_configs = [
                    config.HEDGING_CONFIG.get("ENABLED"),
                    config.CASCADE_CONFIG.get("ENABLED"), 
                    config.TP_CONFIG.get("ENABLED")
                ]
                
                if not all(required_configs):
                    self.logger.warning("Configuration CASCADE_MASTER incomplète")
                    return False
                
                self.logger.debug("Configuration CASCADE_MASTER validée")
                return True
            
            elif strategy_type == StrategyType.ACCUMULATOR.value:
                # Vérifier la configuration requise pour ACCUMULATOR
                accumulator_enabled = config.ACCUMULATOR_CONFIG.get("ENABLED")
                tp_percent = config.ACCUMULATOR_CONFIG.get("TP_PERCENT")
                max_accumulations = config.ACCUMULATOR_CONFIG.get("MAX_ACCUMULATIONS")
                
                if not accumulator_enabled or not tp_percent or not max_accumulations:
                    self.logger.warning("Configuration ACCUMULATOR incomplète")
                    return False
                
                self.logger.debug("Configuration ACCUMULATOR validée")
                return True

            elif strategy_type == StrategyType.ALL_OR_NOTHING.value:
                # Vérifier la configuration requise pour ALL_OR_NOTHING
                all_or_nothing_enabled = config.ALL_OR_NOTHING_CONFIG.get("ENABLED")
                sl_lookback = config.ALL_OR_NOTHING_CONFIG.get("SL_LOOKBACK_CANDLES")
                sl_offset = config.ALL_OR_NOTHING_CONFIG.get("SL_OFFSET_PERCENT")
                tp_percent = config.ALL_OR_NOTHING_CONFIG.get("TP_PERCENT")

                if not all_or_nothing_enabled or not sl_lookback or sl_offset is None or not tp_percent:
                    self.logger.warning("Configuration ALL_OR_NOTHING incomplète")
                    return False

                self.logger.debug("Configuration ALL_OR_NOTHING validée")
                return True

            elif strategy_type == StrategyType.ONE_OR_MORE.value:
                # Vérifier la configuration requise pour ONE_OR_MORE
                one_or_more_enabled = config.ONE_OR_MORE_CONFIG.get("ENABLED")
                sl_lookback = config.ONE_OR_MORE_CONFIG.get("SL_LOOKBACK_CANDLES")
                sl_offset = config.ONE_OR_MORE_CONFIG.get("SL_OFFSET_PERCENT")
                hedge_multiplier = config.ONE_OR_MORE_CONFIG.get("HEDGE_QUANTITY_MULTIPLIER")

                if not one_or_more_enabled or not sl_lookback or sl_offset is None or not hedge_multiplier:
                    self.logger.warning("Configuration ONE_OR_MORE incomplète")
                    return False

                self.logger.debug("Configuration ONE_OR_MORE validée")
                return True

            else:
                self.logger.error(f"Type de stratégie inconnu pour validation: {strategy_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur validation config {strategy_type}: {e}", exc_info=True)
            return False
    
    def log_strategy_info(self, strategy: BaseStrategy) -> None:
        """
        Log les informations d'une stratégie
        
        Args:
            strategy: Stratégie à logger
        """
        if strategy:
            self.logger.info(f"📊 Stratégie active: {strategy.get_strategy_name()}")
            self.logger.info(f"   Config: {strategy.get_strategy_config()}")
            # Utiliser la méthode de la stratégie (sans emojis pour Windows)
            strategy.log_strategy_info()
        else:
            self.logger.error("❌ Aucune stratégie fournie pour logging")