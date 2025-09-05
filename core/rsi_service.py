"""
Service de calcul RSI
Responsabilité unique : Orchestration du calcul RSI avec données historiques
"""
from typing import Dict, List, Optional, Tuple
import pandas as pd

import config
from api.market_data import MarketDataClient
from indicators.rsi import RSI
from indicators.heikin_ashi import HeikinAshi
from core.logger import get_module_logger


class RSIService:
    """Service pour calculer les RSI avec données historiques"""
    
    def __init__(self) -> None:
        """Initialise le service RSI"""
        self.logger = get_module_logger("RSIService")
        self.market_data_client = MarketDataClient()
        
        self.logger.debug("RSIService initialisé")
    
    def _get_rsi_periods(self) -> List[int]:
        """
        Extrait les périodes RSI de la configuration
        
        Returns:
            Liste des périodes à calculer
        """
        periods = list(config.SIGNAL_CONFIG["RSI_THRESHOLDS"].keys())
        self.logger.debug(f"Périodes RSI configurées: {periods}")
        return periods
    
    def _get_required_candles(self, periods: List[int]) -> int:
        """
        Calcule le nombre de bougies nécessaires pour le calcul RSI
        
        Args:
            periods: Liste des périodes RSI
            
        Returns:
            Nombre de bougies à récupérer
        """
        max_period = max(periods)
        # Prendre 3x la période max pour avoir assez de données pour la convergence
        required = max_period * 3
        # Minimum 100 bougies pour assurer la qualité du calcul
        required = max(required, 100)
        
        self.logger.debug(f"Bougies nécessaires: {required} (max période: {max_period})")
        return required
    
    def calculate_rsi_for_symbol(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Dict[str, Dict]]:
        """
        Calcule les RSI pour toutes les périodes configurées
        
        Args:
            symbol: Symbole de trading
            interval: Intervalle de temps
            
        Returns:
            Dictionnaire avec RSI calculés et classifications ou None
        """
        self.logger.debug(f"calculate_rsi_for_symbol called: {symbol} {interval}")
        self.logger.info(f"Début du calcul RSI pour {symbol}")
        
        try:
            # Obtenir les périodes de la configuration
            periods = self._get_rsi_periods()
            
            # Calculer le nombre de bougies nécessaires
            required_candles = self._get_required_candles(periods)
            
            # Récupérer les données historiques
            self.logger.info(f"Récupération de {required_candles} bougies pour {symbol}")
            historical_data = self.market_data_client.get_historical_data(
                symbol, interval, required_candles
            )
            
            if historical_data is None or historical_data.empty:
                self.logger.error("Impossible de récupérer les données historiques")
                return None
            
            # Déterminer quelles données utiliser pour le calcul RSI
            if config.SIGNAL_CONFIG["RSI_ON_HA"]:
                # Calculer les données Heikin Ashi
                self.logger.info("Calcul RSI sur données Heikin Ashi activé")
                ha_data = HeikinAshi.compute(historical_data)
                close_prices = ha_data['HA_close']
                self.logger.debug(f"Utilisation de {len(close_prices)} prix de clôture HA")
            else:
                # Utiliser les données normales
                self.logger.info("Calcul RSI sur données normales")
                close_prices = historical_data['close']
                self.logger.debug(f"Utilisation de {len(close_prices)} prix de clôture normaux")
            
            # Calculer les RSI pour toutes les périodes
            rsi_results = RSI.calculate_multiple(close_prices, periods)
            
            # Obtenir les dernières valeurs
            latest_rsi_values = RSI.get_latest_values(rsi_results)
            
            # Classer chaque RSI selon les seuils configurés
            classified_rsi = {}
            
            for period in periods:
                rsi_key = f"RSI_{period}"
                rsi_value = latest_rsi_values.get(rsi_key)
                
                if rsi_value is not None:
                    # Obtenir les seuils pour cette période
                    thresholds = config.SIGNAL_CONFIG["RSI_THRESHOLDS"][period]
                    oversold = thresholds["OVERSOLD"]
                    overbought = thresholds["OVERBOUGHT"]
                    
                    # Classifier la valeur RSI
                    classification = RSI.classify_rsi_level(
                        rsi_value, oversold, overbought
                    )
                    
                    classified_rsi[f"RSI_{period}"] = {
                        "value": round(rsi_value, 2),
                        "classification": classification,
                        "oversold_threshold": oversold,
                        "overbought_threshold": overbought
                    }
                    
                    self.logger.info(
                        f"RSI_{period}: {rsi_value:.2f} - {classification} "
                        f"(seuils: {oversold}/{overbought})"
                    )
                else:
                    self.logger.warning(f"Valeur RSI manquante pour période {period}")
                    classified_rsi[f"RSI_{period}"] = {
                        "value": None,
                        "classification": "N/A",
                        "oversold_threshold": config.SIGNAL_CONFIG["RSI_THRESHOLDS"][period]["OVERSOLD"],
                        "overbought_threshold": config.SIGNAL_CONFIG["RSI_THRESHOLDS"][period]["OVERBOUGHT"]
                    }
            
            self.logger.info(f"Calcul RSI terminé pour {symbol}")
            return classified_rsi
            
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul RSI: {e}", exc_info=True)
            return None
    
    def format_rsi_display(self, rsi_data: Dict[str, Dict]) -> str:
        """
        Formate les données RSI pour l'affichage
        
        Args:
            rsi_data: Données RSI calculées
            
        Returns:
            Chaîne formatée pour l'affichage
        """
        self.logger.debug("format_rsi_display called")
        
        if not rsi_data:
            return "RSI: Données non disponibles"
        
        # Déterminer le type de RSI selon la configuration
        rsi_type = "HA" if config.SIGNAL_CONFIG["RSI_ON_HA"] else "Normal"
        
        rsi_parts = []
        
        for rsi_key, rsi_info in rsi_data.items():
            value = rsi_info["value"]
            classification = rsi_info["classification"]
            
            if value is not None:
                # Couleur/symbole selon classification
                if classification == "oversold":
                    symbol = "📈"  # Potentiel d'achat
                elif classification == "overbought":
                    symbol = "📉"  # Potentiel de vente
                else:
                    symbol = "➡️"  # Neutre
                
                rsi_parts.append(f"{rsi_key}: {value} {symbol}")
            else:
                rsi_parts.append(f"{rsi_key}: N/A")
        
        result = f"RSI ({rsi_type}): " + " | ".join(rsi_parts)
        self.logger.debug(f"RSI formaté: {result}")
        
        return result