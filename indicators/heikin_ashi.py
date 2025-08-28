"""
Calculs des bougies Heikin Ashi
Module responsable uniquement du calcul des bougies Heikin Ashi
"""
import logging
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd


def setup_heikin_ashi_logging() -> logging.Logger:
    """Configure le système de logging pour le module Heikin Ashi"""
    logger = logging.getLogger("HeikinAshi")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(module)s.%(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


class HeikinAshi:
    """Calculateur des bougies Heikin Ashi"""
    
    _logger = setup_heikin_ashi_logging()
    
    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcule les valeurs Heikin Ashi pour un DataFrame
        
        Args:
            df: DataFrame avec colonnes 'open', 'high', 'low', 'close'
            
        Returns:
            DataFrame avec colonnes HA_open, HA_high, HA_low, HA_close
        """
        HeikinAshi._logger.debug(f"compute called with DataFrame shape: {df.shape}")
        
        if not isinstance(df, pd.DataFrame):
            HeikinAshi._logger.error(f"df doit être un DataFrame, reçu: {type(df)}")
            raise TypeError("df doit être un pandas DataFrame")
        
        required_cols = ['open', 'high', 'low', 'close']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            HeikinAshi._logger.error(f"Colonnes manquantes: {missing_cols}")
            raise ValueError(f"Colonnes manquantes dans le DataFrame: {missing_cols}")
        
        if df.empty:
            HeikinAshi._logger.warning("DataFrame vide fourni")
            return df.copy()
        
        HeikinAshi._logger.info(f"Calcul Heikin Ashi sur {len(df)} bougies")
        
        try:
            ha_df: pd.DataFrame = df.copy()
            
            # HA Close = moyenne des 4 prix
            ha_df['HA_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
            
            # HA Open - calculé séquentiellement
            ha_open: list = []
            
            # Premier HA Open = moyenne open et close
            first_ha_open: float = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
            ha_open.append(first_ha_open)
            
            # HA Open suivants = moyenne du HA Open précédent et HA Close précédent
            for i in range(1, len(df)):
                prev_ha_open: float = ha_open[i - 1]
                prev_ha_close: float = ha_df['HA_close'].iloc[i - 1]
                current_ha_open: float = (prev_ha_open + prev_ha_close) / 2
                ha_open.append(current_ha_open)
            
            ha_df['HA_open'] = ha_open
            
            # HA High = maximum entre HA_open, HA_close et high original
            ha_df['HA_high'] = ha_df[['HA_open', 'HA_close', 'high']].max(axis=1)
            
            # HA Low = minimum entre HA_open, HA_close et low original
            ha_df['HA_low'] = ha_df[['HA_open', 'HA_close', 'low']].min(axis=1)
            
            HeikinAshi._logger.info("Calcul Heikin Ashi terminé avec succès")
            HeikinAshi._logger.debug(f"Résultat: colonnes {list(ha_df.columns)}")
            
            return ha_df
            
        except Exception as e:
            HeikinAshi._logger.error(f"Erreur lors du calcul Heikin Ashi: {e}", exc_info=True)
            raise
    
    @staticmethod
    def get_candle_color(ha_open: float, ha_close: float) -> str:
        """
        Détermine la couleur d'une bougie Heikin Ashi
        
        Args:
            ha_open: Prix d'ouverture HA
            ha_close: Prix de clôture HA
            
        Returns:
            str: 'green', 'red', ou 'doji'
        """
        HeikinAshi._logger.debug(f"get_candle_color called with open={ha_open}, close={ha_close}")
        
        if not isinstance(ha_open, (int, float)) or not isinstance(ha_close, (int, float)):
            HeikinAshi._logger.error(f"Paramètres doivent être numériques: open={ha_open}, close={ha_close}")
            raise TypeError("ha_open et ha_close doivent être numériques")
        
        color: str
        if ha_close > ha_open:
            color = "green"
        elif ha_close < ha_open:
            color = "red"
        else:
            color = "doji"
            
        HeikinAshi._logger.debug(f"Couleur de bougie déterminée: {color}")
        return color
    
    @staticmethod
    def get_latest_ha_candle(ha_df: pd.DataFrame) -> Optional[Dict[str, Union[float, str]]]:
        """
        Retourne les données de la dernière bougie HA
        
        Args:
            ha_df: DataFrame avec colonnes HA calculées
            
        Returns:
            dict: Données de la dernière bougie HA ou None si vide
        """
        HeikinAshi._logger.debug(f"get_latest_ha_candle called with DataFrame shape: {ha_df.shape}")
        
        if not isinstance(ha_df, pd.DataFrame):
            HeikinAshi._logger.error(f"ha_df doit être un DataFrame, reçu: {type(ha_df)}")
            raise TypeError("ha_df doit être un pandas DataFrame")
        
        required_ha_cols = ['HA_open', 'HA_high', 'HA_low', 'HA_close']
        missing_cols = [col for col in required_ha_cols if col not in ha_df.columns]
        if missing_cols:
            HeikinAshi._logger.error(f"Colonnes HA manquantes: {missing_cols}")
            raise ValueError(f"Colonnes HA manquantes: {missing_cols}")
        
        if ha_df.empty:
            HeikinAshi._logger.warning("DataFrame HA vide")
            return None
        
        try:
            latest = ha_df.iloc[-1]
            
            candle_data: Dict[str, Union[float, str]] = {
                'open': float(latest['HA_open']),
                'high': float(latest['HA_high']),
                'low': float(latest['HA_low']),
                'close': float(latest['HA_close']),
                'color': HeikinAshi.get_candle_color(latest['HA_open'], latest['HA_close'])
            }
            
            HeikinAshi._logger.info(f"Dernière bougie HA: {candle_data['color']} O={candle_data['open']:.4f} C={candle_data['close']:.4f}")
            return candle_data
            
        except Exception as e:
            HeikinAshi._logger.error(f"Erreur lors de l'extraction de la dernière bougie: {e}", exc_info=True)
            raise
    
    @staticmethod
    def get_close_series(ha_df: pd.DataFrame) -> pd.Series:
        """
        Retourne la série des prix de clôture HA
        
        Args:
            ha_df: DataFrame avec colonnes HA
            
        Returns:
            Series: Prix de clôture HA
        """
        HeikinAshi._logger.debug(f"get_close_series called with DataFrame shape: {ha_df.shape}")
        
        if not isinstance(ha_df, pd.DataFrame):
            HeikinAshi._logger.error(f"ha_df doit être un DataFrame, reçu: {type(ha_df)}")
            raise TypeError("ha_df doit être un pandas DataFrame")
        
        if 'HA_close' not in ha_df.columns:
            HeikinAshi._logger.warning("Colonne HA_close manquante dans le DataFrame")
            return pd.Series(dtype=float)
        
        close_series: pd.Series = ha_df['HA_close'].copy()
        HeikinAshi._logger.info(f"Série HA_close extraite: {len(close_series)} valeurs")
        HeikinAshi._logger.debug(f"HA_close range: {close_series.min():.4f} - {close_series.max():.4f}")
        
        return close_series