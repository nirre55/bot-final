"""
Service de gestion de la stratégie ALL_OR_NOTHING
Responsabilité unique : Gestion des positions avec Stop Loss et Take Profit fixes
"""
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import time

import config
from api.binance_client import BinanceAPIClient
from core.logger import get_module_logger


class AllOrNothingSide(Enum):
    """Côtés des positions All Or Nothing"""
    LONG = "LONG"
    SHORT = "SHORT"


class AllOrNothingService:
    """Service de gestion des positions All Or Nothing avec SL/TP automatiques"""

    def __init__(self, binance_client: BinanceAPIClient, trading_service=None) -> None:
        """Initialise le service All Or Nothing"""
        self.logger = get_module_logger("AllOrNothingService")
        self.binance_client = binance_client
        self.trading_service = trading_service  # Référence pour formatage dynamique

        # Ordres actifs par côté
        self.active_position_long: Optional[Dict[str, Any]] = None  # Position LONG
        self.active_position_short: Optional[Dict[str, Any]] = None  # Position SHORT
        self.active_sl_long: Optional[Dict[str, Any]] = None  # Stop Loss LONG
        self.active_sl_short: Optional[Dict[str, Any]] = None  # Stop Loss SHORT
        self.active_tp_long: Optional[Dict[str, Any]] = None  # Take Profit LONG
        self.active_tp_short: Optional[Dict[str, Any]] = None  # Take Profit SHORT

        # Configuration depuis config
        self.config = config.ALL_OR_NOTHING_CONFIG

        # Cache des informations de formatage pour éviter appels répétés
        self._symbol_precision_cache: Optional[Dict[str, Any]] = None
        self._cached_symbol: Optional[str] = None

        # Historique des bougies pour calcul SL
        self._candle_history: List[Dict[str, float]] = []

        self.logger.debug("AllOrNothingService initialisé")

        # Recovery automatique de l'état existant au démarrage
        self._recover_existing_state()

    def set_trading_service_reference(self, trading_service) -> None:
        """
        Définit la référence au TradingService après initialisation

        Args:
            trading_service: Instance du TradingService pour formatage dynamique
        """
        self.trading_service = trading_service
        self.logger.debug("Référence TradingService définie pour AllOrNothingService")

        # Précharger le cache de précision pour le symbole actuel
        self._cache_symbol_precision()

        # Préremplir l'historique des bougies si possible
        self._prefill_candle_history()

    def update_candle_history(self, candle_data: Dict[str, float]) -> None:
        """
        Met à jour l'historique des bougies pour calcul des SL

        Args:
            candle_data: Données de la bougie fermée (high, low, close, volume)
        """
        self.logger.debug(f"update_candle_history called with candle: {candle_data}")

        # Ajouter la bougie à l'historique
        self._candle_history.append(candle_data)

        # Garder seulement les N dernières bougies selon la configuration
        max_candles = self.config.get("SL_LOOKBACK_CANDLES", 5) + 1  # +1 pour sécurité
        if len(self._candle_history) > max_candles:
            self._candle_history = self._candle_history[-max_candles:]

        self.logger.debug(f"Historique bougies mis à jour: {len(self._candle_history)} bougies")

    def _prefill_candle_history(self) -> None:
        """
        Prérempli l'historique des bougies au démarrage pour permettre le calcul immédiat des SL
        """
        self.logger.debug("_prefill_candle_history called")

        if not self.trading_service:
            self.logger.warning("TradingService non disponible - impossible de préremplir l'historique")
            return

        try:
            # Obtenir le symbole depuis la config globale
            symbol = getattr(config, 'SYMBOL', 'BTCUSDC')
            timeframe = getattr(config, 'TIMEFRAME', '5m')
            lookback_candles = self.config.get("SL_LOOKBACK_CANDLES", 5)

            self.logger.info(f"Préremplissage historique bougies: {lookback_candles} dernières bougies {symbol} {timeframe}")

            # Récupérer les données historiques via market_data
            from api.market_data import MarketDataClient
            market_data = MarketDataClient()
            historical_data = market_data.get_historical_data(
                symbol=symbol,
                interval=timeframe,
                limit=lookback_candles + 1  # +1 pour sécurité
            )

            if historical_data is None or historical_data.empty:
                self.logger.warning("Aucune donnée historique récupérée pour préremplissage")
                return

            # Convertir le DataFrame en format attendu par update_candle_history
            # Exclure la dernière ligne (bougie en cours)
            for _, row in historical_data.iloc[:-1].iterrows():
                candle_data = {
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": float(row['volume'])
                }
                self._candle_history.append(candle_data)

            # Garder seulement le nombre requis
            if len(self._candle_history) > lookback_candles:
                self._candle_history = self._candle_history[-lookback_candles:]

            self.logger.info(f"✅ Historique prérempli: {len(self._candle_history)} bougies disponibles")

        except Exception as e:
            self.logger.error(f"Erreur préremplissage historique bougies: {e}", exc_info=True)

    def _retry_operation(self, operation: Callable[[], bool], operation_name: str, max_attempts: int = 5) -> bool:
        """
        Effectue une opération avec retry automatique

        Args:
            operation: Fonction à exécuter qui retourne bool
            operation_name: Nom de l'opération pour les logs
            max_attempts: Nombre maximum de tentatives

        Returns:
            True si l'opération réussit, False après max_attempts échecs
        """
        for attempt in range(1, max_attempts + 1):
            try:
                self.logger.info(f"Tentative {attempt}/{max_attempts} - {operation_name}")

                if operation():
                    self.logger.info(f"✅ {operation_name} réussi à la tentative {attempt}")
                    return True
                else:
                    self.logger.warning(f"❌ Échec tentative {attempt}/{max_attempts} - {operation_name}")

            except Exception as e:
                self.logger.error(f"❌ Erreur tentative {attempt}/{max_attempts} - {operation_name}: {e}")

            # Délai entre les tentatives (sauf dernière)
            if attempt < max_attempts:
                delay = 2 * attempt  # Délai croissant: 2s, 4s, 6s, 8s
                self.logger.info(f"⏳ Attente {delay}s avant prochaine tentative...")
                time.sleep(delay)

        self.logger.error(f"🚫 ÉCHEC DÉFINITIF {operation_name} après {max_attempts} tentatives")
        return False

    def _calculate_sl_price(self, signal_type: str) -> Optional[float]:
        """
        Calcule le prix du Stop Loss selon le signal et l'historique des bougies

        Args:
            signal_type: "LONG" ou "SHORT"

        Returns:
            Prix du Stop Loss ou None si pas assez d'historique
        """
        self.logger.debug(f"_calculate_sl_price called for {signal_type}")

        lookback_candles = self.config.get("SL_LOOKBACK_CANDLES", 5)
        sl_offset = self.config.get("SL_OFFSET_PERCENT", 0.001)

        if len(self._candle_history) < lookback_candles:
            self.logger.warning(f"Historique insuffisant pour SL: {len(self._candle_history)}/{lookback_candles}")
            return None

        # Prendre les dernières bougies pour le calcul
        recent_candles = self._candle_history[-lookback_candles:]

        if signal_type == "LONG":
            # Pour LONG: SL = LOW minimum - offset
            min_low = min(candle["low"] for candle in recent_candles)
            sl_price = min_low * (1 - sl_offset)
            self.logger.info(f"SL LONG calculé: {sl_price:.6f} (LOW min: {min_low:.6f} - {sl_offset*100}%)")
        else:  # SHORT
            # Pour SHORT: SL = HIGH maximum + offset
            max_high = max(candle["high"] for candle in recent_candles)
            sl_price = max_high * (1 + sl_offset)
            self.logger.info(f"SL SHORT calculé: {sl_price:.6f} (HIGH max: {max_high:.6f} + {sl_offset*100}%)")

        return sl_price

    def _calculate_tp_price(self, entry_price: float, signal_type: str) -> float:
        """
        Calcule le prix du Take Profit selon le prix d'entrée

        Args:
            entry_price: Prix d'entrée de la position
            signal_type: "LONG" ou "SHORT"

        Returns:
            Prix du Take Profit
        """
        self.logger.debug(f"_calculate_tp_price called: {entry_price} for {signal_type}")

        tp_percent = self.config.get("TP_PERCENT", 0.005)  # 0.5% par défaut

        if signal_type == "LONG":
            tp_price = entry_price * (1 + tp_percent)
        else:  # SHORT
            tp_price = entry_price * (1 - tp_percent)

        self.logger.info(f"TP {signal_type} calculé: {tp_price:.6f} ({tp_percent*100}% du prix d'entrée {entry_price:.6f})")
        return tp_price

    def execute_signal(self, signal_type: str, symbol: str) -> bool:
        """
        Exécute un signal All Or Nothing avec création automatique des SL/TP

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole à trader

        Returns:
            True si l'exécution réussit, False sinon
        """
        self.logger.debug(f"execute_signal called: {signal_type} on {symbol}")

        # Vérifier si une position existe déjà pour ce côté
        if signal_type == "LONG" and self.active_position_long:
            self.logger.warning(f"Position LONG déjà active - Signal {signal_type} ignoré")
            return False
        elif signal_type == "SHORT" and self.active_position_short:
            self.logger.warning(f"Position SHORT déjà active - Signal {signal_type} ignoré")
            return False

        try:
            # 1. Calculer le prix SL préliminaire pour estimation de quantité
            preliminary_sl_price = self._calculate_sl_price(signal_type)
            if preliminary_sl_price is None:
                self.logger.error(f"Impossible de calculer le SL préliminaire pour {signal_type}")
                return False

            # 2. Préparer les données pour le calcul de quantité (mode PERCENTAGE)
            # Obtenir le prix actuel approximatif (dernière bougie)
            current_price = None
            if self._candle_history:
                current_price = self._candle_history[-1]["close"]

            signal_data = {
                "signal_type": signal_type.lower(),
                "current_price": current_price,
                "sl_price": preliminary_sl_price  # Prix SL préliminaire pour calcul quantité
            }

            # 3. Exécuter l'ordre d'entrée MARKET
            quantity = self._get_trade_quantity(symbol, signal_data)
            if not quantity:
                self.logger.error(f"Impossible d'obtenir la quantité pour {signal_type}")
                return False

            side = "BUY" if signal_type == "LONG" else "SELL"
            position_side = "LONG" if signal_type == "LONG" else "SHORT"

            self.logger.info(f"🚀 Exécution signal {signal_type}: {side} {quantity} {symbol}")

            entry_order = self.binance_client.place_order(
                symbol=symbol,
                side=side,
                quantity=str(quantity),
                order_type="MARKET",
                position_side=position_side
            )

            if not entry_order:
                self.logger.error(f"Échec ordre d'entrée {signal_type}")
                return False

            # 4. Récupérer le prix d'exécution réel
            entry_price = self._get_order_execution_price(entry_order)
            if not entry_price:
                self.logger.error(f"Impossible de récupérer le prix d'exécution pour {signal_type}")
                return False

            self.logger.info(f"✅ Ordre d'entrée {signal_type} exécuté: {entry_price:.6f}")

            # 5. RECALCULER LE RISQUE avec le prix d'exécution réel
            self.logger.info(f"🔄 Recalcul du risque avec prix d'exécution réel: {entry_price:.6f}")

            # Mettre à jour l'historique avec la bougie courante si nécessaire
            if self._candle_history and current_price:
                # Remplacer la dernière bougie par une version avec le prix d'exécution réel
                self._candle_history[-1]["close"] = entry_price

            # Recalculer le SL avec les données actualisées
            final_sl_price = self._calculate_sl_price(signal_type)
            if final_sl_price is None:
                self.logger.error(f"Impossible de recalculer le SL final pour {signal_type}")
                return False

            if abs(final_sl_price - preliminary_sl_price) > 0.001:  # Plus de 0.1% de différence
                self.logger.info(f"⚠️ SL ajusté: {preliminary_sl_price:.6f} → {final_sl_price:.6f}")

            # Utiliser le SL final pour les ordres
            sl_price = final_sl_price

            # BLOQUER IMMÉDIATEMENT LES SIGNAUX SUIVANTS - Position marquée comme active
            if signal_type == "LONG":
                self.active_position_long = {"status": "creating_sl_tp", "entry_price": entry_price}
            else:
                self.active_position_short = {"status": "creating_sl_tp", "entry_price": entry_price}

            self.logger.debug(f"🔒 Position {signal_type} marquée active - signaux suivants bloqués")

            # 2. Créer le Stop Loss avec retry (5 tentatives max)
            def create_sl_operation() -> bool:
                return self._create_stop_loss(signal_type, symbol, quantity, sl_price)

            sl_success = self._retry_operation(create_sl_operation, f"Création SL {signal_type}")
            if not sl_success:
                self.logger.critical(f"🚫 ÉCHEC CRITIQUE: Impossible de créer SL pour {signal_type} - ARRÊT DU SYSTÈME")
                # Nettoyer la position partiellement créée
                if signal_type == "LONG":
                    self.active_position_long = None
                else:
                    self.active_position_short = None
                raise RuntimeError(f"Échec critique création SL {signal_type} après 5 tentatives")

            # 3. Créer le Take Profit avec retry (5 tentatives max)
            tp_price = self._calculate_tp_price(entry_price, signal_type)

            def create_tp_operation() -> bool:
                return self._create_take_profit(signal_type, symbol, quantity, tp_price)

            tp_success = self._retry_operation(create_tp_operation, f"Création TP {signal_type}")
            if not tp_success:
                self.logger.critical(f"🚫 ÉCHEC CRITIQUE: Impossible de créer TP pour {signal_type} - ARRÊT DU SYSTÈME")
                # Annuler le SL créé avant d'arrêter
                if signal_type == "LONG" and self.active_sl_long:
                    self._cancel_order(self.active_sl_long, "SL LONG")
                    self.active_sl_long = None
                elif signal_type == "SHORT" and self.active_sl_short:
                    self._cancel_order(self.active_sl_short, "SL SHORT")
                    self.active_sl_short = None

                # Nettoyer la position partiellement créée
                if signal_type == "LONG":
                    self.active_position_long = None
                else:
                    self.active_position_short = None
                raise RuntimeError(f"Échec critique création TP {signal_type} après 5 tentatives")

            # 4. Compléter les données de position (déjà marquée active plus tôt)
            complete_position_data = {
                "orderId": entry_order.get("orderId"),
                "symbol": symbol,
                "side": position_side,
                "quantity": quantity,
                "entry_price": entry_price,
                "timestamp": entry_order.get("transactTime"),
                "status": "active"  # Position complètement créée avec SL/TP
            }

            if signal_type == "LONG":
                if self.active_position_long:
                    self.active_position_long.update(complete_position_data)
            else:
                if self.active_position_short:
                    self.active_position_short.update(complete_position_data)

            self.logger.info(f"🎯 Position {signal_type} All Or Nothing créée avec SL/TP")
            return True

        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution signal {signal_type}: {e}", exc_info=True)

            # Nettoyer la position partiellement créée en cas d'erreur
            if signal_type == "LONG":
                self.active_position_long = None
            else:
                self.active_position_short = None

            return False

    def _get_trade_quantity(self, symbol: str, signal_data: Optional[Dict[str, Any]] = None) -> Optional[float]:
        """
        Obtient la quantité de trading formatée selon la configuration

        Args:
            symbol: Symbole à trader
            signal_data: Données du signal (nécessaire pour mode PERCENTAGE)

        Returns:
            Quantité formatée ou None si erreur
        """
        self.logger.debug(f"_get_trade_quantity called for {symbol}")

        try:
            if self.trading_service:
                return self.trading_service.get_initial_trade_quantity(symbol, signal_data)
            else:
                self.logger.warning("TradingService non disponible - utilisation quantité par défaut")
                return 0.001  # Quantité par défaut
        except Exception as e:
            self.logger.error(f"Erreur obtention quantité: {e}", exc_info=True)
            return None

    def _get_order_execution_price(self, order: Dict[str, Any]) -> Optional[float]:
        """
        Récupère le prix d'exécution d'un ordre

        Args:
            order: Données de l'ordre

        Returns:
            Prix d'exécution ou None si non disponible
        """
        self.logger.debug("_get_order_execution_price called")

        try:
            # Utiliser prioritairement get_order_status() comme CASCADE pour fiabilité
            order_id = order.get("orderId")
            symbol = order.get("symbol")

            if order_id and symbol:
                self.logger.info(f"Récupération prix d'exécution via API - Order ID: {order_id}")
                order_status = self.binance_client.get_order_status(symbol, int(order_id))

                if order_status and order_status.get("status") == "FILLED":
                    execution_price = float(order_status.get("avgPrice", "0"))
                    executed_qty = float(order_status.get("executedQty", "0"))

                    self.logger.info(f"✅ Prix ordre récupéré via API: {execution_price}, qty: {executed_qty}")

                    if execution_price > 0.0:
                        return execution_price
                    else:
                        self.logger.warning("avgPrice API = 0.0 - ordre peut-être pas complètement traité")
                else:
                    self.logger.warning(f"Ordre non FILLED ou non trouvé: {order_status.get('status') if order_status else 'None'}")

            # Fallback: vérifier avgPrice dans la réponse initiale
            avg_price = order.get("avgPrice", "0")
            if avg_price and avg_price != "0":
                execution_price = float(avg_price)
                if execution_price > 0.0:
                    self.logger.info(f"Prix d'exécution récupéré (réponse initiale): {execution_price}")
                    return execution_price

            self.logger.error("Prix d'exécution non disponible par aucune méthode")
            return None

        except Exception as e:
            self.logger.error(f"Erreur récupération prix d'exécution: {e}", exc_info=True)
            return None

    def _create_stop_loss(self, signal_type: str, symbol: str, quantity: float, sl_price: float) -> bool:
        """
        Crée un ordre Stop Loss

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole
            quantity: Quantité
            sl_price: Prix du Stop Loss

        Returns:
            True si création réussie, False sinon
        """
        self.logger.debug(f"_create_stop_loss called: {signal_type} SL={sl_price}")

        try:
            # Format du prix selon la précision du symbole
            formatted_sl_price = self._format_price_with_precision(sl_price, symbol)
            if not formatted_sl_price:
                return False

            # Pour LONG: SL = ordre SELL, pour SHORT: SL = ordre BUY
            side = "SELL" if signal_type == "LONG" else "BUY"
            position_side = "LONG" if signal_type == "LONG" else "SHORT"

            sl_order = self.binance_client.place_stop_market_order(
                symbol=symbol,
                side=side,
                quantity=str(quantity),
                stop_price=str(formatted_sl_price),
                position_side=position_side
            )

            if sl_order:
                sl_data = {
                    "orderId": sl_order.get("orderId"),
                    "symbol": symbol,
                    "side": side,
                    "stopPrice": formatted_sl_price,
                    "quantity": quantity
                }

                if signal_type == "LONG":
                    self.active_sl_long = sl_data
                else:
                    self.active_sl_short = sl_data

                self.logger.info(f"🛑 Stop Loss {signal_type} créé: {formatted_sl_price}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Erreur création Stop Loss {signal_type}: {e}", exc_info=True)
            return False

    def _create_take_profit(self, signal_type: str, symbol: str, quantity: float, tp_price: float) -> bool:
        """
        Crée un ordre Take Profit

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole
            quantity: Quantité
            tp_price: Prix du Take Profit

        Returns:
            True si création réussie, False sinon
        """
        self.logger.debug(f"_create_take_profit called: {signal_type} TP={tp_price}")

        try:
            # Format du prix selon la précision du symbole
            formatted_tp_price = self._format_price_with_precision(tp_price, symbol)
            if not formatted_tp_price:
                return False

            # Calculer le prix de déclenchement avec offset
            price_offset = self.config.get("PRICE_OFFSET", 0.001)
            if signal_type == "LONG":
                # LONG TP: trigger en dessous du prix limite
                stop_price = formatted_tp_price * (1 - price_offset)
            else:
                # SHORT TP: trigger au dessus du prix limite
                stop_price = formatted_tp_price * (1 + price_offset)

            formatted_stop_price = self._format_price_with_precision(stop_price, symbol)
            if not formatted_stop_price:
                return False

            # Pour LONG: TP = ordre SELL, pour SHORT: TP = ordre BUY
            side = "SELL" if signal_type == "LONG" else "BUY"
            position_side = "LONG" if signal_type == "LONG" else "SHORT"

            tp_order = self.binance_client.place_take_profit_order(
                symbol=symbol,
                side=side,
                quantity=str(quantity),
                stop_price=str(formatted_stop_price),
                price=str(formatted_tp_price),
                position_side=position_side
            )

            if tp_order:
                tp_data = {
                    "orderId": tp_order.get("orderId"),
                    "symbol": symbol,
                    "side": side,
                    "price": formatted_tp_price,
                    "stopPrice": formatted_stop_price,
                    "quantity": quantity
                }

                if signal_type == "LONG":
                    self.active_tp_long = tp_data
                else:
                    self.active_tp_short = tp_data

                self.logger.info(f"🎯 Take Profit {signal_type} créé: {formatted_tp_price}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Erreur création Take Profit {signal_type}: {e}", exc_info=True)
            return False

    def _format_price_with_precision(self, price: float, symbol: str) -> Optional[float]:
        """
        Formate un prix selon la précision du symbole

        Args:
            price: Prix à formater
            symbol: Symbole pour la précision

        Returns:
            Prix formaté ou None si erreur
        """
        self.logger.debug(f"_format_price_with_precision called: {price} for {symbol}")

        try:
            # Utiliser binance_client.format_price() et convertir en float
            formatted_price_str = self.binance_client.format_price(price, symbol)
            return float(formatted_price_str)
        except Exception as e:
            self.logger.error(f"Erreur formatage prix: {e}", exc_info=True)
            return None

    def _cache_symbol_precision(self) -> None:
        """Cache les informations de précision du symbole actuel"""
        self.logger.debug("_cache_symbol_precision called")
        # Implémentation similaire à AccumulatorService si nécessaire
        pass

    def _recover_existing_state(self) -> None:
        """Récupère l'état existant au démarrage du service"""
        self.logger.debug("_recover_existing_state called")
        self.logger.info("AllOrNothing: Recovery non implémenté (positions simples)")
        # Pour AllOrNothing, on peut laisser la recovery simple car les positions sont temporaires

    def handle_order_execution_from_websocket(self, order_data: Dict[str, Any]) -> None:
        """
        Gère l'exécution d'ordres depuis le WebSocket User Data Stream

        Args:
            order_data: Données d'exécution d'ordre
        """
        self.logger.debug("handle_order_execution_from_websocket called")

        try:
            if order_data.get("X") != "FILLED":
                return  # Seuls les ordres exécutés nous intéressent

            order_id = order_data.get("i")

            # Vérifier si c'est un SL ou TP qui s'est exécuté
            if order_id and self._is_sl_or_tp_executed(str(order_id)):
                self.logger.info(f"🔄 SL/TP All Or Nothing exécuté: {order_id}")
                # Reset de la position concernée
                self._reset_position_for_order(str(order_id))

        except Exception as e:
            self.logger.error(f"Erreur traitement exécution WebSocket: {e}", exc_info=True)

    def _is_sl_or_tp_executed(self, order_id: str) -> bool:
        """
        Vérifie si l'ordre exécuté est un de nos SL/TP

        Args:
            order_id: ID de l'ordre exécuté

        Returns:
            True si c'est un de nos SL/TP
        """
        # Vérifier parmi tous les SL/TP actifs
        all_orders = [
            self.active_sl_long, self.active_sl_short,
            self.active_tp_long, self.active_tp_short
        ]

        for order in all_orders:
            if order and str(order.get("orderId")) == str(order_id):
                return True

        return False

    def _reset_position_for_order(self, order_id: str) -> None:
        """
        Reset de la position concernée par l'ordre exécuté

        Args:
            order_id: ID de l'ordre exécuté
        """
        self.logger.debug(f"_reset_position_for_order called: {order_id}")

        # Reset LONG si SL/TP LONG exécuté
        if ((self.active_sl_long and str(self.active_sl_long.get("orderId")) == str(order_id)) or
            (self.active_tp_long and str(self.active_tp_long.get("orderId")) == str(order_id))):

            self.logger.info("🔄 Reset position LONG All Or Nothing")

            # Annuler l'ordre opposé avant reset
            if self.active_sl_long and str(self.active_sl_long.get("orderId")) == str(order_id) and self.active_tp_long:
                # SL exécuté, annuler TP
                self._cancel_order(self.active_tp_long, "TP LONG")
            elif self.active_tp_long and str(self.active_tp_long.get("orderId")) == str(order_id) and self.active_sl_long:
                # TP exécuté, annuler SL
                self._cancel_order(self.active_sl_long, "SL LONG")

            self.active_position_long = None
            self.active_sl_long = None
            self.active_tp_long = None

        # Reset SHORT si SL/TP SHORT exécuté
        if ((self.active_sl_short and str(self.active_sl_short.get("orderId")) == str(order_id)) or
            (self.active_tp_short and str(self.active_tp_short.get("orderId")) == str(order_id))):

            self.logger.info("🔄 Reset position SHORT All Or Nothing")

            # Annuler l'ordre opposé avant reset
            if self.active_sl_short and str(self.active_sl_short.get("orderId")) == str(order_id) and self.active_tp_short:
                # SL exécuté, annuler TP
                self._cancel_order(self.active_tp_short, "TP SHORT")
            elif self.active_tp_short and str(self.active_tp_short.get("orderId")) == str(order_id) and self.active_sl_short:
                # TP exécuté, annuler SL
                self._cancel_order(self.active_sl_short, "SL SHORT")

            self.active_position_short = None
            self.active_sl_short = None
            self.active_tp_short = None

    def _cancel_order(self, order_data: Dict[str, Any], order_type: str) -> bool:
        """
        Annule un ordre sur Binance

        Args:
            order_data: Données de l'ordre à annuler
            order_type: Type d'ordre pour les logs

        Returns:
            True si annulation réussie, False sinon
        """
        try:
            order_id = order_data.get("orderId")
            symbol = order_data.get("symbol")

            if not order_id or not symbol:
                self.logger.warning(f"Données incomplètes pour annulation {order_type}: {order_data}")
                return False

            self.logger.info(f"🚫 Annulation {order_type}: {order_id}")

            # Utiliser l'API Binance pour annuler l'ordre
            result = self.binance_client.cancel_order(symbol, int(order_id))

            if result:
                self.logger.info(f"✅ {order_type} annulé avec succès: {order_id}")
                return True
            else:
                self.logger.warning(f"❌ Échec annulation {order_type}: {order_id}")
                return False

        except Exception as e:
            self.logger.error(f"Erreur annulation {order_type}: {e}", exc_info=True)
            return False

    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel de la stratégie All Or Nothing

        Returns:
            Dictionnaire avec l'état des positions
        """
        return {
            "strategy": "ALL_OR_NOTHING",
            "long_active": self.active_position_long is not None,
            "short_active": self.active_position_short is not None,
            "long_sl_active": self.active_sl_long is not None,
            "short_sl_active": self.active_sl_short is not None,
            "long_tp_active": self.active_tp_long is not None,
            "short_tp_active": self.active_tp_short is not None,
            "candle_history_size": len(self._candle_history)
        }

    def cleanup(self) -> None:
        """Nettoyage des ressources du service"""
        self.logger.debug("cleanup called")

        # Préserver les ordres SL/TP actifs lors de l'arrêt
        if self.active_sl_long or self.active_tp_long:
            self.logger.info("⚠️ Position LONG All Or Nothing préservée lors de l'arrêt")

        if self.active_sl_short or self.active_tp_short:
            self.logger.info("⚠️ Position SHORT All Or Nothing préservée lors de l'arrêt")

        # Reset des états sans annuler les ordres
        self.active_position_long = None
        self.active_position_short = None
        self.active_sl_long = None
        self.active_sl_short = None
        self.active_tp_long = None
        self.active_tp_short = None

        self.logger.info("AllOrNothingService nettoyé")