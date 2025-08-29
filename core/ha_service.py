"""
Service de calcul Heikin Ashi
Responsabilité unique : Orchestration du calcul HA avec données historiques
"""
from typing import Dict, Optional

import config
from api.market_data import MarketDataClient
from indicators.heikin_ashi import HeikinAshi
from core.logger import get_module_logger


class HAService:
    """Service pour calculer les bougies Heikin Ashi"""
    
    def __init__(self) -> None:
        """Initialise le service HA"""
        self.logger = get_module_logger("HAService")
        self.market_data_client = MarketDataClient()
        
        self.logger.debug("HAService initialisé")
    
    def get_latest_ha_candle_color(
        self, 
        symbol: str, 
        interval: str
    ) -> Optional[Dict[str, str]]:
        """
        Obtient la couleur de la dernière bougie HA fermée
        
        Args:
            symbol: Symbole de trading
            interval: Intervalle de temps
            
        Returns:
            Dictionnaire avec couleur HA ou None
        """
        self.logger.debug(f"get_latest_ha_candle_color called: {symbol} {interval}")
        self.logger.info(f"Calcul de la couleur HA pour {symbol}")
        
        try:
            # Récupérer les données historiques (moins que pour RSI)
            self.logger.info(f"Récupération de 50 bougies pour calcul HA")
            historical_data = self.market_data_client.get_historical_data(
                symbol, interval, 50
            )
            
            if historical_data is None or historical_data.empty:
                self.logger.error("Impossible de récupérer les données pour HA")
                return None
            
            # Calculer les bougies HA
            ha_df = HeikinAshi.compute(historical_data)
            
            # Obtenir la dernière bougie HA
            latest_candle = HeikinAshi.get_latest_ha_candle(ha_df)
            
            if latest_candle is None:
                self.logger.warning("Impossible d'obtenir la dernière bougie HA")
                return None
            
            # Retourner seulement les informations essentielles
            ha_info = {
                "color": latest_candle["color"],
                "open": round(float(latest_candle["open"]), 2),
                "close": round(float(latest_candle["close"]), 2)
            }
            
            self.logger.info(f"HA: {ha_info['color']} (O:{ha_info['open']} C:{ha_info['close']})")
            return ha_info
            
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul HA: {e}", exc_info=True)
            return None
    
    def format_ha_display(self, ha_info: Optional[Dict[str, str]]) -> str:
        """
        Formate les données HA pour l'affichage
        
        Args:
            ha_info: Données HA calculées
            
        Returns:
            Chaîne formatée pour l'affichage
        """
        self.logger.debug("format_ha_display called")
        
        if not ha_info:
            return "HA: N/A"
        
        color = ha_info["color"]
        
        # Symboles pour les couleurs
        if color == "green":
            symbol = "🟢"  # Bougie verte (hausse)
        elif color == "red":
            symbol = "🔴"  # Bougie rouge (baisse)
        else:  # doji
            symbol = "⚪"  # Bougie neutre
        
        result = f"HA: {color.upper()} {symbol}"
        self.logger.debug(f"HA formaté: {result}")
        
        return result