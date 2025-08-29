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
    
    def __init__(self) -> None:
        """Initialise le service de trading"""
        self.logger = get_module_logger("TradingService")
        self.binance_client = BinanceAPIClient()
        self.market_data_client = MarketDataClient()
        
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
            
            # Obtenir la quantité minimale
            min_quantity = self.get_minimum_trade_quantity(symbol)
            
            if not min_quantity:
                self.logger.error("Impossible de déterminer la quantité minimale")
                return None
            
            # Placer l'ordre avec position side pour mode Hedge
            self.logger.info(f"Placement ordre {side} {min_quantity} {symbol} (position: {position_side})")
            
            order_result = self.binance_client.place_order(
                symbol=symbol,
                side=side,
                quantity=min_quantity,
                order_type="MARKET",
                position_side=position_side
            )
            
            if order_result:
                self.logger.info(f"✅ Trade exécuté avec succès - ID: {order_result.get('orderId')}")
                
                # Créer l'ordre hedge automatiquement
                hedge_result = self._create_hedge_order(signal, order_result)
                
                # Ajouter les informations de hedge au résultat
                order_result["hedge_order"] = hedge_result
                
                return order_result
            else:
                self.logger.error("❌ Échec de l'exécution du trade")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du trade: {e}", exc_info=True)
            return None
    
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