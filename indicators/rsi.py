"""
Calculs du RSI (Relative Strength Index)
Module responsable uniquement du calcul de l'indicateur RSI
"""
import logging
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd


def setup_rsi_logging() -> logging.Logger:
    """Configure le système de logging pour le module RSI"""
    logger = logging.getLogger("RSI")
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


class RSI:
    """Calculateur RSI avec méthode EMA"""
    
    _logger = setup_rsi_logging()
    
    @staticmethod
    def calculate(price_series: pd.Series, period: int) -> pd.Series:
        """
        Calcule le RSI pour une série de prix
        
        Args:
            price_series: Série des prix (Series pandas)
            period: Période du RSI
            
        Returns:
            Series: Valeurs RSI
        """
        RSI._logger.debug(f"calculate called with period={period}, data_length={len(price_series)}")
        
        if not isinstance(price_series, pd.Series):
            RSI._logger.error(f"price_series doit être un pd.Series, reçu: {type(price_series)}")
            raise TypeError("price_series doit être un pandas Series")
            
        if not isinstance(period, int) or period <= 0:
            RSI._logger.error(f"period doit être un entier positif, reçu: {period}")
            raise ValueError("period doit être un entier positif")
        
        if len(price_series) < period + 1:
            RSI._logger.warning(f"Données insuffisantes: {len(price_series)} < {period + 1}")
            return pd.Series([np.nan] * len(price_series), index=price_series.index)
        
        RSI._logger.info(f"Calcul RSI période {period} sur {len(price_series)} données")
        
        try:
            # Calculer les variations de prix
            delta: pd.Series = price_series.diff()
            
            # Séparer les gains et pertes
            gain: pd.Series = delta.where(delta > 0, 0.0)
            loss: pd.Series = -delta.where(delta < 0, 0.0)
            
            # Calculer les moyennes avec EMA
            avg_gain: pd.Series = gain.ewm(alpha=1/period, adjust=False).mean()
            avg_loss: pd.Series = loss.ewm(alpha=1/period, adjust=False).mean()
            
            # Calculer RS et RSI
            rs: pd.Series = avg_gain / avg_loss
            rsi: pd.Series = 100 - (100 / (1 + rs))
            
            RSI._logger.debug(f"RSI calculé avec succès, valeurs: min={rsi.min():.2f}, max={rsi.max():.2f}")
            return rsi
            
        except Exception as e:
            RSI._logger.error(f"Erreur lors du calcul RSI: {e}", exc_info=True)
            raise
    
    @staticmethod
    def calculate_multiple(price_series: pd.Series, periods: List[int]) -> Dict[str, pd.Series]:
        """
        Calcule le RSI pour plusieurs périodes
        
        Args:
            price_series: Série des prix
            periods: Liste des périodes (ex: [14, 21])
            
        Returns:
            dict: {f'RSI_{period}': Series} pour chaque période
        """
        RSI._logger.debug(f"calculate_multiple called with periods={periods}")
        
        if not isinstance(periods, (list, tuple)):
            RSI._logger.error(f"periods doit être une liste, reçu: {type(periods)}")
            raise TypeError("periods doit être une liste d'entiers")
            
        if not all(isinstance(p, int) and p > 0 for p in periods):
            RSI._logger.error(f"Tous les éléments de periods doivent être des entiers positifs: {periods}")
            raise ValueError("Tous les éléments de periods doivent être des entiers positifs")
        
        RSI._logger.info(f"Calcul RSI multiple pour {len(periods)} périodes: {periods}")
        
        rsi_results: Dict[str, pd.Series] = {}
        
        try:
            for period in periods:
                rsi_key: str = f'RSI_{period}'
                rsi_values: pd.Series = RSI.calculate(price_series, period)
                rsi_results[rsi_key] = rsi_values
                RSI._logger.debug(f"RSI calculé pour période {period}")
            
            RSI._logger.info(f"RSI multiple calculé avec succès pour {len(periods)} périodes")
            return rsi_results
            
        except Exception as e:
            RSI._logger.error(f"Erreur lors du calcul RSI multiple: {e}", exc_info=True)
            raise
    
    @staticmethod
    def get_latest_values(rsi_dict: Dict[str, pd.Series]) -> Dict[str, Optional[float]]:
        """
        Extrait les dernières valeurs RSI
        
        Args:
            rsi_dict: Dictionnaire des RSI calculés
            
        Returns:
            dict: {period: dernière_valeur} ou {period: None} si NaN
        """
        RSI._logger.debug(f"get_latest_values called with {len(rsi_dict)} RSI series")
        
        if not isinstance(rsi_dict, dict):
            RSI._logger.error(f"rsi_dict doit être un dictionnaire, reçu: {type(rsi_dict)}")
            raise TypeError("rsi_dict doit être un dictionnaire")
        
        latest_values: Dict[str, Optional[float]] = {}
        
        try:
            for rsi_name, rsi_series in rsi_dict.items():
                if not isinstance(rsi_series, pd.Series):
                    RSI._logger.warning(f"Série RSI invalide pour {rsi_name}: {type(rsi_series)}")
                    latest_values[rsi_name] = None
                    continue
                    
                if rsi_series.empty:
                    RSI._logger.warning(f"Série RSI vide pour {rsi_name}")
                    latest_values[rsi_name] = None
                else:
                    latest_value: float = rsi_series.iloc[-1]
                    final_value: Optional[float] = latest_value if not np.isnan(latest_value) else None
                    latest_values[rsi_name] = final_value
                    RSI._logger.debug(f"Dernière valeur {rsi_name}: {final_value}")
            
            RSI._logger.info(f"Extraction des dernières valeurs terminée: {len(latest_values)} valeurs")
            return latest_values
            
        except Exception as e:
            RSI._logger.error(f"Erreur lors de l'extraction des dernières valeurs: {e}", exc_info=True)
            raise
    
    @staticmethod
    def classify_rsi_level(
        rsi_value: Optional[float], 
        oversold: float = 30, 
        overbought: float = 70
    ) -> str:
        """
        Classe le niveau RSI
        
        Args:
            rsi_value: Valeur RSI
            oversold: Seuil de survente
            overbought: Seuil de surachat
            
        Returns:
            str: 'oversold', 'overbought', 'neutral', ou 'N/A'
        """
        RSI._logger.debug(f"classify_rsi_level called with value={rsi_value}, oversold={oversold}, overbought={overbought}")
        
        if not isinstance(oversold, (int, float)) or not isinstance(overbought, (int, float)):
            RSI._logger.error(f"Seuils doivent être numériques: oversold={oversold}, overbought={overbought}")
            raise TypeError("Les seuils oversold et overbought doivent être numériques")
            
        if oversold >= overbought:
            RSI._logger.error(f"oversold ({oversold}) doit être < overbought ({overbought})")
            raise ValueError("oversold doit être inférieur à overbought")
        
        if rsi_value is None or np.isnan(rsi_value):
            RSI._logger.debug("Valeur RSI invalide ou NaN")
            return 'N/A'
        
        classification: str
        if rsi_value <= oversold:
            classification = 'oversold'
        elif rsi_value >= overbought:
            classification = 'overbought'
        else:
            classification = 'neutral'
            
        RSI._logger.debug(f"RSI {rsi_value:.2f} classifié comme: {classification}")
        return classification