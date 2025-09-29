#!/usr/bin/env python3
"""
Stratégie ONE_OR_MORE
Responsabilité unique : Gestion de position simple avec hedge automatique et TP 1RR
"""

from typing import Dict, Any, Optional
import config
from core.logger import get_module_logger
from strategies.base_strategy import BaseStrategy
from core.one_or_more_service import OneOrMoreService


class OneOrMoreStrategy(BaseStrategy):
    """Stratégie ONE_OR_MORE avec hedge automatique et TP 1RR"""

    def __init__(self, binance_client, user_data_manager) -> None:
        """
        Initialise la stratégie ONE_OR_MORE

        Args:
            binance_client: Client API Binance
            user_data_manager: Gestionnaire User Data Stream
        """
        super().__init__()
        self.logger = get_module_logger(__name__)

        # Service spécialisé pour ONE_OR_MORE
        self.one_or_more_service = OneOrMoreService(
            binance_client,
            config.ONE_OR_MORE_CONFIG
        )

        # Référence pour WebSocket
        self.user_data_manager = user_data_manager
        if user_data_manager:
            user_data_manager.trading_bot_reference = self

        self.logger.info("🎯 OneOrMoreStrategy initialisée avec hedge automatique et TP 1RR")

    def get_strategy_name(self) -> str:
        """Retourne le nom de la stratégie"""
        return "ONE_OR_MORE"

    def get_strategy_config(self) -> Dict[str, Any]:
        """Retourne la configuration de la stratégie"""
        return config.ONE_OR_MORE_CONFIG

    def should_use_hedge(self) -> bool:
        """ONE_OR_MORE utilise un système de hedge automatique"""
        return True

    def should_use_cascade(self) -> bool:
        """ONE_OR_MORE n'utilise pas le système de cascade"""
        return False

    def should_use_advanced_tp(self) -> bool:
        """ONE_OR_MORE utilise un système TP 1RR intégré"""
        return False

    def execute_signal_strategy(self, signal_data: Dict[str, Any], trading_service: Any) -> Optional[Dict[str, Any]]:
        """
        Exécute la logique spécifique ONE_OR_MORE pour un signal

        Args:
            signal_data: Données du signal détecté
            trading_service: Service de trading

        Returns:
            Résultat de l'exécution ou None si erreur
        """
        try:
            signal_type = signal_data.get("type", "").upper()
            symbol = config.SYMBOL  # Utiliser le symbole de la configuration

            if not signal_type:
                self.logger.error("Type de signal manquant pour ONE_OR_MORE")
                return None

            # Déléguer à la méthode execute_signal
            success = self.execute_signal(signal_type, symbol, signal_data)

            if success:
                return {
                    "strategy": "ONE_OR_MORE",
                    "signal_type": signal_type,
                    "symbol": symbol,
                    "status": "executed",
                    "hedge_created": True,
                    "tp_1rr": True
                }
            else:
                return None

        except Exception as e:
            self.logger.error(f"Erreur execute_signal_strategy ONE_OR_MORE: {e}", exc_info=True)
            return None

    def execute_signal(self, signal_type: str, symbol: str, signal_info: Dict[str, Any]) -> bool:
        """
        Exécute un signal de trading avec la stratégie ONE_OR_MORE

        Args:
            signal_type: Type du signal ("LONG" ou "SHORT")
            symbol: Symbole de trading
            signal_info: Informations du signal (RSI, HA, etc.)

        Returns:
            True si l'exécution a réussi, False sinon
        """
        self.logger.info(f"🎯 ONE_OR_MORE: Exécution signal {signal_type} pour {symbol}")

        try:
            # Vérifier si ANY position existe déjà (blocage total pour ONE_OR_MORE)
            if self.one_or_more_service.has_any_active_position():
                active_positions = self.one_or_more_service.get_active_positions()
                self.logger.warning(f"❌ Système ONE_OR_MORE actif - Signal {signal_type} ignoré")
                self.logger.warning(f"   Positions actives: LONG={active_positions['LONG']}, SHORT={active_positions['SHORT']}")
                return False

            # Exécuter le signal via le service
            success = self.one_or_more_service.execute_signal(signal_type, symbol, signal_info)

            if success:
                self.logger.info(f"✅ Signal {signal_type} exécuté avec succès")
            else:
                self.logger.error(f"❌ Échec exécution signal {signal_type}")

            return success

        except Exception as e:
            self.logger.error(f"Erreur exécution signal ONE_OR_MORE: {e}", exc_info=True)
            return False

    def handle_order_execution_from_websocket(self, order_data: Dict[str, Any]) -> None:
        """
        Traite les exécutions d'ordres via WebSocket pour ONE_OR_MORE

        Args:
            order_data: Données de l'ordre exécuté
        """
        try:
            order_status = order_data.get("X")  # Statut ordre
            order_id = order_data.get("i")      # ID ordre

            if order_status == "FILLED":
                self.logger.info(f"🔔 ONE_OR_MORE: Ordre exécuté ID:{order_id}")

                # Déléguer au service pour traitement
                self.one_or_more_service.handle_order_execution_from_websocket(order_data)

        except Exception as e:
            self.logger.error(f"Erreur traitement WebSocket ONE_OR_MORE: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        """
        Retourne le statut de la stratégie ONE_OR_MORE

        Returns:
            Dictionnaire avec le statut actuel
        """
        try:
            return {
                "strategy_type": "ONE_OR_MORE",
                "active_positions": self.one_or_more_service.get_active_positions(),
                "active_orders": self.one_or_more_service.get_active_orders_count(),
                "last_signal": self.one_or_more_service.get_last_signal_info()
            }
        except Exception as e:
            self.logger.error(f"Erreur récupération statut ONE_OR_MORE: {e}", exc_info=True)
            return {"strategy_type": "ONE_OR_MORE", "error": str(e)}

    def cleanup(self) -> None:
        """Nettoyage de la stratégie ONE_OR_MORE"""
        try:
            self.logger.info("🧹 Nettoyage stratégie ONE_OR_MORE...")

            if hasattr(self, 'one_or_more_service'):
                self.one_or_more_service.cleanup()

            self.logger.info("✅ Nettoyage ONE_OR_MORE terminé")

        except Exception as e:
            self.logger.error(f"Erreur nettoyage ONE_OR_MORE: {e}", exc_info=True)

    def update_candle_data(self, candle_data: Dict[str, Any]) -> None:
        """
        Met à jour les données de bougie pour calcul hedge levels

        Args:
            candle_data: Données de la bougie fermée
        """
        try:
            # Extraire les données OHLC pour calcul hedge
            candle_info = {
                "open": float(candle_data.get("o", 0)),
                "high": float(candle_data.get("h", 0)),
                "low": float(candle_data.get("l", 0)),
                "close": float(candle_data.get("c", 0)),
                "volume": float(candle_data.get("v", 0))
            }

            # Mettre à jour l'historique dans le service
            self.one_or_more_service.update_candle_history(candle_info)

        except Exception as e:
            self.logger.error(f"Erreur mise à jour données bougie ONE_OR_MORE: {e}", exc_info=True)

    def process_candle_close(self) -> None:
        """
        Traite la fermeture d'une bougie pour ONE_OR_MORE

        Note: ONE_OR_MORE n'a pas de traitement spécial sur fermeture de bougie
        contrairement à ALL_OR_NOTHING (dynamic RSI, trailing stop)
        """
        # Pas de traitement spécial pour ONE_OR_MORE sur fermeture de bougie
        pass