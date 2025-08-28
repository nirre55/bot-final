"""
Module de récupération des données de marché
Responsabilité unique : Récupération des données historiques et temps réel
"""
from typing import List, Dict, Any, Optional
import pandas as pd
import requests

import config
from core.logger import get_module_logger


class MarketDataClient:
    """Client pour récupérer les données de marché Binance"""
    
    def __init__(self) -> None:
        """Initialise le client de données de marché"""
        self.logger = get_module_logger("MarketDataClient")
        self.base_url: str = "https://fapi.binance.com"
        
        self.logger.debug("MarketDataClient initialisé")
    
    def get_klines(
        self, 
        symbol: str, 
        interval: str, 
        limit: int = 100
    ) -> Optional[List[List]]:
        """
        Récupère les données klines (bougies) historiques
        
        Args:
            symbol: Symbole de trading (ex: BTCUSDT)
            interval: Intervalle de temps (ex: 1m, 5m, 1h)
            limit: Nombre de bougies à récupérer (max 1500)
            
        Returns:
            Liste des klines ou None en cas d'erreur
        """
        self.logger.debug(f"get_klines called: symbol={symbol}, interval={interval}, limit={limit}")
        
        if limit > 1500:
            self.logger.error(f"Limite trop élevée: {limit} > 1500")
            raise ValueError("La limite ne peut pas dépasser 1500")
        
        endpoint = "/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        try:
            self.logger.info(f"Récupération de {limit} bougies {interval} pour {symbol}")
            
            response = requests.get(
                f"{self.base_url}{endpoint}",
                params=params
            )
            
            if response.status_code == 200:
                klines_data = response.json()
                self.logger.info(f"Récupération réussie: {len(klines_data)} bougies")
                self.logger.debug(f"Première bougie: {klines_data[0] if klines_data else 'Aucune'}")
                return klines_data
            else:
                self.logger.error(f"Erreur API klines: {response.status_code}")
                self.logger.error(f"Réponse: {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des klines: {e}", exc_info=True)
            return None
    
    def klines_to_dataframe(self, klines_data: List[List]) -> pd.DataFrame:
        """
        Convertit les données klines en DataFrame pandas
        
        Args:
            klines_data: Données klines brutes de l'API
            
        Returns:
            DataFrame avec colonnes OHLCV
        """
        self.logger.debug(f"klines_to_dataframe called with {len(klines_data)} klines")
        
        if not klines_data:
            self.logger.warning("Données klines vides")
            return pd.DataFrame()
        
        try:
            # Structure des klines Binance:
            # [timestamp, open, high, low, close, volume, close_time, ...]
            df = pd.DataFrame(klines_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Convertir les types de données
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Convertir timestamp en datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            
            # Garder seulement les colonnes essentielles
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            self.logger.info(f"DataFrame créé: {len(df)} lignes, période {df.index[0]} à {df.index[-1]}")
            self.logger.debug(f"Colonnes: {list(df.columns)}")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la conversion en DataFrame: {e}", exc_info=True)
            return pd.DataFrame()
    
    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        limit: int = 100
    ) -> Optional[pd.DataFrame]:
        """
        Récupère les données historiques sous forme de DataFrame
        
        Args:
            symbol: Symbole de trading
            interval: Intervalle de temps
            limit: Nombre de bougies
            
        Returns:
            DataFrame OHLCV ou None en cas d'erreur
        """
        self.logger.debug(f"get_historical_data called: {symbol} {interval} {limit}")
        
        # Récupérer les données klines
        klines_data = self.get_klines(symbol, interval, limit)
        
        if klines_data is None:
            self.logger.error("Impossible de récupérer les données klines")
            return None
        
        # Convertir en DataFrame
        df = self.klines_to_dataframe(klines_data)
        
        if df.empty:
            self.logger.error("DataFrame vide après conversion")
            return None
        
        self.logger.info(f"Données historiques prêtes: {len(df)} bougies")
        return df