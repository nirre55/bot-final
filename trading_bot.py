#!/usr/bin/env python3
"""
Bot de trading Binance principal
Responsabilité unique : Orchestration des différents composants du bot
"""
import asyncio
import sys
from typing import Dict, Any, Optional
import datetime

import config
from api.binance_client import BinanceAPIClient
from core.display import DataDisplay
from core.logger import setup_logging
from core.rsi_service import RSIService
from core.ha_service import HAService
from websocket.websocket_manager import WebSocketManager

# Configuration de l'encodage pour Windows
if sys.platform == "win32":
    try:
        # Type ignore pour Pylance car reconfigure existe sur Python 3.7+
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except (AttributeError, Exception):
        pass


class BinanceTradingBot:
    """Bot de trading Binance - Orchestrateur principal"""
    
    def __init__(self) -> None:
        """Initialise le bot de trading"""
        self.logger = setup_logging()
        self.binance_client = BinanceAPIClient()
        self.display = DataDisplay()
        self.rsi_service = RSIService()
        self.ha_service = HAService()
        
        # Variables pour gérer la mise à jour des RSI et HA
        self.cached_rsi_data: Optional[Dict[str, Dict]] = None
        self.cached_ha_data: Optional[Dict[str, str]] = None
        self.rsi_displayed_for_current_candle: bool = False
        
        # Le WebSocket manager sera initialisé avec un handler de messages
        self.websocket_manager: WebSocketManager
        self._init_websocket_manager()
        
        self.logger.info("Bot de trading initialisé avec tous ses composants")
    
    def _init_websocket_manager(self) -> None:
        """Initialise le gestionnaire WebSocket avec le handler de messages"""
        self.websocket_manager = WebSocketManager(self._handle_kline_message)
    
    def _handle_kline_message(self, kline_data: Dict[str, Any]) -> None:
        """
        Traite les messages kline reçus du WebSocket
        
        Args:
            kline_data: Données kline du WebSocket
        """
        self.logger.debug("_handle_kline_message called")
        
        try:
            # Vérifier si c'est une fermeture de bougie
            is_candle_closed = kline_data.get('k', {}).get('x', False)
            
            # Afficher les données de prix depuis les klines
            self._display_kline_data(kline_data)
            
            # Calculer et afficher les RSI seulement à la fermeture de bougie
            if is_candle_closed:
                self.logger.info("Fermeture de bougie détectée - Mise à jour des RSI")
                self._calculate_and_display_rsi()
                # Reset du flag pour la nouvelle bougie qui commence
                self.rsi_displayed_for_current_candle = False
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message kline: {e}", exc_info=True)
    
    def _display_kline_data(self, kline_data: Dict[str, Any]) -> None:
        """Affiche les données kline de manière similaire au ticker"""
        self.logger.debug("_display_kline_data called")
        
        try:
            k = kline_data.get('k', {})
            symbol = k.get('s', 'N/A')
            close_price = float(k.get('c', '0'))
            volume = float(k.get('v', '0'))
            price_change_percent = float(k.get('P', '0'))
            
            # Format similaire au ticker
            print(f"{symbol} | Prix: {close_price:.4f} USDT | 24h: {price_change_percent:+6.2f}% | Volume: {volume/1000:>10.2f}K", end=" ")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'affichage des données kline: {e}", exc_info=True)
    
    def _calculate_and_display_rsi(self) -> None:
        """Calcule et affiche les RSI et la couleur HA"""
        self.logger.debug("_calculate_and_display_rsi called")
        
        try:
            # Calculer les RSI pour le symbole configuré
            rsi_data = self.rsi_service.calculate_rsi_for_symbol(
                config.SYMBOL, 
                config.TIMEFRAME
            )
            
            if rsi_data:
                # Mettre à jour le cache RSI
                self.cached_rsi_data = rsi_data
                
                # Formater et afficher les RSI
                rsi_display = self.rsi_service.format_rsi_display(rsi_data)
                print(f"RSI: {rsi_display}")
                
                self.logger.info("RSI calculés et mis à jour")
            else:
                self.logger.warning("Impossible de calculer les RSI")
            
            # Calculer et afficher la couleur HA de la bougie fermée
            self._calculate_and_display_ha()
                
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul RSI: {e}", exc_info=True)
    
    def _calculate_and_display_ha(self) -> None:
        """Calcule et affiche la couleur de la bougie HA fermée"""
        self.logger.debug("_calculate_and_display_ha called")
        
        try:
            # Calculer la couleur HA pour le symbole configuré
            ha_data = self.ha_service.get_latest_ha_candle_color(
                config.SYMBOL,
                config.TIMEFRAME
            )
            
            if ha_data:
                # Mettre à jour le cache HA
                self.cached_ha_data = ha_data
                
                # Formater et afficher la couleur HA
                ha_display = self.ha_service.format_ha_display(ha_data)
                print(f"{ha_display}")
                
                self.logger.info("Couleur HA calculée et affichée")
            else:
                self.logger.warning("Impossible de calculer la couleur HA")
                
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul HA: {e}", exc_info=True)
    
    def _display_account_balance(self) -> None:
        """Récupère et affiche la balance du compte"""
        self.logger.debug("_display_account_balance called")
        balance_data = self.binance_client.get_account_balance()
        self.display.display_balance(balance_data)
    
    async def run_bot(self) -> None:
        """Lance le bot de trading"""
        self.logger.debug("run_bot called")
        self.logger.info("Démarrage du bot de trading")
        
        try:
            # Affichage des informations de démarrage
            self.display.display_startup_info()
            
            # Affichage de la balance
            self._display_account_balance()
            
            # Affichage des informations de connexion
            self.display.display_connection_info()
            self.display.display_reconnection_config()
            
            print("Appuyez sur Ctrl+C pour arrêter le bot\n")

            # Démarrage de la connexion WebSocket pour les klines
            stream = f"{config.SYMBOL.lower()}@kline_{config.TIMEFRAME}"
            uri = f"{config.WEBSOCKET_URL}{stream}"
            
            await self.websocket_manager.connect(uri)

        except KeyboardInterrupt:
            self.logger.info("Arrêt du bot demandé par l'utilisateur")
            print("\n\n[ARRET] Bot arrete par l'utilisateur")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du bot: {e}", exc_info=True)
            print(f"\nErreur lors de l'exécution du bot: {e}")
        finally:
            # Arrêt propre du WebSocket manager
            self.websocket_manager.stop()
            self.display.display_shutdown_info()


def main() -> None:
    """Point d'entrée principal"""
    try:
        bot = BinanceTradingBot()
        asyncio.run(bot.run_bot())
    except KeyboardInterrupt:
        print("\nBot arrêté.")
    except Exception as e:
        print(f"Erreur fatale: {e}")


if __name__ == "__main__":
    main()