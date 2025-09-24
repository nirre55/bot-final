"""
Service d'exécution de trading
Responsabilité unique : Gestion de l'exécution des trades
"""
from typing import Dict, Optional, Any
from decimal import Decimal, ROUND_DOWN

import config
from api.binance_client import BinanceAPIClient
from api.market_data import MarketDataClient
from core.logger import get_module_logger


class TradingService:
    """Service pour l'exécution des trades"""
    
    def __init__(self, cascade_service=None, tp_service=None) -> None:
        """Initialise le service de trading"""
        self.logger = get_module_logger("TradingService")
        self.binance_client = BinanceAPIClient()
        self.market_data_client = MarketDataClient()
        
        # Référence aux services (injection de dépendance)
        self.cascade_service = cascade_service
        self.tp_service = tp_service
        
        # Cache des informations de symbole
        self.symbol_info_cache: Dict[str, Dict[str, Any]] = {}
        
        # Cache optimisé pour la quantité minimale (éviter les recalculs)
        self.min_quantity_cache: Dict[str, str] = {}
        
        self.logger.debug("TradingService initialisé")
    
    def _get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations du symbole avec cache
        
        Args:
            symbol: Symbole à récupérer
            
        Returns:
            Informations du symbole ou None
        """
        self.logger.debug(f"_get_symbol_info called for {symbol}")
        
        # Vérifier le cache d'abord
        if symbol in self.symbol_info_cache:
            self.logger.debug(f"Informations {symbol} trouvées dans le cache")
            return self.symbol_info_cache[symbol]
        
        # Récupérer depuis l'API
        symbol_info = self.binance_client.get_symbol_info(symbol)
        
        if symbol_info:
            # Mettre en cache
            self.symbol_info_cache[symbol] = symbol_info
            self.logger.info(f"Informations {symbol} mises en cache")
        
        return symbol_info
    
    def _extract_lot_size_info(self, symbol_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrait les informations LOT_SIZE du symbole
        
        Args:
            symbol_info: Informations du symbole
            
        Returns:
            Dictionnaire avec min_qty, max_qty, step_size
        """
        self.logger.debug("_extract_lot_size_info called")
        
        filters = symbol_info.get("filters", [])
        
        for filter_info in filters:
            if filter_info.get("filterType") == "LOT_SIZE":
                lot_size_info = {
                    "min_qty": float(filter_info.get("minQty", "0")),
                    "max_qty": float(filter_info.get("maxQty", "0")),
                    "step_size": float(filter_info.get("stepSize", "0"))
                }
                
                self.logger.info(f"LOT_SIZE: min={lot_size_info['min_qty']}, step={lot_size_info['step_size']}")
                return lot_size_info
        
        self.logger.error("Filtre LOT_SIZE non trouvé")
        return {"min_qty": 0, "max_qty": 0, "step_size": 0}
    
    def _format_quantity(self, quantity: float, step_size: float) -> str:
        """
        Formate la quantité selon le step_size
        
        Args:
            quantity: Quantité à formater
            step_size: Pas de quantité
            
        Returns:
            Quantité formatée
        """
        self.logger.debug(f"_format_quantity called: qty={quantity}, step={step_size}")
        
        if step_size == 0:
            self.logger.error("Step size est 0 - impossible de formater")
            return "0"
        
        # Calculer le nombre de décimales nécessaires
        step_decimal = Decimal(str(step_size))
        exponent = step_decimal.as_tuple().exponent
        decimal_places = abs(exponent) if isinstance(exponent, int) else 0
        
        # Arrondir vers le bas pour respecter les règles Binance
        quantity_decimal = Decimal(str(quantity))
        step_decimal_places = Decimal(str(step_size))
        
        formatted_qty = quantity_decimal.quantize(step_decimal_places, rounding=ROUND_DOWN)
        
        # Formater en string sans notation scientifique
        formatted_str = f"{formatted_qty:.{decimal_places}f}".rstrip('0').rstrip('.')
        
        self.logger.debug(f"Quantité formatée: {formatted_str}")
        return formatted_str
    
    def _extract_price_filter_info(self, symbol_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrait les informations PRICE_FILTER du symbole
        
        Args:
            symbol_info: Informations du symbole
            
        Returns:
            Dictionnaire avec min_price, max_price, tick_size
        """
        self.logger.debug("_extract_price_filter_info called")
        
        filters = symbol_info.get("filters", [])
        
        for filter_info in filters:
            if filter_info.get("filterType") == "PRICE_FILTER":
                price_filter_info = {
                    "min_price": float(filter_info.get("minPrice", "0")),
                    "max_price": float(filter_info.get("maxPrice", "0")),
                    "tick_size": float(filter_info.get("tickSize", "0"))
                }
                
                self.logger.info(f"PRICE_FILTER: min={price_filter_info['min_price']}, tick={price_filter_info['tick_size']}")
                return price_filter_info
        
        self.logger.error("Filtre PRICE_FILTER non trouvé")
        return {"min_price": 0, "max_price": 0, "tick_size": 0}
    
    def _format_price(self, price: float, tick_size: float) -> str:
        """
        Formate un prix selon le tick_size du symbole
        
        Args:
            price: Prix à formater
            tick_size: Tick size du symbole
            
        Returns:
            Prix formaté
        """
        self.logger.debug(f"_format_price called: price={price}, tick={tick_size}")
        
        if tick_size == 0:
            self.logger.error("Tick size est 0 - formatage par défaut")
            return f"{price:.2f}"
        
        # Calculer le nombre de décimales basé sur le tick_size
        tick_decimal = Decimal(str(tick_size))
        exponent = tick_decimal.as_tuple().exponent
        
        # Gérer le type de l'exposant (peut être int ou str)
        if isinstance(exponent, int):
            decimal_places = abs(exponent)
        else:
            # Si c'est 'n', 'N', ou 'F', utiliser 2 décimales par défaut
            decimal_places = 2
        
        # Arrondir le prix selon le tick_size
        price_decimal = Decimal(str(price))
        tick_decimal_places = Decimal(str(tick_size))
        
        # Arrondir vers le bas (ROUND_DOWN) pour éviter les erreurs de prix
        formatted_price = price_decimal.quantize(tick_decimal_places, rounding=ROUND_DOWN)
        
        # Formater en string
        formatted_str = f"{formatted_price:.{decimal_places}f}"
        
        self.logger.debug(f"Prix formaté: {formatted_str}")
        return formatted_str
    
    def get_symbol_precision(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations de précision d'un symbole
        
        Args:
            symbol: Symbole à analyser
            
        Returns:
            Dict avec lot_size_info et price_filter_info
        """
        self.logger.debug(f"get_symbol_precision called for {symbol}")
        
        symbol_info = self._get_symbol_info(symbol)
        if not symbol_info:
            return None
        
        lot_size_info = self._extract_lot_size_info(symbol_info)
        price_filter_info = self._extract_price_filter_info(symbol_info)
        
        return {
            "lot_size": lot_size_info,
            "price_filter": price_filter_info
        }
    
    def preload_symbol_info(self, symbol: str) -> bool:
        """
        Précharge les informations d'un symbole au démarrage
        
        Args:
            symbol: Symbole à précharger
            
        Returns:
            True si succès, False sinon
        """
        self.logger.debug(f"preload_symbol_info called for {symbol}")
        self.logger.info(f"Préchargement des informations pour {symbol}")
        
        try:
            # Récupérer les informations du symbole
            symbol_info = self._get_symbol_info(symbol)
            
            if not symbol_info:
                self.logger.error(f"Impossible de précharger {symbol}")
                return False
            
            # Calculer et mettre en cache la quantité minimale
            lot_size_info = self._extract_lot_size_info(symbol_info)
            
            min_qty = lot_size_info["min_qty"]
            step_size = lot_size_info["step_size"]
            
            if min_qty == 0 or step_size == 0:
                self.logger.error("Quantité minimale ou step size invalide")
                return False
            
            # Calculer et mettre en cache la quantité formatée
            formatted_qty = self._format_quantity(min_qty, step_size)
            self.min_quantity_cache[symbol] = formatted_qty
            
            self.logger.info(f"✅ {symbol} préchargé - Quantité min: {formatted_qty}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du préchargement de {symbol}: {e}", exc_info=True)
            return False

    def get_minimum_trade_quantity(self, symbol: str) -> Optional[str]:
        """
        Obtient la quantité minimale de trading pour un symbole (depuis le cache)
        
        Args:
            symbol: Symbole à analyser
            
        Returns:
            Quantité minimale formatée ou None
        """
        self.logger.debug(f"get_minimum_trade_quantity called for {symbol}")
        
        # Vérifier le cache d'abord
        if symbol in self.min_quantity_cache:
            min_qty = self.min_quantity_cache[symbol]
            self.logger.debug(f"Quantité minimale {symbol} depuis le cache: {min_qty}")
            return min_qty
        
        # Fallback : calcul à la volée si pas en cache
        self.logger.warning(f"Quantité {symbol} pas en cache, calcul à la volée")
        
        symbol_info = self._get_symbol_info(symbol)
        
        if not symbol_info:
            self.logger.error(f"Impossible de récupérer les infos pour {symbol}")
            return None
        
        lot_size_info = self._extract_lot_size_info(symbol_info)
        
        min_qty = lot_size_info["min_qty"]
        step_size = lot_size_info["step_size"]
        
        if min_qty == 0 or step_size == 0:
            self.logger.error("Quantité minimale ou step size invalide")
            return None
        
        # Calculer et mettre en cache pour la prochaine fois
        formatted_qty = self._format_quantity(min_qty, step_size)
        self.min_quantity_cache[symbol] = formatted_qty
        
        self.logger.info(f"Quantité minimale pour {symbol}: {formatted_qty}")
        return formatted_qty
    
    def _extract_quote_asset(self, symbol: str) -> str:
        """
        Extrait l'asset de cotation d'un symbole (ex: BTCUSDC -> USDC)
        
        Args:
            symbol: Symbole de trading (ex: BTCUSDC)
            
        Returns:
            Asset de cotation (ex: USDC)
        """
        # Pour la plupart des symboles futures, les assets de cotation sont connus
        common_quote_assets = ['USDT', 'USDC', 'BTC', 'ETH', 'BNB']
        
        for quote_asset in common_quote_assets:
            if symbol.endswith(quote_asset):
                return quote_asset
        
        # Fallback: assumons que c'est USDT si rien trouvé
        self.logger.warning(f"Asset de cotation non identifié pour {symbol}, utilisation de USDT par défaut")
        return 'USDT'
    
    def get_quote_asset_balance(self, symbol: str) -> Optional[float]:
        """
        Récupère la balance de l'asset de cotation du symbole
        
        Args:
            symbol: Symbole de trading (ex: BTCUSDC)
            
        Returns:
            Balance de l'asset de cotation ou None en cas d'erreur
        """
        self.logger.debug(f"get_quote_asset_balance called for {symbol}")
        
        try:
            # Déterminer l'asset de cotation
            quote_asset = self._extract_quote_asset(symbol)
            self.logger.info(f"Asset de cotation déterminé pour {symbol}: {quote_asset}")
            
            account_balance = self.binance_client.get_account_balance()
            
            if not account_balance:
                self.logger.error("Impossible de récupérer la balance du compte")
                return None
            
            # Chercher la balance de l'asset de cotation
            for balance_item in account_balance:
                if balance_item.get("asset") == quote_asset:
                    available_balance = float(balance_item.get("availableBalance", "0"))
                    self.logger.info(f"Balance {quote_asset} disponible: {available_balance}")
                    return available_balance
            
            self.logger.warning(f"Balance {quote_asset} non trouvée")
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de la balance {quote_asset}: {e}", exc_info=True)
            return None
    
    def calculate_theoretical_hedge_price(self, current_price: float, signal_type: str) -> Optional[float]:
        """
        Calcule le prix théorique du hedge basé sur la configuration
        
        Args:
            current_price: Prix actuel du symbole
            signal_type: Type de signal ("long" ou "short")
            
        Returns:
            Prix théorique du hedge ou None
        """
        self.logger.debug(f"calculate_theoretical_hedge_price called: price={current_price}, signal={signal_type}")
        
        try:
            symbol = config.SYMBOL
            
            # Récupérer les données historiques pour analyser high/low
            from api.market_data import MarketDataClient
            market_data_client = MarketDataClient()
            
            lookback_candles = config.HEDGING_CONFIG["LOOKBACK_CANDLES"]
            historical_data = market_data_client.get_historical_data(
                symbol, config.TIMEFRAME, lookback_candles + 1
            )
            
            if historical_data is None or len(historical_data) < lookback_candles:
                self.logger.error("Données historiques insuffisantes pour le calcul hedge")
                return None
            
            # Analyser les dernières bougies (exclure la bougie courante)
            recent_data = historical_data.iloc[-lookback_candles-1:-1]
            
            if signal_type == "long":
                # Pour un signal LONG, le hedge sera SHORT -> prix = support (LOW)
                theoretical_hedge_price = float(recent_data['low'].min())
                self.logger.info(f"Prix hedge théorique LONG->SHORT: {theoretical_hedge_price}")
            elif signal_type == "short":
                # Pour un signal SHORT, le hedge sera LONG -> prix = résistance (HIGH)
                theoretical_hedge_price = float(recent_data['high'].max())
                self.logger.info(f"Prix hedge théorique SHORT->LONG: {theoretical_hedge_price}")
            else:
                self.logger.error(f"Type de signal invalide: {signal_type}")
                return None
            
            return theoretical_hedge_price
            
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul du prix hedge théorique: {e}", exc_info=True)
            return None
    
    def get_initial_trade_quantity(self, symbol: str, signal_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Obtient la quantité initiale de trading selon la configuration
        
        Args:
            symbol: Symbole de trading
            signal_data: Données du signal (nécessaire pour mode PERCENTAGE)
            
        Returns:
            Quantité initiale formatée ou None
        """
        self.logger.debug(f"get_initial_trade_quantity called for {symbol}")
        
        try:
            quantity_mode = config.TRADING_CONFIG["QUANTITY_MODE"]
            self.logger.info(f"Mode de quantité: {quantity_mode}")
            
            # Obtenir les infos du symbole pour le formatage
            symbol_info = self.binance_client.get_symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Impossible d'obtenir les infos pour {symbol}")
                return None
            
            lot_size_info = self._extract_lot_size_info(symbol_info)
            step_size = lot_size_info["step_size"]
            
            if step_size == 0:
                self.logger.error("Step size invalide")
                return None
            
            calculated_quantity: float
            
            if quantity_mode == "MINIMUM":
                # Utiliser la quantité minimale du symbole
                self.logger.info("Utilisation de la quantité minimale du symbole")
                return self.get_minimum_trade_quantity(symbol)
                
            elif quantity_mode == "FIXED":
                # Utiliser la quantité fixe configurée
                calculated_quantity = config.TRADING_CONFIG["INITIAL_QUANTITY"]
                self.logger.info(f"Utilisation de la quantité fixe: {calculated_quantity}")
                
            elif quantity_mode == "PERCENTAGE":
                # Utiliser le pourcentage de la balance
                if not signal_data:
                    self.logger.error("Signal data requis pour le mode PERCENTAGE")
                    return None
                
                # Récupérer la balance de l'asset de cotation
                balance = self.get_quote_asset_balance(symbol)
                if balance is None or balance <= 0:
                    quote_asset = self._extract_quote_asset(symbol)
                    self.logger.warning(f"Balance {quote_asset} insuffisante ou non disponible - fallback vers quantité minimale")
                    return self.get_minimum_trade_quantity(symbol)
                
                # Récupérer le prix actuel depuis les données du signal
                current_price = signal_data.get("current_price")
                signal_type = signal_data.get("type") or signal_data.get("signal_type")  # Compatible avec ALL_OR_NOTHING

                if not current_price or not signal_type:
                    self.logger.error("Prix actuel ou type de signal manquant dans signal_data")
                    return None

                # Utiliser sl_price si fourni (ALL_OR_NOTHING) ou calculer hedge price (CASCADE)
                sl_price = signal_data.get("sl_price")
                if sl_price:
                    self.logger.info(f"Mode ALL_OR_NOTHING: Calcul distance au SL avec offset")

                    # Récupérer l'offset SL depuis la configuration ALL_OR_NOTHING
                    sl_offset = config.ALL_OR_NOTHING_CONFIG.get("SL_OFFSET_PERCENT", 0.005)

                    # Calculer la distance correcte selon le sens
                    if signal_type.lower() == "long":
                        # LONG: Distance = Signal_Price - (SL_Level - SL_Offset)
                        sl_with_offset = sl_price * (1 - sl_offset)
                        price_difference = current_price - sl_with_offset
                        self.logger.info(f"LONG: Signal={current_price}, SL_Level={sl_price}, "
                                       f"SL_avec_offset={sl_with_offset}, Distance={price_difference}")
                    else:  # SHORT
                        # SHORT: Distance = (SL_Level + SL_Offset) - Signal_Price
                        sl_with_offset = sl_price * (1 + sl_offset)
                        price_difference = sl_with_offset - current_price
                        self.logger.info(f"SHORT: Signal={current_price}, SL_Level={sl_price}, "
                                       f"SL_avec_offset={sl_with_offset}, Distance={price_difference}")
                else:
                    # Mode CASCADE: Calculer le prix hedge théorique
                    hedge_price = self.calculate_theoretical_hedge_price(current_price, signal_type)
                    if hedge_price is None:
                        self.logger.error("Impossible de calculer le prix hedge théorique")
                        return None

                    # Calculer la différence de prix pour CASCADE
                    price_difference = abs(current_price - hedge_price)
                    self.logger.info(f"Mode CASCADE: CurrentPrice={current_price}, HedgePrice={hedge_price}, Diff={price_difference}")
                
                if price_difference == 0:
                    self.logger.error("Différence de prix nulle - calcul impossible")
                    return None
                
                # Calculer la quantité basée sur le pourcentage
                balance_percentage = config.TRADING_CONFIG["BALANCE_PERCENTAGE"]
                risk_amount = balance * balance_percentage
                calculated_quantity = risk_amount / price_difference
                
                quote_asset = self._extract_quote_asset(symbol)
                self.logger.info(f"Mode PERCENTAGE: Balance_{quote_asset}={balance}, Risk%={balance_percentage*100}%, "
                               f"RiskAmount={risk_amount}, PriceDiff={price_difference}, Qty={calculated_quantity}")
                
                # Vérifier si la quantité calculée est trop petite
                if calculated_quantity <= 0:
                    self.logger.warning("Quantité calculée nulle ou négative - fallback vers quantité minimale")
                    return self.get_minimum_trade_quantity(symbol)
                
            else:
                self.logger.error(f"Mode de quantité invalide: {quantity_mode}")
                return None
            
            # Formater selon le step_size
            formatted_qty = self._format_quantity(calculated_quantity, step_size)
            self.logger.info(f"Quantité initiale formatée: {formatted_qty} (mode: {quantity_mode})")
            return formatted_qty
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la détermination de la quantité initiale: {e}", exc_info=True)
            return None
    
    def execute_signal_trade(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Exécute un trade basé sur un signal
        
        Args:
            signal: Signal de trading confirmé
            
        Returns:
            Résultat de l'ordre ou None
        """
        self.logger.debug("execute_signal_trade called")
        self.logger.info(f"Exécution du trade pour signal: {signal['type']}")
        
        try:
            symbol = config.SYMBOL
            signal_type = signal["type"]
            
            # Déterminer le côté de l'ordre et position side pour mode Hedge
            if signal_type == "long":
                side = "BUY"
                position_side = "LONG"
            elif signal_type == "short":
                side = "SELL" 
                position_side = "SHORT"
            else:
                self.logger.error(f"Type de signal invalide: {signal_type}")
                return None
            
            # Obtenir la quantité initiale selon le mode configuré
            initial_quantity = self.get_initial_trade_quantity(symbol, signal)
            
            if not initial_quantity:
                self.logger.error("Impossible de déterminer la quantité initiale")
                return None
            
            # Placer l'ordre avec position side pour mode Hedge
            self.logger.info(f"Placement ordre {side} {initial_quantity} {symbol} (position: {position_side})")
            
            order_result = self.binance_client.place_order(
                symbol=symbol,
                side=side,
                quantity=initial_quantity,
                order_type="MARKET",
                position_side=position_side
            )
            
            if order_result:
                self.logger.info(f"✅ Trade exécuté avec succès - ID: {order_result.get('orderId')}")
                
                # Créer l'ordre hedge automatiquement
                hedge_result = self._create_hedge_order(signal, order_result)
                
                # Ajouter les informations de hedge au résultat
                order_result["hedge_order"] = hedge_result
                
                # Démarrer le système TP si hedge créé avec succès et TP service disponible
                if hedge_result and self.tp_service and config.TP_CONFIG["ENABLED"]:
                    self.logger.info("🎯 Démarrage du système TP")
                    self._initialize_tp_system(order_result, hedge_result)
                
                # Démarrer la cascade si hedge créé avec succès et cascade service disponible
                if hedge_result and self.cascade_service and config.CASCADE_CONFIG["ENABLED"]:
                    self.logger.info("🔄 Démarrage du système cascade")
                    self.cascade_service.start_cascade(order_result, hedge_result)
                
                return order_result
            else:
                self.logger.error("❌ Échec de l'exécution du trade")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du trade: {e}", exc_info=True)
            return None
    
    def _initialize_tp_system(
        self, 
        initial_order: Dict[str, Any], 
        hedge_order: Dict[str, Any]
    ) -> None:
        """
        Initialise le système TP avec les prix d'exécution et de hedge
        
        Args:
            initial_order: Résultat de l'ordre initial
            hedge_order: Résultat de l'ordre hedge
        """
        self.logger.debug("_initialize_tp_system called")
        
        try:
            # Extraire le prix d'exécution de l'ordre initial (MARKET)
            initial_price = 0.0
            
            # Essayer les différentes sources de prix pour l'ordre initial
            fills = initial_order.get("fills", [])
            if fills and len(fills) > 0:
                initial_price = float(fills[0].get("price", "0"))
            
            if initial_price == 0.0:
                avg_price = initial_order.get("avgPrice", "0")
                if avg_price and avg_price != "0":
                    initial_price = float(avg_price)
            
            # Si toujours 0, essayer de récupérer via l'API
            if initial_price == 0.0:
                order_id = initial_order.get("orderId")
                if order_id:
                    self.logger.info(f"Récupération prix initial via API - Order ID: {order_id}")
                    order_status = self.binance_client.get_order_status(config.SYMBOL, int(order_id))
                    if order_status:
                        api_price = order_status.get("avgPrice", "0")
                        if api_price and api_price != "0":
                            initial_price = float(api_price)
                            self.logger.info(f"Prix initial récupéré via API: {initial_price}")
                        else:
                            self.logger.warning("Prix avgPrice non disponible via API")
            
            # Pour l'ordre hedge STOP_MARKET, utiliser le stopPrice
            hedge_stop_price = float(hedge_order.get("stopPrice", "0"))
            
            self.logger.info(f"Prix pour TP - Initial: {initial_price}, Hedge stop: {hedge_stop_price}")
            
            if initial_price == 0.0 or hedge_stop_price == 0.0:
                self.logger.error(f"Prix invalides pour initialisation TP - Initial: {initial_price}, Hedge: {hedge_stop_price}")
                return
            
            # Vérifier que le service TP est disponible
            if self.tp_service is None:
                self.logger.warning("Service TP non disponible - initialisation ignorée")
                return
            
            # Déterminer les côtés signal et hedge
            initial_side = initial_order.get("side", "").upper()
            hedge_side = hedge_order.get("side", "").upper()
            
            # Convertir en position sides
            initial_position_side = initial_order.get("positionSide", "BOTH").upper()
            hedge_position_side = hedge_order.get("positionSide", "BOTH").upper()
            
            self.logger.info(f"Côtés - Signal: {initial_side} ({initial_position_side}), Hedge: {hedge_side} ({hedge_position_side})")
            
            # Initialiser les niveaux TP dans le service avec informations sur les côtés
            self.tp_service.initialize_tp_levels(
                initial_price, 
                hedge_stop_price, 
                initial_position_side,  # "LONG" ou "SHORT"
                hedge_position_side     # "LONG" ou "SHORT"
            )
            
            # Créer le TP pour la position initiale
            
            # Extraire la quantité avec fallback
            initial_quantity = 0.0
            
            # Essayer executedQty d'abord
            executed_qty = initial_order.get("executedQty", "0")
            if executed_qty and executed_qty != "0":
                initial_quantity = float(executed_qty)
            
            # Si 0, essayer via les fills
            if initial_quantity == 0.0 and fills:
                fill_qty = fills[0].get("qty", "0")
                if fill_qty and fill_qty != "0":
                    initial_quantity = float(fill_qty)
            
            # Si toujours 0, récupérer via API
            if initial_quantity == 0.0:
                order_id = initial_order.get("orderId")
                if order_id:
                    self.logger.info(f"Récupération quantité initiale via API - Order ID: {order_id}")
                    order_status = self.binance_client.get_order_status(config.SYMBOL, int(order_id))
                    if order_status:
                        api_qty = order_status.get("executedQty", "0")
                        if api_qty and api_qty != "0":
                            initial_quantity = float(api_qty)
                            self.logger.info(f"Quantité initiale récupérée via API: {initial_quantity}")
                        else:
                            self.logger.warning("Quantité executedQty non disponible via API")
            
            self.logger.info(f"Quantité pour TP initial: {initial_quantity}")
            
            if initial_quantity == 0.0:
                self.logger.error("Quantité invalide pour TP - abandon initialisation")
                return
            
            # Créer TP SEULEMENT pour l'ordre initial (position réelle)
            from core.tp_service import TPSide
            
            # Déterminer le côté TP pour la position initiale (basé sur positionSide)
            if initial_position_side == "LONG":
                initial_tp_side = TPSide.LONG
            else:
                initial_tp_side = TPSide.SHORT
            
            # Créer TP uniquement pour la position initiale exécutée
            success_initial = self.tp_service.create_or_update_tp(
                initial_tp_side, 
                initial_quantity, 
                increment_position=False  # False = c'est le signal initial (position 1)
            )
            
            if success_initial:
                self.logger.info(f"TP {initial_tp_side.value} créé pour position initiale: {initial_quantity}")
            else:
                self.logger.error(f"Échec création TP {initial_tp_side.value} initial")
            
            # Le TP pour le hedge sera créé SEULEMENT quand le hedge s'exécute
            self.logger.info("TP hedge sera créé lors de l'exécution réelle du hedge STOP_MARKET")
                    
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation TP: {e}", exc_info=True)
    
    def format_trade_display(self, signal: Dict[str, Any], order_result: Dict[str, Any]) -> str:
        """
        Formate l'affichage du trade exécuté avec informations de hedge
        
        Args:
            signal: Signal original
            order_result: Résultat de l'ordre (avec hedge_order si disponible)
            
        Returns:
            Chaîne formatée pour l'affichage
        """
        self.logger.debug("format_trade_display called")
        
        signal_type = signal["type"].upper()
        order_id = order_result.get("orderId", "N/A")
        symbol = order_result.get("symbol", "N/A")
        quantity = order_result.get("executedQty", order_result.get("origQty", "N/A"))
        
        if signal_type == "LONG":
            emoji = "📈🟢"
        else:
            emoji = "📉🔴"
        
        # Information principale
        main_result = f"TRADE EXECUTÉ: {signal_type} {emoji} | {symbol} {quantity} | ID: {order_id}"
        
        # Information hedge si disponible
        hedge_order = order_result.get("hedge_order")
        if hedge_order:
            hedge_id = hedge_order.get("orderId", "N/A")
            hedge_qty = hedge_order.get("origQty", "N/A")
            hedge_stop = hedge_order.get("stopPrice", "N/A")
            hedge_side = "LONG" if signal_type == "SHORT" else "SHORT"
            
            hedge_result = f"HEDGE: {hedge_side} 🛡️ | {hedge_qty} @ {hedge_stop} | ID: {hedge_id}"
            result = f"{main_result}\n{hedge_result}"
        else:
            # Hedge non créé
            hedge_result = "HEDGE: ❌ Échec de création"
            result = f"{main_result}\n{hedge_result}"
        
        self.logger.debug(f"Trade formaté: {result}")
        return result
    
    def _get_historical_high_low(
        self, 
        symbol: str, 
        interval: str, 
        candles_count: int
    ) -> Optional[Dict[str, float]]:
        """
        Récupère le highest et lowest des X dernières bougies
        
        Args:
            symbol: Symbole de trading
            interval: Intervalle de temps
            candles_count: Nombre de bougies à analyser
            
        Returns:
            Dict avec 'highest' et 'lowest' ou None
        """
        self.logger.debug(f"_get_historical_high_low called: {symbol} {interval} {candles_count}")
        
        try:
            # Récupérer les données historiques
            historical_data = self.market_data_client.get_historical_data(
                symbol, interval, candles_count
            )
            
            if historical_data is None or historical_data.empty:
                self.logger.error("Impossible de récupérer les données historiques pour hedge")
                return None
            
            # Calculer highest et lowest
            highest = float(historical_data['high'].max())
            lowest = float(historical_data['low'].min())
            
            self.logger.info(f"Analyse {candles_count} bougies - High: {highest}, Low: {lowest}")
            return {"highest": highest, "lowest": lowest}
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse high/low: {e}", exc_info=True)
            return None
    
    def _calculate_hedge_quantity(self, original_quantity: str) -> str:
        """
        Calcule la quantité pour l'ordre hedge (multiplié par config)
        
        Args:
            original_quantity: Quantité de l'ordre original
            
        Returns:
            Quantité pour l'ordre hedge
        """
        self.logger.debug(f"_calculate_hedge_quantity called: {original_quantity}")
        
        try:
            original_qty = float(original_quantity)
            multiplier = config.HEDGING_CONFIG["QUANTITY_MULTIPLIER"]
            
            hedge_qty = original_qty * multiplier
            
            # Obtenir les informations de formatage depuis le cache
            symbol = config.SYMBOL
            if symbol in self.symbol_info_cache:
                symbol_info = self.symbol_info_cache[symbol]
                lot_size_info = self._extract_lot_size_info(symbol_info)
                step_size = lot_size_info["step_size"]
                
                # Formater la quantité hedge
                formatted_hedge_qty = self._format_quantity(hedge_qty, step_size)
            else:
                # Fallback simple
                formatted_hedge_qty = f"{hedge_qty:.3f}".rstrip('0').rstrip('.')
            
            self.logger.info(f"Quantité hedge calculée: {original_quantity} x {multiplier} = {formatted_hedge_qty}")
            return formatted_hedge_qty
            
        except Exception as e:
            self.logger.error(f"Erreur calcul quantité hedge: {e}", exc_info=True)
            return original_quantity  # Fallback à la quantité originale
    
    def _format_stop_price(self, price: float) -> str:
        """
        Formate le prix de stop selon la précision du symbole
        
        Args:
            price: Prix à formater
            
        Returns:
            Prix formaté
        """
        self.logger.debug(f"_format_stop_price called: {price}")
        
        try:
            # Pour BTCUSDC, généralement 2 décimales suffisent
            # TODO: Récupérer la précision depuis symbol info si nécessaire
            formatted_price = f"{price:.2f}"
            
            self.logger.debug(f"Prix stop formaté: {formatted_price}")
            return formatted_price
            
        except Exception as e:
            self.logger.error(f"Erreur formatage prix stop: {e}", exc_info=True)
            return str(price)
    
    def _create_hedge_order(
        self, 
        original_signal: Dict[str, Any], 
        original_order: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Crée l'ordre hedge après exécution du signal principal
        
        Args:
            original_signal: Signal original qui a déclenché le trade
            original_order: Résultat de l'ordre principal
            
        Returns:
            Résultat de l'ordre hedge ou None
        """
        self.logger.debug("_create_hedge_order called")
        self.logger.info("Création de l'ordre hedge automatique")
        
        try:
            if not config.HEDGING_CONFIG["ENABLED"]:
                self.logger.info("Hedging désactivé dans la configuration")
                return None
            
            symbol = config.SYMBOL
            interval = config.TIMEFRAME
            lookback_candles = config.HEDGING_CONFIG["LOOKBACK_CANDLES"]
            
            # Récupérer les données high/low
            high_low_data = self._get_historical_high_low(symbol, interval, lookback_candles)
            
            if not high_low_data:
                self.logger.error("Impossible de récupérer les données high/low pour hedge")
                return None
            
            # Déterminer les paramètres de l'ordre hedge selon le signal original
            original_signal_type = original_signal["type"]
            # Utiliser origQty car executedQty peut être 0 si l'ordre est encore en cours
            original_quantity = original_order.get("origQty", original_order.get("executedQty", "0"))
            
            if original_signal_type == "short":
                # Signal SHORT → Hedge LONG avec highest comme stop
                hedge_side = "BUY"
                hedge_position_side = "LONG"
                stop_price = self._format_stop_price(high_low_data["highest"])
                
            elif original_signal_type == "long":
                # Signal LONG → Hedge SHORT avec lowest comme stop
                hedge_side = "SELL"
                hedge_position_side = "SHORT"
                stop_price = self._format_stop_price(high_low_data["lowest"])
                
            else:
                self.logger.error(f"Type de signal invalide pour hedge: {original_signal_type}")
                return None
            
            # Calculer la quantité hedge (doublée)
            hedge_quantity = self._calculate_hedge_quantity(original_quantity)
            
            # Vérification de sécurité pour éviter quantité nulle
            if not hedge_quantity or float(hedge_quantity) <= 0:
                self.logger.error(f"Quantité hedge invalide: {hedge_quantity} (quantité originale: {original_quantity})")
                return None
            
            # Placer l'ordre STOP_MARKET
            self.logger.info(f"Création hedge {hedge_side} {hedge_quantity} @ {stop_price} (position: {hedge_position_side})")
            
            hedge_order = self.binance_client.place_stop_market_order(
                symbol=symbol,
                side=hedge_side,
                quantity=hedge_quantity,
                stop_price=stop_price,
                position_side=hedge_position_side
            )
            
            if hedge_order:
                self.logger.info(f"✅ Ordre hedge créé avec succès - ID: {hedge_order.get('orderId')}")
                return hedge_order
            else:
                self.logger.error("❌ Échec de la création de l'ordre hedge")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de l'ordre hedge: {e}", exc_info=True)
            return None