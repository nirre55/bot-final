#!/usr/bin/env python3
"""
Bot de trading Binance principal
Responsabilité unique : Orchestration des différents composants du bot
"""
import asyncio
import sys
import signal
from typing import Dict, Any, Optional
import datetime

import config
from api.binance_client import BinanceAPIClient
from core.display import DataDisplay
from core.logger import setup_logging
from core.rsi_service import RSIService
from core.ha_service import HAService
from core.signal_service import SignalService
from core.trading_service import TradingService
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
        self.signal_service = SignalService()
        self.trading_service = TradingService()
        
        # Variables pour gérer la mise à jour des RSI et HA
        self.cached_rsi_data: Optional[Dict[str, Dict]] = None
        self.cached_ha_data: Optional[Dict[str, str]] = None
        self.rsi_displayed_for_current_candle: bool = False
        self.shutdown_requested: bool = False
        
        # Le WebSocket manager sera initialisé avec un handler de messages
        self.websocket_manager: WebSocketManager
        self._init_websocket_manager()
        
        self.logger.info("Bot de trading initialisé avec tous ses composants")
        
        # Précharger les informations du symbole de trading
        self._preload_symbol_information()
    
    def _init_websocket_manager(self) -> None:
        """Initialise le gestionnaire WebSocket avec le handler de messages"""
        self.websocket_manager = WebSocketManager(self._handle_kline_message)
    
    def _preload_symbol_information(self) -> None:
        """Précharge les informations du symbole de trading au démarrage"""
        self.logger.debug("_preload_symbol_information called")
        self.logger.info(f"Préchargement des informations pour {config.SYMBOL}")
        
        try:
            success = self.trading_service.preload_symbol_info(config.SYMBOL)
            
            if success:
                self.logger.info(f"✅ Informations {config.SYMBOL} préchargées avec succès")
                print(f"[INIT] Informations de trading préchargées pour {config.SYMBOL}")
            else:
                self.logger.error(f"❌ Échec du préchargement pour {config.SYMBOL}")
                print(f"[ERREUR] Impossible de précharger les infos de {config.SYMBOL}")
                
        except Exception as e:
            self.logger.error(f"Erreur lors du préchargement: {e}", exc_info=True)
            print(f"[ERREUR] Problème lors du préchargement: {e}")
    
    def _display_trading_info(self) -> None:
        """Affiche les informations de trading préchargées"""
        self.logger.debug("_display_trading_info called")
        
        try:
            # Récupérer la quantité minimale depuis le cache
            min_qty = self.trading_service.get_minimum_trade_quantity(config.SYMBOL)
            
            if min_qty:
                print(f"[TRADING] Symbole: {config.SYMBOL}")
                print(f"[TRADING] Quantité minimale: {min_qty}")
                print(f"[TRADING] Type d'ordre: MARKET")
                self.logger.info(f"Informations de trading affichées: {config.SYMBOL} min={min_qty}")
            else:
                print(f"[TRADING] ⚠️ Quantité minimale non disponible pour {config.SYMBOL}")
                self.logger.warning("Quantité minimale non disponible pour l'affichage")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'affichage des infos trading: {e}", exc_info=True)
            print("[TRADING] ❌ Erreur lors de l'affichage des informations")
    
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
            
            # Traiter les données pour la détection de signaux
            self._process_signal_detection()
                
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
    
    def _process_signal_detection(self) -> None:
        """Traite la détection de signaux avec les données RSI et HA"""
        self.logger.debug("_process_signal_detection called")
        
        try:
            # Traiter avec le service de signaux
            signal = self.signal_service.process_market_data(
                self.cached_rsi_data, 
                self.cached_ha_data
            )
            
            if signal:
                # Signal confirmé - afficher
                signal_display = self.signal_service.format_signal_display(signal)
                print(f"{signal_display}")
                
                self.logger.info(f"Signal de trading détecté: {signal}")
                
                # Exécuter le trade
                self._execute_trade(signal)
                
                # Reset pour chercher le prochain signal
                self.signal_service.reset_signal()
            else:
                # Afficher l'état actuel si pas de signal
                status = self.signal_service.get_current_status()
                if status["state"] != "waiting":
                    self.logger.debug(f"État signal: {status}")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection de signaux: {e}", exc_info=True)
    
    def _execute_trade(self, signal: Dict[str, Any]) -> None:
        """Exécute un trade basé sur un signal validé"""
        self.logger.debug("_execute_trade called")
        
        try:
            # Exécuter le trade avec le service de trading
            order_result = self.trading_service.execute_signal_trade(signal)
            
            if order_result:
                # Trade réussi - afficher le résultat
                trade_display = self.trading_service.format_trade_display(signal, order_result)
                print(f"{trade_display}")
                
                self.logger.info(f"Trade exécuté avec succès: {order_result}")
            else:
                # Trade échoué
                self.logger.error("❌ Échec de l'exécution du trade")
                print("❌ ERREUR: Trade non exécuté")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du trade: {e}", exc_info=True)
            print("❌ ERREUR: Problème lors de l'exécution du trade")
    
    def _display_account_balance(self) -> None:
        """Récupère et affiche la balance du compte"""
        self.logger.debug("_display_account_balance called")
        balance_data = self.binance_client.get_account_balance()
        self.display.display_balance(balance_data)
    
    def _setup_signal_handlers(self) -> None:
        """Configure les gestionnaires de signaux pour un arrêt propre"""
        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Signal {signum} reçu - arrêt demandé")
            self.shutdown_requested = True
            self.websocket_manager.stop()
        
        # Gestion des signaux sur Unix/Linux/Mac
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
    
    async def run_bot(self) -> None:
        """Lance le bot de trading"""
        self.logger.debug("run_bot called")
        self.logger.info("Démarrage du bot de trading")
        
        try:
            # Configuration des gestionnaires de signaux
            self._setup_signal_handlers()
            
            # Affichage des informations de démarrage
            self.display.display_startup_info()
            
            # Affichage de la balance
            self._display_account_balance()
            
            # Affichage des informations de connexion
            self.display.display_connection_info()
            self.display.display_reconnection_config()
            
            # Affichage des informations de trading préchargées
            self._display_trading_info()
            
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
            self.logger.info("Nettoyage final et fermeture du bot")
            self.websocket_manager.stop()
            # Attendre un moment pour que les connexions se ferment proprement
            await asyncio.sleep(1)
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