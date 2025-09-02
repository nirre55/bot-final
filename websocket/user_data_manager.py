"""
WebSocket Manager pour Binance User Data Stream
Responsabilité unique : Écoute en temps réel des exécutions d'ordres
"""
import asyncio
import json
import websockets
from typing import Dict, Any, Optional, Callable
import time

import config
from core.logger import get_module_logger
from api.binance_client import BinanceAPIClient


class UserDataStreamManager:
    """Gestionnaire WebSocket pour les événements utilisateur Binance"""
    
    def __init__(self, order_execution_handler: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialise le gestionnaire User Data Stream
        
        Args:
            order_execution_handler: Callback pour traiter les exécutions d'ordres
        """
        self.logger = get_module_logger("UserDataStream")
        self.binance_client = BinanceAPIClient()
        self.order_execution_handler = order_execution_handler
        
        # État du stream
        self.listen_key: Optional[str] = None
        self.websocket_connection = None
        self.is_running: bool = False
        
        # Gestion des reconnexions
        self.max_reconnect_attempts: int = 100
        self.reconnect_delay: int = 5
        
        self.logger.debug("UserDataStreamManager initialisé")
    
    async def start(self) -> None:
        """Démarre le User Data Stream"""
        self.logger.info("Démarrage du User Data Stream")
        
        try:
            # 1. Créer le listen key
            if not await self._create_listen_key():
                self.logger.error("Impossible de créer le listen key")
                return
            
            # 2. Démarrer la connexion WebSocket
            self.is_running = True
            await self._connect_and_listen()
            
        except Exception as e:
            self.logger.error(f"Erreur lors du démarrage User Data Stream: {e}", exc_info=True)
            self.is_running = False
    
    async def stop(self) -> None:
        """Arrête le User Data Stream"""
        self.logger.info("Arrêt du User Data Stream")
        
        self.is_running = False
        
        # Fermer la connexion WebSocket
        if self.websocket_connection:
            await self.websocket_connection.close()
        
        # Fermer le listen key
        if self.listen_key:
            await self._close_listen_key()
    
    async def _create_listen_key(self) -> bool:
        """
        Crée un listen key pour le User Data Stream
        
        Returns:
            True si succès, False sinon
        """
        self.logger.debug("_create_listen_key called")
        
        try:
            # Créer le listen key via API REST
            listen_key_data = self.binance_client.create_listen_key()
            
            if listen_key_data and isinstance(listen_key_data, dict) and "listenKey" in listen_key_data:
                self.listen_key = listen_key_data["listenKey"]
                if self.listen_key:
                    self.logger.info(f"Listen key créé: {self.listen_key[:10]}...")
                else:
                    self.logger.error("Listen key vide reçu")
                    return False
                return True
            else:
                self.logger.error("Réponse invalide lors de la création du listen key")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la création du listen key: {e}", exc_info=True)
            return False
    
    async def _close_listen_key(self) -> None:
        """Ferme le listen key"""
        if not self.listen_key:
            return
        
        try:
            self.binance_client.close_listen_key(self.listen_key)
            self.logger.info("Listen key fermé")
        except Exception as e:
            self.logger.error(f"Erreur lors de la fermeture du listen key: {e}", exc_info=True)
    
    async def _connect_and_listen(self) -> None:
        """Établit la connexion WebSocket et écoute les messages"""
        reconnect_count = 0
        
        while self.is_running and reconnect_count < self.max_reconnect_attempts:
            try:
                # Construire l'URL WebSocket
                ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"
                self.logger.info(f"Connexion au User Data Stream: {ws_url[:50]}...")
                
                # Établir la connexion
                async with websockets.connect(ws_url) as websocket:
                    self.websocket_connection = websocket
                    self.logger.info("✅ Connexion User Data Stream établie")
                    reconnect_count = 0  # Reset du compteur
                    
                    # Démarrer le keep-alive
                    keep_alive_task = asyncio.create_task(self._keep_alive())
                    
                    try:
                        # Écouter les messages
                        async for message in websocket:
                            if not self.is_running:
                                break
                            # Convertir le message en string si nécessaire
                            if isinstance(message, str):
                                message_str = message
                            elif isinstance(message, (bytes, bytearray)):
                                message_str = bytes(message).decode('utf-8')
                            elif hasattr(message, 'tobytes'):
                                # Pour memoryview
                                message_str = message.tobytes().decode('utf-8')
                            else:
                                message_str = str(message)
                            
                            await self._handle_message(message_str)
                    finally:
                        keep_alive_task.cancel()
                        
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("Connexion User Data Stream fermée")
                if self.is_running:
                    reconnect_count += 1
                    await self._handle_reconnection(reconnect_count)
            except Exception as e:
                self.logger.error(f"Erreur User Data Stream: {e}", exc_info=True)
                if self.is_running:
                    reconnect_count += 1
                    await self._handle_reconnection(reconnect_count)
        
        if reconnect_count >= self.max_reconnect_attempts:
            self.logger.error("Nombre maximum de reconnexions atteint - arrêt du stream")
            self.is_running = False
    
    async def _handle_reconnection(self, attempt: int) -> None:
        """Gère les reconnexions"""
        self.logger.info(f"Tentative de reconnexion #{attempt} dans {self.reconnect_delay}s")
        await asyncio.sleep(self.reconnect_delay)
        
        # Recréer le listen key si nécessaire
        if not await self._create_listen_key():
            self.logger.error("Impossible de recréer le listen key pour la reconnexion")
    
    async def _keep_alive(self) -> None:
        """Maintient le listen key actif toutes les 30 minutes"""
        while self.is_running:
            try:
                await asyncio.sleep(1800)  # 30 minutes
                if self.listen_key and self.is_running:
                    self.binance_client.keep_alive_listen_key(self.listen_key)
                    self.logger.debug("Listen key keep-alive envoyé")
            except Exception as e:
                self.logger.error(f"Erreur keep-alive: {e}", exc_info=True)
    
    async def _handle_message(self, message: str) -> None:
        """
        Traite les messages reçus du User Data Stream
        
        Args:
            message: Message JSON reçu
        """
        try:
            data = json.loads(message)
            event_type = data.get("e")
            
            if event_type == "ORDER_TRADE_UPDATE":
                await self._handle_order_trade_update(data)
            elif event_type == "ACCOUNT_UPDATE":
                await self._handle_account_update(data)
            else:
                self.logger.debug(f"Event non traité: {event_type}")
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message: {e}", exc_info=True)
            self.logger.debug(f"Message problématique: {message}")
    
    async def _handle_order_trade_update(self, data: Dict[str, Any]) -> None:
        """
        Traite un événement ORDER_TRADE_UPDATE de Binance Futures
        
        Args:
            data: Données de l'événement ORDER_TRADE_UPDATE
        """
        try:
            # Structure Binance Futures: les données sont dans l'objet 'o'
            order_data = data.get("o", {})
            
            order_id = order_data.get("i")          # Order ID
            symbol = order_data.get("s")            # Symbol
            side = order_data.get("S")              # Side (BUY/SELL)
            order_status = order_data.get("X")      # Order Status (NEW, FILLED, etc.)
            execution_type = order_data.get("x")    # Execution Type (NEW, TRADE, CANCELED)
            order_type = order_data.get("o")        # Order Type (MARKET, STOP_MARKET, etc.)
            cumulative_qty = order_data.get("z", "0")  # Cumulative filled quantity
            original_qty = order_data.get("q", "0")    # Original quantity
            last_fill_price = order_data.get("L", "0") # Last fill price
            position_side = order_data.get("ps", "BOTH") # Position side (LONG/SHORT/BOTH)
            
            self.logger.info(f"🔔 ORDER_TRADE_UPDATE: {symbol} {side} {order_type} ID:{order_id}")
            self.logger.info(f"   Status: {order_status}, Execution: {execution_type}")
            self.logger.info(f"   Qty: {cumulative_qty}/{original_qty}, Price: {last_fill_price}")
            
            # Ne traiter que les ordres FILLED de notre symbole
            if order_status == "FILLED" and symbol == config.SYMBOL:
                self.logger.info(f"✅ Ordre FILLED détecté: {side} {cumulative_qty} {symbol} @ {last_fill_price}")
                
                # Créer un objet compatible avec le handler cascade
                execution_data = {
                    "i": str(order_id),                    # Order ID
                    "s": symbol,                           # Symbol
                    "S": side,                             # Side (BUY/SELL)
                    "X": order_status,                     # Order status
                    "z": cumulative_qty,                   # Executed quantity
                    "L": last_fill_price,                  # Last executed price
                    "ps": position_side                    # Position side
                }
                
                # Appeler le handler si défini (directement dans la boucle d'événements)
                if self.order_execution_handler:
                    self.order_execution_handler(execution_data)
                    
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement ORDER_TRADE_UPDATE: {e}", exc_info=True)
            self.logger.debug(f"Données problématiques: {data}")
    
    async def _handle_account_update(self, data: Dict[str, Any]) -> None:
        """
        Traite une mise à jour de compte ACCOUNT_UPDATE
        
        Args:
            data: Données de compte
        """
        try:
            self.logger.debug("Mise à jour de compte ACCOUNT_UPDATE reçue")
            # Pour l'instant, juste logger - peut être utilisé pour validation des positions
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement ACCOUNT_UPDATE: {e}", exc_info=True)