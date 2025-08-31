"""
Client API Binance
Responsabilité unique : Communication avec l'API REST Binance
"""
import hashlib
import hmac
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import requests

import config
from core.logger import get_module_logger


class BinanceAPIClient:
    """Client pour l'API REST Binance Futures"""
    
    def __init__(self) -> None:
        """Initialise le client API Binance"""
        self.logger = get_module_logger("BinanceAPI")
        self.api_key: Optional[str] = config.BINANCE_API_KEY
        self.secret_key: Optional[str] = config.BINANCE_SECRET_KEY
        self.base_url: str = "https://fapi.binance.com"
        
        self.logger.debug("Client API Binance initialisé")
        
        if not self.api_key or not self.secret_key:
            self.logger.error("Clés API Binance manquantes dans la configuration")
            raise ValueError("Clés API Binance manquantes")
    
    def _generate_signature(self, data: str) -> str:
        """
        Génère la signature HMAC SHA256 pour l'API Binance
        
        Args:
            data: Données à signer
            
        Returns:
            Signature HMAC SHA256
        """
        self.logger.debug("_generate_signature called")
        
        if not self.secret_key:
            self.logger.error("Clé secrète Binance manquante")
            raise ValueError("Clé secrète Binance manquante")
        
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        self.logger.debug("Signature générée avec succès")
        return signature
    
    def get_account_balance(self) -> Optional[List[Dict[str, Any]]]:
        """
        Récupère la balance du compte Binance Futures
        
        Returns:
            Liste des balances ou None en cas d'erreur
        """
        self.logger.debug("get_account_balance called")
        self.logger.info("Récupération de la balance du compte")
        
        try:
            endpoint = "/fapi/v2/balance"
            timestamp = int(time.time() * 1000)
            
            params: Dict[str, Any] = {"timestamp": timestamp}
            
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            self.logger.debug(f"Requête API: {endpoint}")
            response = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                balance_data = response.json()
                self.logger.info("Balance du compte récupérée avec succès")
                self.logger.debug(f"Nombre de balances: {len(balance_data)}")
                return balance_data
            else:
                self.logger.error(
                    f"Erreur lors de la récupération du solde: {response.status_code}"
                )
                self.logger.error(f"Réponse: {response.text}")
                return None

        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de la balance: {e}", exc_info=True)
            return None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations du compte
        
        Returns:
            Informations du compte ou None en cas d'erreur
        """
        self.logger.debug("get_account_info called")
        self.logger.info("Récupération des informations du compte")
        
        try:
            endpoint = "/fapi/v2/account"
            timestamp = int(time.time() * 1000)
            
            params: Dict[str, Any] = {"timestamp": timestamp}
            
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            response = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                account_data = response.json()
                self.logger.info("Informations du compte récupérées avec succès")
                return account_data
            else:
                self.logger.error(
                    f"Erreur lors de la récupération des informations: {response.status_code}"
                )
                return None

        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des informations: {e}", exc_info=True)
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations d'un symbole (précision, quantité min, etc.)
        
        Args:
            symbol: Symbole à récupérer
            
        Returns:
            Informations du symbole ou None
        """
        self.logger.debug(f"get_symbol_info called for {symbol}")
        self.logger.info(f"Récupération des informations du symbole {symbol}")
        
        try:
            endpoint = "/fapi/v1/exchangeInfo"
            
            response = requests.get(f"{self.base_url}{endpoint}")
            
            if response.status_code == 200:
                exchange_info = response.json()
                
                # Chercher le symbole spécifique
                for symbol_info in exchange_info.get("symbols", []):
                    if symbol_info.get("symbol") == symbol:
                        self.logger.info(f"Informations trouvées pour {symbol}")
                        return symbol_info
                
                self.logger.warning(f"Symbole {symbol} non trouvé")
                return None
                
            else:
                self.logger.error(f"Erreur lors de la récupération: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du symbole: {e}", exc_info=True)
            return None
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        order_type: str = "MARKET",
        position_side: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Place un ordre sur Binance Futures
        
        Args:
            symbol: Symbole de trading
            side: BUY ou SELL
            quantity: Quantité à trader
            order_type: Type d'ordre (MARKET par défaut)
            position_side: LONG ou SHORT (requis en mode Hedge)
            
        Returns:
            Réponse de l'ordre ou None
        """
        self.logger.debug(f"place_order called: {symbol} {side} {quantity}")
        self.logger.info(f"Placement d'ordre {side} {quantity} {symbol}")
        
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": quantity,
                "timestamp": timestamp
            }
            
            # Ajouter positionSide si spécifié (requis pour mode Hedge)
            if position_side:
                params["positionSide"] = position_side
                self.logger.debug(f"Position side définie: {position_side}")
            
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            response = requests.post(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                order_data = response.json()
                self.logger.info(f"Ordre placé avec succès: {order_data.get('orderId')}")
                return order_data
            else:
                self.logger.error(f"Erreur placement ordre: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors du placement d'ordre: {e}", exc_info=True)
            return None
    
    def place_stop_market_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        stop_price: str,
        position_side: str
    ) -> Optional[Dict[str, Any]]:
        """
        Place un ordre STOP_MARKET sur Binance Futures
        
        Args:
            symbol: Symbole de trading
            side: BUY ou SELL
            quantity: Quantité à trader
            stop_price: Prix de déclenchement du stop
            position_side: LONG ou SHORT (requis en mode Hedge)
            
        Returns:
            Réponse de l'ordre ou None
        """
        self.logger.debug(f"place_stop_market_order called: {symbol} {side} {quantity} @ {stop_price}")
        self.logger.info(f"Placement ordre STOP_MARKET {side} {quantity} {symbol} @ {stop_price}")
        
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": "STOP_MARKET",
                "quantity": quantity,
                "stopPrice": stop_price,
                "positionSide": position_side,
                "timestamp": timestamp
            }
            
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            response = requests.post(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                order_data = response.json()
                self.logger.info(f"Ordre STOP_MARKET placé avec succès: {order_data.get('orderId')}")
                return order_data
            else:
                self.logger.error(f"Erreur placement STOP_MARKET: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors du placement STOP_MARKET: {e}", exc_info=True)
            return None
    
    def get_order_status(self, symbol: str, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Récupère le statut d'un ordre spécifique
        
        Args:
            symbol: Symbole de trading
            order_id: ID de l'ordre
            
        Returns:
            Statut de l'ordre ou None
        """
        self.logger.debug(f"get_order_status called: {symbol} {order_id}")
        
        try:
            endpoint = "/fapi/v1/order"
            timestamp = int(time.time() * 1000)
            
            params: Dict[str, Any] = {
                "symbol": symbol,
                "orderId": order_id,
                "timestamp": timestamp
            }
            
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            params["signature"] = signature
            
            headers = {"X-MBX-APIKEY": self.api_key}
            
            response = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                order_data = response.json()
                self.logger.debug(f"Statut ordre {order_id}: {order_data.get('status')}")
                return order_data
            else:
                self.logger.error(f"Erreur récupération statut ordre: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du statut d'ordre: {e}", exc_info=True)
            return None