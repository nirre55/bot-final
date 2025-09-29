"""
Stratégie ALL_OR_NOTHING - Positions simples avec Stop Loss et Take Profit automatiques
Responsabilité unique : Logique de la stratégie All Or Nothing
"""
from typing import Dict, Any, Optional

import config
from strategies.base_strategy import BaseStrategy
from core.all_or_nothing_service import AllOrNothingService


class AllOrNothingStrategy(BaseStrategy):
    """Implémentation de la stratégie ALL_OR_NOTHING (position simple + SL/TP automatiques)"""

    def __init__(self, all_or_nothing_service: AllOrNothingService) -> None:
        """
        Initialise la stratégie ALL_OR_NOTHING

        Args:
            all_or_nothing_service: Service All Or Nothing injecté
        """
        super().__init__()
        self.all_or_nothing_service = all_or_nothing_service
        self.logger.info("Stratégie ALL_OR_NOTHING initialisée")

    def get_strategy_name(self) -> str:
        """Retourne le nom de la stratégie"""
        return "ALL_OR_NOTHING"

    def should_use_hedge(self) -> bool:
        """Cette stratégie n'utilise pas de hedging (utilise SL à la place)"""
        return False

    def should_use_cascade(self) -> bool:
        """Cette stratégie n'utilise pas le système de cascade"""
        return False

    def should_use_advanced_tp(self) -> bool:
        """Cette stratégie n'utilise pas le système TP avancé (TP simple intégré)"""
        return False

    def execute_signal_strategy(
        self,
        signal_data: Dict[str, Any],
        trading_service: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Exécute la logique ALL_OR_NOTHING pour un signal

        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading pour exécuter les ordres

        Returns:
            Résultat de l'exécution ou None si erreur
        """
        self.logger.info(f"Exécution signal ALL_OR_NOTHING: {signal_data['type']}")

        try:
            signal_type = signal_data.get("type", "").upper()

            if signal_type not in ["LONG", "SHORT"]:
                self.logger.error(f"Type de signal invalide: {signal_type}")
                return None

            # Obtenir le symbole depuis la configuration
            symbol = config.SYMBOL

            # Exécuter le signal avec création automatique des SL/TP
            success = self.all_or_nothing_service.execute_signal(signal_type, symbol)

            if success:
                result = {
                    "strategy": "ALL_OR_NOTHING",
                    "signal_type": signal_type,
                    "symbol": symbol,
                    "status": "executed",
                    "message": f"Position {signal_type} créée avec SL/TP automatiques"
                }

                self.logger.info(f"✅ Signal ALL_OR_NOTHING {signal_type} exécuté avec succès")
                return result
            else:
                self.logger.error(f"❌ Échec exécution signal ALL_OR_NOTHING {signal_type}")
                return None

        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution signal ALL_OR_NOTHING: {e}", exc_info=True)
            return None

    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel de la stratégie

        Returns:
            Dictionnaire avec l'état de la stratégie
        """
        try:
            return self.all_or_nothing_service.get_strategy_status()
        except Exception as e:
            self.logger.error(f"Erreur récupération statut ALL_OR_NOTHING: {e}", exc_info=True)
            return {"strategy": "ALL_OR_NOTHING", "status": "error"}

    def cleanup(self) -> None:
        """Nettoyage des ressources de la stratégie"""
        self.logger.info("Nettoyage stratégie ALL_OR_NOTHING")

        try:
            self.all_or_nothing_service.cleanup()
        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage ALL_OR_NOTHING: {e}", exc_info=True)

        self.logger.info("Stratégie ALL_OR_NOTHING nettoyée")

    def set_trading_service_reference(self, trading_service: Any) -> None:
        """
        Définit la référence au TradingService

        Args:
            trading_service: Instance du TradingService
        """
        self.all_or_nothing_service.set_trading_service_reference(trading_service)
        self.logger.debug("Référence TradingService définie pour ALL_OR_NOTHING")

    def handle_order_execution_from_websocket(self, order_data: Dict[str, Any]) -> None:
        """
        Gère l'exécution d'ordres depuis le WebSocket User Data Stream

        Args:
            order_data: Données d'exécution d'ordre
        """
        try:
            self.all_or_nothing_service.handle_order_execution_from_websocket(order_data)
        except Exception as e:
            self.logger.error(f"Erreur traitement WebSocket ALL_OR_NOTHING: {e}", exc_info=True)

    def update_candle_data(self, candle_data: Dict[str, Any]) -> None:
        """
        Met à jour les données de bougies pour le calcul des SL, monitoring RSI et trailing stop

        Args:
            candle_data: Données de la bougie fermée
        """
        try:
            # Extraire les données nécessaires de la bougie
            candle_info = {
                "high": float(candle_data.get("h", 0)),
                "low": float(candle_data.get("l", 0)),
                "close": float(candle_data.get("c", 0)),
                "volume": float(candle_data.get("v", 0))
            }

            # Prix de fermeture pour monitoring
            close_price = candle_info["close"]

            # Mettre à jour l'historique pour calcul SL
            self.all_or_nothing_service.update_candle_history(candle_info)

            # Vérifier les conditions de sortie RSI dynamique
            self.all_or_nothing_service.process_candle_close_for_dynamic_exit(candle_data)

            # Vérifier les conditions de trailing stop
            self.all_or_nothing_service.process_candle_close_for_trailing_stop(close_price)

        except Exception as e:
            self.logger.error(f"Erreur mise à jour bougies ALL_OR_NOTHING: {e}", exc_info=True)

    def get_strategy_config(self) -> Dict[str, Any]:
        """Retourne la configuration ALL_OR_NOTHING"""
        return {
            "all_or_nothing": config.ALL_OR_NOTHING_CONFIG,
            "dynamic_rsi_exit_enabled": config.ALL_OR_NOTHING_CONFIG.get("DYNAMIC_RSI_EXIT", {}).get("ENABLED", False),
            "trailing_stop_enabled": config.ALL_OR_NOTHING_CONFIG.get("TRAILING_STOP", {}).get("ENABLED", False)
        }