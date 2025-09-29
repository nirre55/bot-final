#!/usr/bin/env python3
"""
Service OneOrMore
Responsabilité unique : Gestion stratégie ONE_OR_MORE avec hedge automatique et TP 1RR
"""

from typing import Dict, Any, Optional, List
import config
from core.logger import get_module_logger
from core.trading_service import TradingService
from api.market_data import MarketDataClient


class OneOrMoreService:
    """Service pour la stratégie ONE_OR_MORE"""

    def __init__(self, binance_client, config_dict: Dict[str, Any]) -> None:
        """
        Initialise le service ONE_OR_MORE

        Args:
            binance_client: Client API Binance
            config_dict: Configuration de la stratégie
        """
        self.binance_client = binance_client
        self.config = config_dict
        self.logger = get_module_logger(__name__)

        # Service de trading pour les ordres
        self.trading_service = TradingService(binance_client)

        # État des positions et ordres actifs
        self.active_position_long = False
        self.active_position_short = False

        # Ordres actifs (hedge et TP)
        self.active_hedge_long: Optional[Dict[str, Any]] = None    # Hedge pour position LONG
        self.active_hedge_short: Optional[Dict[str, Any]] = None   # Hedge pour position SHORT
        self.active_tp_long: Optional[Dict[str, Any]] = None       # TP pour position LONG
        self.active_tp_short: Optional[Dict[str, Any]] = None      # TP pour position SHORT
        self.active_tp_hedge_long: Optional[Dict[str, Any]] = None  # TP hedge pour position LONG
        self.active_tp_hedge_short: Optional[Dict[str, Any]] = None # TP hedge pour position SHORT

        # Ordres STOP croisés (nouveaux pour 1RR garanti)
        self.active_stop_signal_long: Optional[Dict[str, Any]] = None   # STOP signal LONG (si hedge TP touché)
        self.active_stop_signal_short: Optional[Dict[str, Any]] = None  # STOP signal SHORT (si hedge TP touché)
        self.active_stop_hedge_long: Optional[Dict[str, Any]] = None    # STOP hedge LONG (si signal TP touché)
        self.active_stop_hedge_short: Optional[Dict[str, Any]] = None   # STOP hedge SHORT (si signal TP touché)

        # Informations pour calcul 1RR
        self.signal_price_long: Optional[float] = None
        self.signal_price_short: Optional[float] = None
        self.hedge_price_long: Optional[float] = None
        self.hedge_price_short: Optional[float] = None
        self.distance_long: Optional[float] = None  # Distance pour calcul 1RR LONG
        self.distance_short: Optional[float] = None # Distance pour calcul 1RR SHORT

        # Historique des bougies pour calcul hedge levels
        self._candle_history: List[Dict[str, float]] = []

        # Initialiser l'historique des bougies
        self._initialize_candle_history()

        self.logger.info("🎯 OneOrMoreService initialisé avec hedge automatique et TP 1RR")

    def _initialize_candle_history(self) -> None:
        """Initialise l'historique des bougies au démarrage"""
        try:
            lookback_candles = self.config.get("SL_LOOKBACK_CANDLES", 5)
            market_data_client = MarketDataClient()

            # Récupérer plus de bougies que nécessaire pour avoir un bon historique
            historical_data = market_data_client.get_historical_data(
                config.SYMBOL, config.TIMEFRAME, lookback_candles + 5
            )

            if historical_data is not None and len(historical_data) > 0:
                # Convertir les données en format interne
                for _, row in historical_data.iterrows():
                    candle_info = {
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"])
                    }
                    self._candle_history.append(candle_info)

                # Garder seulement les 20 dernières
                self._candle_history = self._candle_history[-20:]

                self.logger.info(f"✅ Historique bougies initialisé: {len(self._candle_history)} bougies")
            else:
                self.logger.warning("⚠️ Impossible d'initialiser l'historique des bougies")

        except Exception as e:
            self.logger.error(f"Erreur initialisation historique bougies: {e}", exc_info=True)

    def execute_signal(self, signal_type: str, symbol: str, signal_info: Dict[str, Any]) -> bool:
        """
        Exécute un signal avec la logique ONE_OR_MORE

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole de trading
            signal_info: Informations du signal

        Returns:
            True si succès, False sinon
        """
        self.logger.info(f"🎯 Exécution signal ONE_OR_MORE {signal_type} pour {symbol}")

        try:
            # 1. Calculer le niveau hedge (réutilise logique ALL_OR_NOTHING)
            hedge_price = self._calculate_hedge_price(signal_type)
            if not hedge_price:
                self.logger.error("❌ Impossible de calculer le prix hedge")
                return False

            # 2. Obtenir la quantité de trading
            quantity_result = self.trading_service.get_initial_trade_quantity(symbol, signal_info)
            if not quantity_result:
                self.logger.error("❌ Impossible de calculer la quantité")
                return False

            # S'assurer que c'est un float
            if isinstance(quantity_result, dict):
                quantity = float(quantity_result.get("quantity", 0))
            else:
                quantity = float(quantity_result)

            # 3. Exécuter l'ordre signal (MARKET)
            self.logger.info("🔄 Étape 3: Création ordre signal...")
            signal_order = self._execute_signal_order(signal_type, symbol, quantity)
            if not signal_order:
                self.logger.error("❌ Échec étape 3: ordre signal")
                return False

            # Récupérer le prix d'exécution réel via API
            signal_price = self._get_order_execution_price(signal_order)
            if not signal_price:
                self.logger.error("❌ Impossible de récupérer le prix d'exécution réel")
                return False

            self.logger.info(f"✅ Étape 3 OK: Signal exécuté @ {signal_price:.6f}")

            # 4. Créer l'ordre hedge (STOP) avec 2x quantité
            self.logger.info("🔄 Étape 4: Création ordre hedge...")
            hedge_quantity = quantity * self.config.get("HEDGE_QUANTITY_MULTIPLIER", 2)
            hedge_order = self._create_hedge_order(signal_type, symbol, hedge_quantity, hedge_price)
            if not hedge_order:
                self.logger.error("❌ Échec étape 4: ordre hedge")
                return False

            self.logger.info(f"✅ Étape 4 OK: Hedge créé @ {hedge_price}")

            # 5. Calculer distance pour 1RR
            distance = abs(signal_price - hedge_price)
            self.logger.info(f"🔄 Étape 5: Distance calculée = {distance}")

            # 6. Créer TP signal (LIMIT) à 1RR
            self.logger.info("🔄 Étape 6: Création TP signal...")
            tp_signal_price = self._calculate_tp_signal_price(signal_type, signal_price, distance)
            tp_signal_order = self._create_tp_signal_order(signal_type, symbol, quantity, tp_signal_price)
            if not tp_signal_order:
                self.logger.error("❌ Échec étape 6: TP signal")
                return False

            self.logger.info(f"✅ Étape 6 OK: TP signal créé @ {tp_signal_price}")

            # 7. Sauvegarder l'état
            self._save_position_state(signal_type, signal_price, hedge_price, distance,
                                    signal_order, hedge_order, tp_signal_order)

            self.logger.info(f"✅ Signal ONE_OR_MORE {signal_type} exécuté avec succès")
            self.logger.info(f"📊 Signal: {signal_price}, Hedge: {hedge_price}, Distance: {distance}, TP: {tp_signal_price}")

            return True

        except Exception as e:
            self.logger.error(f"Erreur exécution signal ONE_OR_MORE: {e}", exc_info=True)
            return False

    def _calculate_hedge_price(self, signal_type: str) -> Optional[float]:
        """
        Calcule le prix hedge selon la logique CASCADE_MASTER (réutilise code existant)

        Args:
            signal_type: "LONG" ou "SHORT"

        Returns:
            Prix hedge ou None si erreur
        """
        try:
            lookback_candles = self.config.get("SL_LOOKBACK_CANDLES", 5)
            hedge_offset = self.config.get("SL_OFFSET_PERCENT", 0.00001)

            if len(self._candle_history) < lookback_candles:
                self.logger.warning(f"Historique insuffisant pour hedge: {len(self._candle_history)}/{lookback_candles}")
                return None

            # Prendre les dernières bougies
            recent_candles = self._candle_history[-lookback_candles:]

            if signal_type == "LONG":
                # Pour signal LONG: hedge SHORT au niveau support (LOW min - offset)
                min_low = min(candle["low"] for candle in recent_candles)
                hedge_price = min_low * (1 - hedge_offset)
                self.logger.info(f"Hedge LONG calculé: {hedge_price:.6f} (LOW min: {min_low:.6f} - {hedge_offset*100}%)")
            else:  # SHORT
                # Pour signal SHORT: hedge LONG au niveau résistance (HIGH max + offset)
                max_high = max(candle["high"] for candle in recent_candles)
                hedge_price = max_high * (1 + hedge_offset)
                self.logger.info(f"Hedge SHORT calculé: {hedge_price:.6f} (HIGH max: {max_high:.6f} + {hedge_offset*100}%)")

            return hedge_price

        except Exception as e:
            self.logger.error(f"Erreur calcul prix hedge: {e}", exc_info=True)
            return None

    def _execute_signal_order(self, signal_type: str, symbol: str, quantity: float) -> Optional[Dict[str, Any]]:
        """
        Exécute l'ordre signal (MARKET)

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole
            quantity: Quantité

        Returns:
            Informations ordre ou None si erreur
        """
        try:
            side = "BUY" if signal_type == "LONG" else "SELL"
            position_side = signal_type

            self.logger.info(f"📝 Placement ordre signal {side} {quantity} {symbol}")

            order_result = self.binance_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET",
                position_side=position_side
            )

            if order_result:
                self.logger.info(f"✅ Ordre signal placé: {order_result.get('orderId')}")
                return {
                    "orderId": order_result.get("orderId"),
                    "symbol": symbol,  # Ajouter le symbole pour _get_order_execution_price()
                    "price": float(order_result.get("price", 0)),
                    "quantity": quantity,
                    "side": side,
                    "type": "MARKET"
                }
            else:
                self.logger.error("❌ Échec placement ordre signal")
                return None

        except Exception as e:
            self.logger.error(f"Erreur placement ordre signal: {e}", exc_info=True)
            return None

    def _create_hedge_order(self, signal_type: str, symbol: str, quantity: float, hedge_price: float) -> Optional[Dict[str, Any]]:
        """
        Crée l'ordre hedge (STOP_MARKET)

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole
            quantity: Quantité hedge (2x)
            hedge_price: Prix hedge calculé

        Returns:
            Informations ordre hedge ou None si erreur
        """
        try:
            # Pour signal LONG: hedge = SELL SHORT
            # Pour signal SHORT: hedge = BUY LONG
            hedge_side = "SELL" if signal_type == "LONG" else "BUY"
            hedge_position_side = "SHORT" if signal_type == "LONG" else "LONG"

            # Formater le prix selon la précision du symbole
            formatted_price = self._format_price_with_precision(hedge_price, symbol)
            if not formatted_price:
                return None

            self.logger.info(f"📝 Placement hedge {hedge_side} {quantity} {symbol} @ {formatted_price}")

            order_result = self.binance_client.place_stop_market_order(
                symbol=symbol,
                side=hedge_side,
                quantity=quantity,
                stop_price=formatted_price,
                position_side=hedge_position_side
            )

            if order_result:
                self.logger.info(f"🛡️ Ordre hedge placé: {order_result.get('orderId')}")
                return {
                    "orderId": order_result.get("orderId"),
                    "stopPrice": formatted_price,
                    "quantity": quantity,
                    "side": hedge_side,
                    "type": "STOP_MARKET",
                    "positionSide": hedge_position_side
                }
            else:
                self.logger.error("❌ Échec placement ordre hedge")
                return None

        except Exception as e:
            self.logger.error(f"Erreur création ordre hedge: {e}", exc_info=True)
            return None

    def _calculate_tp_signal_price(self, signal_type: str, signal_price: float, distance: float) -> float:
        """
        Calcule le prix TP signal (1RR) avec offset de sécurité et offset pour petites distances

        Args:
            signal_type: "LONG" ou "SHORT"
            signal_price: Prix d'entrée signal
            distance: Distance au hedge

        Returns:
            Prix TP à 1RR avec offsets
        """
        # Offset de sécurité pour éviter déclenchement immédiat (depuis config)
        safety_offset = signal_price * self.config.get("TP_SAFETY_OFFSET_PERCENT", 0.0005)

        # Vérifier si la distance est trop petite (< 0.2% du prix signal)
        min_distance_percent = self.config.get("MIN_DISTANCE_PERCENT", 0.002)
        min_distance_threshold = signal_price * min_distance_percent

        small_distance_offset = 0.0
        if distance < min_distance_threshold:
            # Distance trop petite, ajouter offset supplémentaire
            small_distance_offset_percent = self.config.get("SMALL_DISTANCE_OFFSET_PERCENT", 0.0015)
            small_distance_offset = signal_price * small_distance_offset_percent
            self.logger.info(f"⚡ Distance petite ({distance:.6f} < {min_distance_threshold:.6f}) - Offset supplémentaire: {small_distance_offset:.6f}")

        if signal_type == "LONG":
            # LONG: TP SELL plus haut quand distance petite = signal_price + distance + small_distance_offset - safety_offset
            tp_price = signal_price + distance + small_distance_offset - safety_offset
        else:  # SHORT
            # SHORT: TP BUY plus bas quand distance petite = signal_price - distance - small_distance_offset + safety_offset
            tp_price = signal_price - distance - small_distance_offset + safety_offset

        self.logger.info(f"TP {signal_type} 1RR calculé: {tp_price:.6f} (signal: {signal_price:.6f}, distance: {distance:.6f}, safety: {safety_offset:.6f}, small_dist: {small_distance_offset:.6f})")
        return tp_price

    def _create_tp_signal_order(self, signal_type: str, symbol: str, quantity: float, tp_price: float) -> Optional[Dict[str, Any]]:
        """
        Crée l'ordre TP signal (LIMIT)

        Args:
            signal_type: "LONG" ou "SHORT"
            symbol: Symbole
            quantity: Quantité
            tp_price: Prix TP

        Returns:
            Informations ordre TP ou None si erreur
        """
        try:
            # Pour position LONG: TP = SELL LIMIT
            # Pour position SHORT: TP = BUY LIMIT
            tp_side = "SELL" if signal_type == "LONG" else "BUY"
            tp_position_side = signal_type

            # Formater le prix selon la précision du symbole
            formatted_price = self._format_price_with_precision(tp_price, symbol)
            if not formatted_price:
                return None

            self.logger.info(f"📝 Placement TP signal {tp_side} {quantity} {symbol} @ {formatted_price}")

            # Formater la quantité selon la précision
            formatted_quantity = self._format_quantity_with_precision(quantity, symbol)
            if not formatted_quantity:
                return None

            order_result = self.binance_client.place_take_profit_order(
                symbol=symbol,
                side=tp_side,
                quantity=formatted_quantity,
                stop_price=str(formatted_price),
                price=str(formatted_price),  # Même prix pour stop et limite
                position_side=tp_position_side
            )

            if order_result:
                self.logger.info(f"🎯 TP signal placé: {order_result.get('orderId')}")
                return {
                    "orderId": order_result.get("orderId"),
                    "price": formatted_price,
                    "quantity": quantity,
                    "side": tp_side,
                    "type": "LIMIT",
                    "positionSide": tp_position_side
                }
            else:
                self.logger.error("❌ Échec placement TP signal")
                return None

        except Exception as e:
            self.logger.error(f"Erreur création TP signal: {e}", exc_info=True)
            return None

    def _save_position_state(self, signal_type: str, signal_price: float, hedge_price: float,
                           distance: float, signal_order: Dict[str, Any], hedge_order: Dict[str, Any],
                           tp_order: Dict[str, Any]) -> None:
        """Sauvegarde l'état de la position"""
        if signal_type == "LONG":
            self.active_position_long = True
            self.signal_price_long = signal_price
            self.hedge_price_long = hedge_price
            self.distance_long = distance
            self.active_hedge_long = hedge_order
            self.active_tp_long = tp_order
        else:  # SHORT
            self.active_position_short = True
            self.signal_price_short = signal_price
            self.hedge_price_short = hedge_price
            self.distance_short = distance
            self.active_hedge_short = hedge_order
            self.active_tp_short = tp_order

    def _format_price_with_precision(self, price: float, symbol: str) -> Optional[float]:
        """Formate le prix selon la précision du symbole (réutilise code existant)"""
        try:
            symbol_info = self.binance_client.get_symbol_info(symbol)
            if not symbol_info:
                return None

            # Trouver la précision des prix
            price_precision = 8  # Défaut
            for filter_info in symbol_info.get("filters", []):
                if filter_info.get("filterType") == "PRICE_FILTER":
                    tick_size = float(filter_info.get("tickSize", "0.00000001"))
                    price_precision = len(str(tick_size).split('.')[1].rstrip('0'))
                    break

            formatted_price = round(price, price_precision)
            self.logger.debug(f"Prix formaté: {price} → {formatted_price} (précision: {price_precision})")
            return formatted_price

        except Exception as e:
            self.logger.error(f"Erreur formatage prix: {e}", exc_info=True)
            return None

    def _format_quantity_with_precision(self, quantity: float, symbol: str) -> Optional[str]:
        """Formate la quantité selon la précision du symbole"""
        try:
            symbol_info = self.binance_client.get_symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Impossible de récupérer les infos du symbole {symbol}")
                return None

            # Récupérer step_size depuis les filtres
            step_size = None
            for filter_item in symbol_info.get('filters', []):
                if filter_item.get('filterType') == 'LOT_SIZE':
                    step_size = float(filter_item.get('stepSize', '0.001'))
                    break

            if step_size is None:
                self.logger.error(f"Impossible de trouver stepSize pour {symbol}")
                return None

            # Utiliser la méthode du trading service
            formatted_quantity = self.trading_service._format_quantity(quantity, step_size)
            self.logger.debug(f"Quantité formatée: {quantity} → {formatted_quantity}")
            return formatted_quantity

        except Exception as e:
            self.logger.error(f"Erreur formatage quantité: {e}", exc_info=True)
            return None

    def handle_order_execution_from_websocket(self, order_data: Dict[str, Any]) -> None:
        """
        Traite les exécutions d'ordres via WebSocket

        Args:
            order_data: Données ordre WebSocket
        """
        try:
            order_status = order_data.get("X")  # Status
            order_id = str(order_data.get("i", ""))  # ID

            if order_status != "FILLED":
                return

            self.logger.info(f"🔔 ONE_OR_MORE WebSocket: Ordre {order_id} exécuté")

            # Identifier le type d'ordre exécuté
            if self._is_hedge_order(order_id):
                self._handle_hedge_execution(order_data)
            elif self._is_tp_signal_order(order_id):
                self._handle_tp_signal_execution(order_data)
            elif self._is_tp_hedge_order(order_id):
                self._handle_tp_hedge_execution(order_data)
            elif self._is_stop_signal_order(order_id):
                self._handle_stop_signal_execution(order_data)
            elif self._is_stop_hedge_order(order_id):
                self._handle_stop_hedge_execution(order_data)

        except Exception as e:
            self.logger.error(f"Erreur traitement WebSocket ONE_OR_MORE: {e}", exc_info=True)

    def _is_hedge_order(self, order_id: str) -> bool:
        """Vérifie si l'ordre est un hedge"""
        hedge_long_match = (self.active_hedge_long and
                           str(self.active_hedge_long.get("orderId", "")) == order_id)
        hedge_short_match = (self.active_hedge_short and
                            str(self.active_hedge_short.get("orderId", "")) == order_id)
        return bool(hedge_long_match or hedge_short_match)

    def _is_tp_signal_order(self, order_id: str) -> bool:
        """Vérifie si l'ordre est un TP signal"""
        tp_long_match = (self.active_tp_long and
                        str(self.active_tp_long.get("orderId", "")) == order_id)
        tp_short_match = (self.active_tp_short and
                         str(self.active_tp_short.get("orderId", "")) == order_id)
        return bool(tp_long_match or tp_short_match)

    def _is_tp_hedge_order(self, order_id: str) -> bool:
        """Vérifie si l'ordre est un TP hedge"""
        tp_hedge_long_match = (self.active_tp_hedge_long and
                              str(self.active_tp_hedge_long.get("orderId", "")) == order_id)
        tp_hedge_short_match = (self.active_tp_hedge_short and
                               str(self.active_tp_hedge_short.get("orderId", "")) == order_id)
        return bool(tp_hedge_long_match or tp_hedge_short_match)

    def _is_stop_signal_order(self, order_id: str) -> bool:
        """Vérifie si l'ordre est un STOP signal"""
        stop_signal_long_match = (self.active_stop_signal_long and
                                 str(self.active_stop_signal_long.get("orderId", "")) == order_id)
        stop_signal_short_match = (self.active_stop_signal_short and
                                  str(self.active_stop_signal_short.get("orderId", "")) == order_id)
        return bool(stop_signal_long_match or stop_signal_short_match)

    def _is_stop_hedge_order(self, order_id: str) -> bool:
        """Vérifie si l'ordre est un STOP hedge"""
        stop_hedge_long_match = (self.active_stop_hedge_long and
                                str(self.active_stop_hedge_long.get("orderId", "")) == order_id)
        stop_hedge_short_match = (self.active_stop_hedge_short and
                                 str(self.active_stop_hedge_short.get("orderId", "")) == order_id)
        return bool(stop_hedge_long_match or stop_hedge_short_match)

    def _handle_hedge_execution(self, order_data: Dict[str, Any]) -> None:
        """Traite l'exécution d'un ordre hedge"""
        try:
            order_id = str(order_data.get("i", ""))

            # Déterminer le côté
            if self.active_hedge_long and str(self.active_hedge_long.get("orderId")) == order_id:
                position_side = "LONG"
                distance = self.distance_long
                hedge_price = self.hedge_price_long
            elif self.active_hedge_short and str(self.active_hedge_short.get("orderId")) == order_id:
                position_side = "SHORT"
                distance = self.distance_short
                hedge_price = self.hedge_price_short
            else:
                self.logger.warning(f"Hedge order {order_id} non trouvé")
                return

            # Vérifier que les données nécessaires sont disponibles
            if distance is None or hedge_price is None:
                self.logger.error(f"Données manquantes pour TP hedge {position_side}: distance={distance}, hedge_price={hedge_price}")
                return

            self.logger.info(f"🛡️ Hedge {position_side} exécuté - Création TP hedge")

            # Créer TP hedge (1RR depuis hedge_price)
            symbol = order_data.get("s", config.SYMBOL)
            hedge_quantity = float(order_data.get("z", 0))  # Quantité exécutée

            self._create_tp_hedge_order(position_side, symbol, hedge_quantity, hedge_price, distance)

            self.logger.info(f"✅ TP hedge {position_side} créé - Système prêt")

        except Exception as e:
            self.logger.error(f"Erreur traitement hedge execution: {e}", exc_info=True)

    def _create_tp_hedge_order(self, position_side: str, symbol: str, quantity: float,
                              hedge_price: float, distance: float) -> None:
        """Crée l'ordre TP hedge après exécution hedge"""
        try:
            # Calculer prix TP hedge (1RR depuis hedge_price) avec offset de sécurité
            safety_offset = hedge_price * self.config.get("TP_SAFETY_OFFSET_PERCENT", 0.0005)

            # Vérifier si la distance est trop petite (< 0.2% du prix hedge)
            min_distance_percent = self.config.get("MIN_DISTANCE_PERCENT", 0.002)
            min_distance_threshold = hedge_price * min_distance_percent

            small_distance_offset = 0.0
            if distance < min_distance_threshold:
                # Distance trop petite, ajouter offset supplémentaire (calculé sur prix hedge)
                small_distance_offset_percent = self.config.get("SMALL_DISTANCE_OFFSET_PERCENT", 0.0015)
                small_distance_offset = hedge_price * small_distance_offset_percent
                self.logger.info(f"⚡ Distance petite hedge ({distance:.6f} < {min_distance_threshold:.6f}) - Offset supplémentaire: {small_distance_offset:.6f}")

            if position_side == "LONG":
                # Signal LONG → Hedge SHORT, TP hedge BUY plus bas quand distance petite
                tp_hedge_price = hedge_price - distance - small_distance_offset + safety_offset
                tp_side = "BUY"
                tp_position_side = "SHORT"  # Fermer la position SHORT du hedge
            else:  # SHORT
                # Signal SHORT → Hedge LONG, TP hedge SELL plus haut quand distance petite
                tp_hedge_price = hedge_price + distance + small_distance_offset - safety_offset
                tp_side = "SELL"
                tp_position_side = "LONG"  # Fermer la position LONG du hedge

            self.logger.info(f"TP hedge {position_side} calculé: {tp_hedge_price:.6f} (hedge: {hedge_price:.6f}, distance: {distance:.6f}, safety: {safety_offset:.6f}, small_dist: {small_distance_offset:.6f})")

            # Formater le prix
            formatted_price = self._format_price_with_precision(tp_hedge_price, symbol)
            if not formatted_price:
                return

            self.logger.info(f"📝 Création TP hedge {tp_side} {quantity} {symbol} @ {formatted_price}")

            order_result = self.binance_client.place_take_profit_order(
                symbol=symbol,
                side=tp_side,
                quantity=quantity,
                stop_price=str(formatted_price),
                price=str(formatted_price),  # Même prix pour stop et limite
                position_side=tp_position_side
            )

            if order_result:
                tp_hedge_info = {
                    "orderId": order_result.get("orderId"),
                    "price": formatted_price,
                    "quantity": quantity,
                    "side": tp_side,
                    "type": "LIMIT",
                    "positionSide": tp_position_side
                }

                # Sauvegarder TP hedge
                if position_side == "LONG":
                    self.active_tp_hedge_long = tp_hedge_info
                else:
                    self.active_tp_hedge_short = tp_hedge_info

                self.logger.info(f"🎯 TP hedge {position_side} créé: {order_result.get('orderId')}")

        except Exception as e:
            self.logger.error(f"Erreur création TP hedge: {e}", exc_info=True)

    def _create_cross_stop_orders(self, hedge_position_side: str) -> None:
        """Crée les ordres STOP croisés pour garantir 1RR"""
        try:
            symbol = config.SYMBOL
            self.logger.info(f"📝 Création ordres STOP croisés pour hedge {hedge_position_side}")

            # Debug: Vérifier l'état des variables
            self.logger.debug(f"État variables - signal_price_long: {getattr(self, 'signal_price_long', 'None')}")
            self.logger.debug(f"État variables - signal_price_short: {getattr(self, 'signal_price_short', 'None')}")
            self.logger.debug(f"État variables - distance_long: {getattr(self, 'distance_long', 'None')}")
            self.logger.debug(f"État variables - distance_short: {getattr(self, 'distance_short', 'None')}")

            # Obtenir les prix TP pour les ordres STOP
            if hedge_position_side == "LONG":
                # Vérifier que les données sont disponibles
                if (self.signal_price_short is None or self.distance_short is None or
                    self.hedge_price_long is None or self.distance_long is None):
                    self.logger.error("Données manquantes pour calcul STOP - hedge LONG")
                    return

                # Hedge LONG exécuté - créer STOP pour fermer signal SHORT et hedge LONG
                signal_tp_price = self.signal_price_short + self.distance_short  # Prix TP du signal SHORT
                hedge_tp_price = self.hedge_price_long - self.distance_long     # Prix TP du hedge LONG

                signal_quantity = self._get_position_quantity("SHORT")
                hedge_quantity = self._get_position_quantity("LONG")

            else:  # SHORT
                # Vérifier que les données sont disponibles
                if (self.signal_price_long is None or self.distance_long is None or
                    self.hedge_price_short is None or self.distance_short is None):
                    self.logger.error("Données manquantes pour calcul STOP - hedge SHORT")
                    return

                # Hedge SHORT exécuté - créer STOP pour fermer signal LONG et hedge SHORT
                signal_tp_price = self.signal_price_long - self.distance_long   # Prix TP du signal LONG
                hedge_tp_price = self.hedge_price_short + self.distance_short   # Prix TP du hedge SHORT

                signal_quantity = self._get_position_quantity("LONG")
                hedge_quantity = self._get_position_quantity("SHORT")

            # Créer STOP pour fermer position signal au prix TP hedge
            stop_signal_order = self._create_stop_order(
                position_side="SHORT" if hedge_position_side == "LONG" else "LONG",
                quantity=signal_quantity,
                stop_price=hedge_tp_price,
                symbol=symbol
            )

            # Créer STOP pour fermer position hedge au prix TP signal
            stop_hedge_order = self._create_stop_order(
                position_side=hedge_position_side,
                quantity=hedge_quantity,
                stop_price=signal_tp_price,
                symbol=symbol
            )

            # Sauvegarder les ordres STOP
            if hedge_position_side == "LONG":
                self.active_stop_signal_short = stop_signal_order
                self.active_stop_hedge_long = stop_hedge_order
            else:
                self.active_stop_signal_long = stop_signal_order
                self.active_stop_hedge_short = stop_hedge_order

            if stop_signal_order and stop_hedge_order:
                self.logger.info(f"✅ Ordres STOP croisés créés pour hedge {hedge_position_side}")
            else:
                self.logger.error(f"❌ Échec création ordres STOP croisés")

        except Exception as e:
            self.logger.error(f"Erreur création ordres STOP croisés: {e}", exc_info=True)

    def _create_stop_order(self, position_side: str, quantity: float, stop_price: float, symbol: str) -> Optional[Dict[str, Any]]:
        """Crée un ordre STOP_MARKET pour fermer une position"""
        try:
            # Déterminer le côté de l'ordre (opposé à la position)
            side = "SELL" if position_side == "LONG" else "BUY"

            # Formater le prix selon la précision
            formatted_stop_price = self._format_price_with_precision(stop_price, symbol)
            if not formatted_stop_price:
                return None

            # Formater la quantité
            formatted_quantity = self._format_quantity_with_precision(quantity, symbol)
            if not formatted_quantity:
                return None

            self.logger.info(f"📝 Placement STOP {side} {formatted_quantity} {symbol} @ {formatted_stop_price}")

            order_result = self.binance_client.place_stop_market_order(
                symbol=symbol,
                side=side,
                quantity=formatted_quantity,
                stop_price=formatted_stop_price,
                position_side=position_side
            )

            if order_result:
                self.logger.info(f"🛑 STOP placé: {order_result.get('orderId')}")
                return {
                    "orderId": order_result.get("orderId"),
                    "stopPrice": formatted_stop_price,
                    "quantity": formatted_quantity,
                    "side": side,
                    "type": "STOP_MARKET",
                    "positionSide": position_side
                }
            else:
                self.logger.error("❌ Échec placement ordre STOP")
                return None

        except Exception as e:
            self.logger.error(f"Erreur création ordre STOP: {e}", exc_info=True)
            return None

    def _get_position_quantity(self, position_side: str) -> float:
        """Récupère la quantité d'une position via l'API Binance"""
        try:
            positions = self.binance_client.get_position_info(config.SYMBOL)
            if not positions:
                return 0.0

            for position in positions:
                if position.get("positionSide") == position_side:
                    position_amt = float(position.get("positionAmt", 0))
                    return abs(position_amt)  # Retourner valeur absolue

            return 0.0

        except Exception as e:
            self.logger.error(f"Erreur récupération quantité position {position_side}: {e}", exc_info=True)
            return 0.0

    def _handle_tp_signal_execution(self, order_data: Dict[str, Any]) -> None:
        """Traite l'exécution d'un TP signal - Reset système"""
        try:
            order_id = str(order_data.get("i", ""))

            # Déterminer le côté
            if self.active_tp_long and str(self.active_tp_long.get("orderId")) == order_id:
                position_side = "LONG"
            elif self.active_tp_short and str(self.active_tp_short.get("orderId")) == order_id:
                position_side = "SHORT"
            else:
                self.logger.warning(f"TP signal {order_id} non trouvé")
                return

            self.logger.info(f"🎯 TP signal {position_side} exécuté - FERMETURE COMPLÈTE système")

            # Fermer TOUTES les positions et ordres selon workflow
            self._close_all_positions_and_orders()

        except Exception as e:
            self.logger.error(f"Erreur traitement TP signal: {e}", exc_info=True)

    def _handle_tp_hedge_execution(self, order_data: Dict[str, Any]) -> None:
        """Traite l'exécution d'un TP hedge - Reset système"""
        try:
            order_id = str(order_data.get("i", ""))

            # Déterminer le côté
            if self.active_tp_hedge_long and str(self.active_tp_hedge_long.get("orderId")) == order_id:
                position_side = "LONG"
            elif self.active_tp_hedge_short and str(self.active_tp_hedge_short.get("orderId")) == order_id:
                position_side = "SHORT"
            else:
                self.logger.warning(f"TP hedge {order_id} non trouvé")
                return

            self.logger.info(f"🎯 TP hedge {position_side} exécuté - FERMETURE COMPLÈTE système")

            # Fermer TOUTES les positions et ordres selon workflow
            self._close_all_positions_and_orders()

        except Exception as e:
            self.logger.error(f"Erreur traitement TP hedge: {e}", exc_info=True)

    def _close_all_positions_and_orders(self) -> None:
        """Ferme toutes les positions et annule tous les ordres en attente"""
        try:
            self.logger.info("🧹 FERMETURE COMPLÈTE - Annulation de tous les ordres...")

            # Annuler tous les ordres en attente
            self._cancel_order_if_exists(self.active_hedge_long)
            self._cancel_order_if_exists(self.active_hedge_short)
            self._cancel_order_if_exists(self.active_tp_long)
            self._cancel_order_if_exists(self.active_tp_short)
            self._cancel_order_if_exists(self.active_tp_hedge_long)
            self._cancel_order_if_exists(self.active_tp_hedge_short)

            # Fermer toutes les positions ouvertes avec ordres MARKET
            self._close_open_positions()

            # Reset complet de l'état
            self._reset_all_state()

            self.logger.info("✅ FERMETURE COMPLÈTE terminée - Système prêt pour nouveau signal")

        except Exception as e:
            self.logger.error(f"Erreur fermeture complète: {e}", exc_info=True)

    def _close_open_positions(self) -> None:
        """Ferme toutes les positions ouvertes avec des ordres MARKET"""
        try:
            symbol = config.SYMBOL
            positions = self.binance_client.get_position_info(symbol)

            if not positions:
                self.logger.debug("Aucune position à fermer")
                return

            for position in positions:
                position_side = position.get("positionSide")
                position_amt = float(position.get("positionAmt", 0))

                if abs(position_amt) > 0:
                    # Déterminer le côté de fermeture (opposé à la position)
                    close_side = "SELL" if position_amt > 0 else "BUY"
                    close_quantity = abs(position_amt)

                    # Formater la quantité
                    formatted_quantity = self._format_quantity_with_precision(close_quantity, symbol)
                    if formatted_quantity:
                        self.logger.info(f"🔄 Fermeture position {position_side}: {close_side} {formatted_quantity}")

                        # Ordre MARKET pour fermeture immédiate
                        close_result = self.binance_client.place_order(
                            symbol=symbol,
                            side=close_side,
                            quantity=formatted_quantity,
                            order_type="MARKET",
                            position_side=position_side
                        )

                        if close_result:
                            self.logger.info(f"✅ Position {position_side} fermée: {close_result.get('orderId')}")
                        else:
                            self.logger.error(f"❌ Échec fermeture position {position_side}")

        except Exception as e:
            self.logger.error(f"Erreur fermeture positions: {e}", exc_info=True)

    def _reset_all_state(self) -> None:
        """Reset complet de tout l'état du service"""
        try:
            # Reset positions
            self.active_position_long = False
            self.active_position_short = False

            # Reset ordres
            self.active_hedge_long = None
            self.active_hedge_short = None
            self.active_tp_long = None
            self.active_tp_short = None
            self.active_tp_hedge_long = None
            self.active_tp_hedge_short = None

            # Reset prix et distances
            self.signal_price_long = None
            self.signal_price_short = None
            self.hedge_price_long = None
            self.hedge_price_short = None
            self.distance_long = None
            self.distance_short = None

            self.logger.debug("État ONE_OR_MORE complètement réinitialisé")

        except Exception as e:
            self.logger.error(f"Erreur reset état: {e}", exc_info=True)

    def _handle_stop_signal_execution(self, order_data: Dict[str, Any]) -> None:
        """Traite l'exécution d'un ordre STOP signal - 1RR atteint"""
        try:
            order_id = str(order_data.get("i", ""))

            # Déterminer le côté
            if self.active_stop_signal_long and str(self.active_stop_signal_long.get("orderId")) == order_id:
                position_side = "LONG"
                opposite_side = "SHORT"
            elif self.active_stop_signal_short and str(self.active_stop_signal_short.get("orderId")) == order_id:
                position_side = "SHORT"
                opposite_side = "LONG"
            else:
                self.logger.warning(f"STOP signal {order_id} non trouvé")
                return

            self.logger.info(f"🛑 STOP signal {position_side} exécuté - Position signal fermée au prix TP hedge (1RR)")

            # Reset complet du côté de la position signal fermée
            self._reset_position_side(position_side)

            # Annuler les ordres STOP croisés restants pour l'autre côté
            self._cancel_cross_stop_orders(opposite_side)

        except Exception as e:
            self.logger.error(f"Erreur traitement STOP signal: {e}", exc_info=True)

    def _handle_stop_hedge_execution(self, order_data: Dict[str, Any]) -> None:
        """Traite l'exécution d'un ordre STOP hedge - 1RR atteint"""
        try:
            order_id = str(order_data.get("i", ""))

            # Déterminer le côté
            if self.active_stop_hedge_long and str(self.active_stop_hedge_long.get("orderId")) == order_id:
                position_side = "LONG"
                opposite_side = "SHORT"
            elif self.active_stop_hedge_short and str(self.active_stop_hedge_short.get("orderId")) == order_id:
                position_side = "SHORT"
                opposite_side = "LONG"
            else:
                self.logger.warning(f"STOP hedge {order_id} non trouvé")
                return

            self.logger.info(f"🛑 STOP hedge {position_side} exécuté - Position hedge fermée au prix TP signal (1RR)")

            # Reset complet du côté de la position hedge fermée
            self._reset_position_side(position_side)

            # Annuler les ordres STOP croisés restants pour l'autre côté
            self._cancel_cross_stop_orders(opposite_side)

        except Exception as e:
            self.logger.error(f"Erreur traitement STOP hedge: {e}", exc_info=True)

    def _cancel_cross_stop_orders(self, position_side: str) -> None:
        """Annule les ordres STOP croisés pour un côté donné"""
        try:
            if position_side == "LONG":
                self._cancel_order_if_exists(self.active_stop_signal_long)
                self._cancel_order_if_exists(self.active_stop_hedge_long)
                self.active_stop_signal_long = None
                self.active_stop_hedge_long = None
            else:  # SHORT
                self._cancel_order_if_exists(self.active_stop_signal_short)
                self._cancel_order_if_exists(self.active_stop_hedge_short)
                self.active_stop_signal_short = None
                self.active_stop_hedge_short = None

            self.logger.info(f"✅ Ordres STOP croisés {position_side} annulés")

        except Exception as e:
            self.logger.error(f"Erreur annulation ordres STOP croisés {position_side}: {e}", exc_info=True)

    def _reset_position_side(self, position_side: str) -> None:
        """Reset complet d'un côté de position"""
        try:
            self.logger.info(f"🔄 Reset position {position_side}")

            if position_side == "LONG":
                # Annuler ordres restants
                self._cancel_order_if_exists(self.active_hedge_long)
                self._cancel_order_if_exists(self.active_tp_hedge_long)
                self._cancel_order_if_exists(self.active_stop_signal_long)
                self._cancel_order_if_exists(self.active_stop_hedge_long)

                # Reset état
                self.active_position_long = False
                self.active_hedge_long = None
                self.active_tp_long = None
                self.active_tp_hedge_long = None
                self.active_stop_signal_long = None
                self.active_stop_hedge_long = None
                self.signal_price_long = None
                self.hedge_price_long = None
                self.distance_long = None

            else:  # SHORT
                # Annuler ordres restants
                self._cancel_order_if_exists(self.active_hedge_short)
                self._cancel_order_if_exists(self.active_tp_hedge_short)
                self._cancel_order_if_exists(self.active_stop_signal_short)
                self._cancel_order_if_exists(self.active_stop_hedge_short)

                # Reset état
                self.active_position_short = False
                self.active_hedge_short = None
                self.active_tp_short = None
                self.active_tp_hedge_short = None
                self.active_stop_signal_short = None
                self.active_stop_hedge_short = None
                self.signal_price_short = None
                self.hedge_price_short = None
                self.distance_short = None

            self.logger.info(f"✅ Reset {position_side} terminé")

        except Exception as e:
            self.logger.error(f"Erreur reset position {position_side}: {e}", exc_info=True)

    def _cancel_order_if_exists(self, order_info: Optional[Dict[str, Any]]) -> None:
        """Annule un ordre s'il existe"""
        if not order_info:
            return

        try:
            order_id = order_info.get("orderId")
            if order_id:
                symbol = config.SYMBOL
                # cancel_order peut retourner différents types, on ignore le retour
                cancel_result = self.binance_client.cancel_order(symbol, order_id)
                self.logger.info(f"🚫 Ordre {order_id} annulé")

        except Exception as e:
            self.logger.debug(f"Erreur annulation ordre {order_id}: {e}")

    def update_candle_history(self, candle_data: Dict[str, float]) -> None:
        """Met à jour l'historique des bougies pour calcul hedge"""
        try:
            self._candle_history.append(candle_data)

            # Garder seulement les 20 dernières bougies (plus que nécessaire)
            max_history = 20
            if len(self._candle_history) > max_history:
                self._candle_history = self._candle_history[-max_history:]

        except Exception as e:
            self.logger.error(f"Erreur mise à jour historique bougies: {e}", exc_info=True)

    def _get_order_execution_price(self, order: Dict[str, Any]) -> Optional[float]:
        """
        Récupère le prix d'exécution réel d'un ordre

        Args:
            order: Données de l'ordre

        Returns:
            Prix d'exécution ou None si non disponible
        """
        self.logger.debug("_get_order_execution_price called")

        try:
            # Utiliser prioritairement get_order_status() comme ALL_OR_NOTHING pour fiabilité
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

    def has_active_position(self, position_side: str) -> bool:
        """Vérifie si une position est active pour un côté"""
        if position_side == "LONG":
            return self.active_position_long
        else:
            return self.active_position_short

    def has_any_active_position(self) -> bool:
        """Vérifie si ANY position est active (LONG ou SHORT) - Blocage total pour ONE_OR_MORE"""
        return self.active_position_long or self.active_position_short

    def get_active_positions(self) -> Dict[str, bool]:
        """Retourne l'état des positions actives"""
        return {
            "LONG": self.active_position_long,
            "SHORT": self.active_position_short
        }

    def get_active_orders_count(self) -> int:
        """Retourne le nombre d'ordres actifs"""
        count = 0
        for order in [self.active_hedge_long, self.active_hedge_short,
                     self.active_tp_long, self.active_tp_short,
                     self.active_tp_hedge_long, self.active_tp_hedge_short,
                     self.active_stop_signal_long, self.active_stop_signal_short,
                     self.active_stop_hedge_long, self.active_stop_hedge_short]:
            if order:
                count += 1
        return count

    def get_last_signal_info(self) -> Dict[str, Any]:
        """Retourne les informations du dernier signal"""
        return {
            "signal_prices": {
                "LONG": self.signal_price_long,
                "SHORT": self.signal_price_short
            },
            "hedge_prices": {
                "LONG": self.hedge_price_long,
                "SHORT": self.hedge_price_short
            },
            "distances": {
                "LONG": self.distance_long,
                "SHORT": self.distance_short
            }
        }

    def cleanup(self) -> None:
        """Nettoyage du service (préserve ordres actifs comme ACCUMULATOR)"""
        try:
            self.logger.info("🧹 Nettoyage OneOrMoreService...")

            # Préserver les ordres actifs (hedge + TP + STOP) pour continuité
            if self.active_hedge_long:
                self.logger.info(f"⚠️ Hedge LONG préservé: {self.active_hedge_long.get('orderId')}")
            if self.active_hedge_short:
                self.logger.info(f"⚠️ Hedge SHORT préservé: {self.active_hedge_short.get('orderId')}")
            if self.active_tp_long:
                self.logger.info(f"⚠️ TP LONG préservé: {self.active_tp_long.get('orderId')}")
            if self.active_tp_short:
                self.logger.info(f"⚠️ TP SHORT préservé: {self.active_tp_short.get('orderId')}")
            if self.active_tp_hedge_long:
                self.logger.info(f"⚠️ TP Hedge LONG préservé: {self.active_tp_hedge_long.get('orderId')}")
            if self.active_tp_hedge_short:
                self.logger.info(f"⚠️ TP Hedge SHORT préservé: {self.active_tp_hedge_short.get('orderId')}")
            if self.active_stop_signal_long:
                self.logger.info(f"⚠️ STOP Signal LONG préservé: {self.active_stop_signal_long.get('orderId')}")
            if self.active_stop_signal_short:
                self.logger.info(f"⚠️ STOP Signal SHORT préservé: {self.active_stop_signal_short.get('orderId')}")
            if self.active_stop_hedge_long:
                self.logger.info(f"⚠️ STOP Hedge LONG préservé: {self.active_stop_hedge_long.get('orderId')}")
            if self.active_stop_hedge_short:
                self.logger.info(f"⚠️ STOP Hedge SHORT préservé: {self.active_stop_hedge_short.get('orderId')}")

            self.logger.info("✅ Nettoyage OneOrMoreService terminé")

        except Exception as e:
            self.logger.error(f"Erreur nettoyage OneOrMoreService: {e}", exc_info=True)