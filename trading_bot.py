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
from core.cascade_service import CascadeService
from core.tp_service import TPService
from strategies.strategy_manager import StrategyManager
from websocket.websocket_manager import WebSocketManager
from websocket.user_data_manager import UserDataStreamManager

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
        
        # Créer les services avancés
        self.tp_service = TPService(self.binance_client)
        self.cascade_service = CascadeService(self.binance_client, self.tp_service)
        
        # Créer le manager de stratégies
        self.strategy_manager = StrategyManager(self.binance_client)
        
        # Créer les services avec injection des dépendances
        self.signal_service = SignalService(self.cascade_service, self.tp_service)
        self.trading_service = TradingService(self.cascade_service, self.tp_service)
        
        # Configurer les références TradingService pour formatage dynamique
        self.tp_service.set_trading_service_reference(self.trading_service)
        self.cascade_service.set_trading_service_reference(self.trading_service)
        
        # Initialiser la stratégie selon la configuration
        strategy_initialized = self.strategy_manager.initialize_strategy(self.trading_service)
        if not strategy_initialized:
            self.logger.error("❌ Échec initialisation stratégie - Arrêt du bot")
            raise RuntimeError("Impossible d'initialiser la stratégie de trading")
        
        # Variables pour gérer la mise à jour des RSI et HA
        self.cached_rsi_data: Optional[Dict[str, Dict]] = None
        self.cached_ha_data: Optional[Dict[str, str]] = None
        self.rsi_displayed_for_current_candle: bool = False
        self.shutdown_requested: bool = False
        self._signal_count: int = 0
        
        # Le WebSocket manager sera initialisé avec un handler de messages
        self.websocket_manager: WebSocketManager
        self._init_websocket_manager()
        
        # User Data Stream WebSocket pour les exécutions d'ordres
        self.user_data_manager: UserDataStreamManager
        self._init_user_data_manager()
        
        self.logger.info("Bot de trading initialisé avec tous ses composants")
        
        # Précharger les informations du symbole de trading
        self._preload_symbol_information()
    
    def _init_websocket_manager(self) -> None:
        """Initialise le gestionnaire WebSocket avec le handler de messages"""
        self.websocket_manager = WebSocketManager(self._handle_kline_message)
    
    def _init_user_data_manager(self) -> None:
        """Initialise le gestionnaire User Data Stream pour les exécutions d'ordres"""
        self.user_data_manager = UserDataStreamManager(self._handle_order_execution)
        # Définir la référence au trading bot pour accéder au strategy manager
        self.user_data_manager.set_trading_bot_reference(self)
    
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
            # Récupérer la quantité initiale selon la configuration
            initial_qty = self.trading_service.get_initial_trade_quantity(config.SYMBOL)
            qty_mode = config.TRADING_CONFIG["QUANTITY_MODE"]
            qty_type = {"MINIMUM": "minimale", "FIXED": "fixe", "PERCENTAGE": "pourcentage"}.get(qty_mode, qty_mode)
            
            if initial_qty:
                print(f"[TRADING] Symbole: {config.SYMBOL}")
                print(f"[TRADING] Quantité initiale ({qty_type}): {initial_qty}")
                print(f"[TRADING] Type d'ordre: MARKET")
                self.logger.info(f"Informations de trading affichées: {config.SYMBOL} qty={initial_qty} (type: {qty_type})")
            else:
                print(f"[TRADING] ⚠️ Quantité initiale non disponible pour {config.SYMBOL}")
                self.logger.warning("Quantité initiale non disponible pour l'affichage")
                
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
            # Stocker les dernières données kline pour le calcul de quantité
            self._latest_kline_data = kline_data.get('k', {})
            
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
            
            # Afficher l'état cascade s'il est actif
            cascade_display = self.cascade_service.format_cascade_display()
            if cascade_display:
                print(f"{cascade_display}")
            
            # Afficher l'état TP s'il est actif
            tp_display = self.tp_service.format_tp_display()
            if tp_display:
                print(f"{tp_display}")
            
            # Vérifier si des TP ont été exécutés et effectuer le nettoyage automatique
            executed_tp = self.tp_service.check_tp_execution_and_cleanup()
            if executed_tp:
                print(f"🎯 TP {executed_tp} EXÉCUTÉ - Reset complet en cours...")
                # Notifier le service cascade qu'un TP a été exécuté (fermeture complète)
                self.cascade_service.handle_tp_execution(executed_tp)
                # Reset du service de signaux pour permettre nouveau cycle
                self.signal_service.reset_signal()
                print("✅ SYSTÈME RÉINITIALISÉ - Prêt pour nouveau signal")
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection de signaux: {e}", exc_info=True)
    
    def _execute_trade(self, signal: Dict[str, Any]) -> None:
        """Exécute un trade basé sur un signal validé"""
        self.logger.debug("_execute_trade called")
        
        try:
            # Ajouter le prix actuel au signal pour le calcul de quantité basé sur pourcentage
            if hasattr(self, '_latest_kline_data') and self._latest_kline_data:
                current_price = float(self._latest_kline_data.get('c', 0))
                signal['current_price'] = current_price
                self.logger.debug(f"Prix actuel ajouté au signal: {current_price}")
            
            # Exécuter le trade via le manager de stratégies
            order_result = self.strategy_manager.execute_signal(signal, self.trading_service)
            
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
    
    def _handle_order_execution(self, execution_data: Dict[str, Any]) -> None:
        """
        Traite les exécutions d'ordres reçues du User Data Stream
        
        Args:
            execution_data: Données d'exécution du WebSocket
        """
        self.logger.debug("_handle_order_execution called")
        
        try:
            # Transmettre à CascadeService pour traitement
            self.cascade_service.handle_order_execution_from_websocket(execution_data)
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'exécution d'ordre: {e}", exc_info=True)
    
    def _display_account_balance(self) -> None:
        """Récupère et affiche la balance du compte"""
        self.logger.debug("_display_account_balance called")
        balance_data = self.binance_client.get_account_balance()
        self.display.display_balance(balance_data)
    
    async def _cleanup_resources(self) -> None:
        """Nettoie toutes les ressources du bot avant arrêt"""
        self.logger.info("🧹 Début du nettoyage des ressources...")
        
        try:
            # 1. Arrêter les WebSocket managers
            if hasattr(self, 'websocket_manager'):
                self.logger.info("Arrêt du WebSocket manager...")
                self.websocket_manager.stop()
            
            if hasattr(self, 'user_data_manager'):
                self.logger.info("Arrêt du User Data manager...")
                await self.user_data_manager.stop()
            
            # 2. Nettoyer le listen key côté Binance
            if (hasattr(self, 'user_data_manager') and 
                hasattr(self.user_data_manager, 'listen_key') and 
                self.user_data_manager.listen_key):
                try:
                    self.logger.info("Nettoyage du listen key Binance...")
                    self.binance_client.close_listen_key(self.user_data_manager.listen_key)
                except Exception as e:
                    self.logger.warning(f"Erreur nettoyage listen key: {e}")
            
            # 3. Nettoyer le manager de stratégies
            if hasattr(self, 'strategy_manager'):
                self.logger.info("Nettoyage du strategy manager...")
                self.strategy_manager.cleanup()
            
            # 4. Attendre que les tâches se terminent
            self.logger.info("Attente fin des tâches en cours...")
            await asyncio.sleep(0.5)  # Laisser le temps aux connexions de se fermer
            
            self.logger.info("✅ Nettoyage des ressources terminé")
            
        except Exception as e:
            self.logger.error(f"Erreur lors du nettoyage: {e}", exc_info=True)
    
    def _setup_signal_handlers(self) -> None:
        """Configure les gestionnaires de signaux pour un arrêt propre"""
        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Signal {signum} reçu - arrêt demandé")
            self.shutdown_requested = True
            self._signal_count += 1
            
            print(f"\n[SIGNAL] Arrêt demandé ({self._signal_count}/3)...")
            
            # Premier signal: arrêt propre
            if self._signal_count == 1:
                try:
                    # Programmer le nettoyage des ressources
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._cleanup_resources())
                    else:
                        # Si pas de loop en cours, forcer l'arrêt des WebSockets
                        if hasattr(self, 'websocket_manager'):
                            self.websocket_manager.stop()
                        if hasattr(self, 'user_data_manager'):
                            self.user_data_manager.is_running = False
                except Exception as e:
                    self.logger.warning(f"Erreur lors du nettoyage: {e}")
                    
            # Deuxième signal: arrêt plus agressif
            elif self._signal_count == 2:
                print("\n[SIGNAL] Arrêt forcé des WebSockets...")
                if hasattr(self, 'websocket_manager'):
                    self.websocket_manager.stop()
                if hasattr(self, 'user_data_manager'):
                    self.user_data_manager.is_running = False
                    
            # Troisième signal: arrêt brutal
            else:
                print("\n[FORCE] Arrêt brutal du processus...")
                import os
                os._exit(1)
        
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
            
            # Démarrer les deux WebSocket en parallèle
            tasks = [
                asyncio.create_task(self.websocket_manager.connect(uri)),
                asyncio.create_task(self.user_data_manager.start())
            ]
            
            try:
                # Attendre que toutes les tâches se terminent ou qu'une exception soit levée
                await asyncio.gather(*tasks, return_exceptions=True)
            except KeyboardInterrupt:
                # Annuler toutes les tâches
                for task in tasks:
                    task.cancel()
                # Attendre que les tâches se terminent proprement
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        except KeyboardInterrupt:
            self.logger.info("Arrêt du bot demandé par l'utilisateur")
            print("\n\n[ARRET] Bot arrete par l'utilisateur")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du bot: {e}", exc_info=True)
            print(f"\nErreur lors de l'exécution du bot: {e}")
        finally:
            # Nettoyage final et fermeture du bot
            self.logger.info("Nettoyage final et fermeture du bot")
            try:
                # Utiliser notre méthode de nettoyage centralisée
                await self._cleanup_resources()
                self.display.display_shutdown_info()
            except Exception as cleanup_error:
                self.logger.error(f"Erreur lors du nettoyage final: {cleanup_error}", exc_info=True)
                print(f"[ERREUR] Problème lors du nettoyage: {cleanup_error}")
                # Forcer l'arrêt si le nettoyage échoue
                import os
                os._exit(1)


