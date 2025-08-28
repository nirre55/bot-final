"""
Module d'affichage
Responsabilité unique : Affichage formaté des données
"""
from typing import Dict, List, Any, Optional

import config
from core.logger import get_module_logger


class DataDisplay:
    """Gestionnaire d'affichage des données"""
    
    def __init__(self) -> None:
        """Initialise le gestionnaire d'affichage"""
        self.logger = get_module_logger("DataDisplay")
        self.logger.debug("DataDisplay initialisé")
    
    def display_balance(self, balance_data: Optional[List[Dict[str, Any]]]) -> None:
        """
        Affiche la balance du compte de manière formatée
        
        Args:
            balance_data: Données de balance de l'API
        """
        self.logger.debug("display_balance called")
        
        if balance_data:
            self.logger.info("Affichage de la balance du compte")
            
            print("\n" + "=" * 50)
            print("           BALANCE DU COMPTE BINANCE")
            print("=" * 50)

            displayed_count = 0
            for balance in balance_data:
                if float(balance["balance"]) > 0:
                    asset = balance["asset"]
                    available = float(balance["balance"])
                    wallet_balance = float(
                        balance.get("walletBalance", balance["balance"])
                    )

                    balance_info = f"{asset}: {available:.8f}"
                    print(
                        f"{asset:>10} | Balance: {available:>15.8f} | Portefeuille: {wallet_balance:>15.8f}"
                    )
                    self.logger.info(f"Balance {balance_info}")
                    displayed_count += 1

            print("=" * 50)
            self.logger.debug(f"Affiché {displayed_count} balances non nulles")
        else:
            print("Impossible de recuperer la balance du compte.")
            self.logger.error("Impossible de récupérer la balance du compte")
    
    def display_startup_info(self) -> None:
        """Affiche les informations de démarrage"""
        self.logger.debug("display_startup_info called")
        self.logger.info("Démarrage du Bot de Trading Binance")
        
        print("[DEMARRAGE] Bot de Trading Binance")
        print("-" * 40)

    def display_connection_info(self) -> None:
        """Affiche les informations de connexion"""
        self.logger.debug("display_connection_info called")
        self.logger.info(f"Connexion aux données en temps réel pour {config.SYMBOL}")
        
        print(f"\n[INFO] Connexion aux donnees en temps reel pour {config.SYMBOL}...")

    def display_reconnection_config(self) -> None:
        """Affiche la configuration de reconnexion"""
        self.logger.debug("display_reconnection_config called")
        
        if config.RECONNECTION_CONFIG["ENABLED"]:
            self.logger.info(
                f"Reconnexion automatique activée - Max: {config.RECONNECTION_CONFIG['MAX_ATTEMPTS']}, "
                f"Délai: {config.RECONNECTION_CONFIG['DELAY_SECONDS']}s"
            )
            print(f"[CONFIG] Reconnexion automatique activée")
            print(f"[CONFIG] Max tentatives: {config.RECONNECTION_CONFIG['MAX_ATTEMPTS']}")
            print(f"[CONFIG] Délai: {config.RECONNECTION_CONFIG['DELAY_SECONDS']}s")
            print(f"[CONFIG] Timeout: {config.RECONNECTION_CONFIG['TIMEOUT_SECONDS']}s")
        else:
            self.logger.info("Reconnexion automatique désactivée")
            print("[CONFIG] Reconnexion automatique désactivée")
    
    def display_ticker_data(self, ticker_data: Dict[str, Any]) -> None:
        """
        Affiche les données ticker en temps réel
        
        Args:
            ticker_data: Données ticker du WebSocket
        """
        self.logger.debug("display_ticker_data called")
        
        symbol = ticker_data["s"]
        price = float(ticker_data["c"])
        change_24h = float(ticker_data["P"])
        volume = float(ticker_data["v"])

        self.logger.debug(f"Ticker reçu: {symbol} prix={price} change={change_24h}% volume={volume}")
        
        print(
            f"\r{symbol} | Prix: {price:>10.4f} USDT | 24h: {change_24h:>+6.2f}% | Volume: {volume:>12,.0f}",
            end="",
        )
    
    def display_shutdown_info(self) -> None:
        """Affiche les informations d'arrêt"""
        self.logger.info("Bot arrêté complètement")
        print("[INFO] Bot arrêté complètement")