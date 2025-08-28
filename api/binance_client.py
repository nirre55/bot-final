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