def main() -> None:
    """Point d'entrée principal avec timeout d'arrêt"""
    try:
        bot = BinanceTradingBot()
        
        # Lancer le bot avec timeout d'arrêt
        try:
            asyncio.run(bot.run_bot())
        except KeyboardInterrupt:
            print("\n[ARRET] Arrêt demandé par l'utilisateur...")
            
            # Timeout d'arrêt gracieux: 10 secondes
            print("[ARRET] Nettoyage en cours (timeout: 10s)...")
            try:
                # Essayer un arrêt gracieux avec timeout
                asyncio.run(asyncio.wait_for(bot._cleanup_resources(), timeout=10.0))
                print("[ARRET] ✅ Arrêt gracieux terminé")
            except asyncio.TimeoutError:
                print("[ARRET] ⚠️ Timeout - Arrêt forcé")
                import os
                os._exit(1)
            except Exception as cleanup_error:
                print(f"[ARRET] ❌ Erreur lors du nettoyage: {cleanup_error}")
                import os
                os._exit(1)
                
    except KeyboardInterrupt:
        print("\n[FORCE] Arrêt forcé immédiat")
        import os
        os._exit(1)
    except Exception as e:
        print(f"Erreur fatale: {e}")
        import os
        os._exit(1)


if __name__ == "__main__":
    main()