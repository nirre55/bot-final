"""
Gestionnaire WebSocket
Responsabilité unique : Gestion des connexions WebSocket avec reconnexion automatique
"""
import asyncio
import json
from typing import Any, Callable, Optional

import websockets

import config
from core.logger import get_module_logger


class WebSocketManager:
    """Gestionnaire WebSocket avec reconnexion automatique"""
    
    def __init__(self, message_handler: Callable[[dict], None]) -> None:
        """
        Initialise le gestionnaire WebSocket
        
        Args:
            message_handler: Fonction pour traiter les messages reçus
        """
        self.logger = get_module_logger("WebSocketManager")
        self.message_handler = message_handler
        self.reconnection_attempts: int = 0
        self.is_running: bool = True
        
        self.logger.debug("WebSocketManager initialisé")
    
    def _log_connection_attempt(self, uri: str) -> None:
        """Log les tentatives de connexion"""
        self.logger.debug(f"_log_connection_attempt called with uri={uri}")
        
        if self.reconnection_attempts > 0:
            self.logger.info(
                f"Tentative de reconnexion {self.reconnection_attempts}/{config.RECONNECTION_CONFIG['MAX_ATTEMPTS']}"
            )
            print(f"[RECONNEXION] Tentative {self.reconnection_attempts}/{config.RECONNECTION_CONFIG['MAX_ATTEMPTS']}")
        else:
            self.logger.info(f"Connexion WebSocket à: {uri}")
            print(f"[CONNEXION] WebSocket à: {uri}")

    def _log_connection_success(self) -> None:
        """Log les connexions réussies"""
        self.logger.debug("_log_connection_success called")
        
        if self.reconnection_attempts > 0:
            self.logger.info("Reconnexion WebSocket réussie")
            print("[OK] Reconnexion WebSocket réussie!")
        else:
            self.logger.info("Connexion WebSocket établie avec succès")
            print("[OK] Connexion WebSocket établie avec succès!")

    def _should_stop_reconnection(self) -> bool:
        """Vérifie s'il faut arrêter les reconnexions"""
        max_attempts_reached = self.reconnection_attempts >= config.RECONNECTION_CONFIG["MAX_ATTEMPTS"]
        
        if max_attempts_reached:
            self.logger.error(
                f"Nombre maximum de tentatives atteint: {config.RECONNECTION_CONFIG['MAX_ATTEMPTS']}"
            )
            print(f"\n[ERREUR] Nombre maximum de tentatives de reconnexion atteint ({config.RECONNECTION_CONFIG['MAX_ATTEMPTS']})")
            print("Arrêt du bot...")
            self.is_running = False
        
        return max_attempts_reached

    async def _handle_connection_error(self, error: Exception) -> bool:
        """
        Gère les erreurs de connexion
        
        Args:
            error: Exception survenue
            
        Returns:
            True si doit continuer, False sinon
        """
        self.logger.warning(f"Erreur de connexion: {error}")
        self.reconnection_attempts += 1
        
        if self._should_stop_reconnection():
            return False
            
        print(f"\n[ERREUR] Connexion perdue: {error}")
        print(f"[ATTENTE] Reconnexion dans {config.RECONNECTION_CONFIG['DELAY_SECONDS']} secondes...")
        
        try:
            await asyncio.sleep(config.RECONNECTION_CONFIG["DELAY_SECONDS"])
            return True
        except asyncio.CancelledError:
            self.logger.info("Reconnexion annulée par l'utilisateur")
            print("\n[ARRET] Reconnexion annulée")
            self.is_running = False
            return False

    async def _receive_websocket_data(self, websocket: Any) -> str:
        """
        Reçoit des données du WebSocket avec timeout
        
        Args:
            websocket: Connexion WebSocket
            
        Returns:
            Données reçues
        """
        self.logger.debug("_receive_websocket_data called")
        
        try:
            data = await asyncio.wait_for(
                websocket.recv(), 
                timeout=config.RECONNECTION_CONFIG["TIMEOUT_SECONDS"]
            )
            return data
        except asyncio.TimeoutError:
            self.logger.warning("Timeout WebSocket - aucune donnée reçue, reconnexion nécessaire")
            print("\n[TIMEOUT] Aucune donnée reçue, reconnexion nécessaire")
            raise websockets.exceptions.ConnectionClosed(None, None)

    async def _handle_websocket_connection(self, websocket: Any) -> None:
        """
        Gère une connexion WebSocket active
        
        Args:
            websocket: Connexion WebSocket
        """
        self.logger.debug("_handle_websocket_connection called")
        
        while self.is_running:
            try:
                data = await self._receive_websocket_data(websocket)
                message_data = json.loads(data)
                
                # Traiter le message via le handler fourni
                self.message_handler(message_data)
                
                # Réinitialiser le compteur de reconnexions après succès
                self.reconnection_attempts = 0

            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("Connexion WebSocket fermée")
                print("\n[ERREUR] Connexion WebSocket fermée")
                raise
            except Exception as e:
                self.logger.error(f"Erreur WebSocket: {e}", exc_info=True)
                print(f"\nErreur WebSocket: {e}")
                raise

    async def _single_websocket_connection(self, uri: str) -> None:
        """
        Gère une tentative de connexion WebSocket
        
        Args:
            uri: URI de connexion
        """
        self.logger.debug(f"_single_websocket_connection called with uri={uri}")
        self._log_connection_attempt(uri)
        
        async with websockets.connect(uri) as websocket:
            self._log_connection_success()
            await self._handle_websocket_connection(websocket)

    async def connect(self, uri: str) -> None:
        """
        Connecte au WebSocket avec reconnexion automatique
        
        Args:
            uri: URI de connexion WebSocket
        """
        self.logger.debug(f"connect called with uri={uri}")
        self.logger.info("Démarrage de la connexion WebSocket")
        
        while self.is_running and config.RECONNECTION_CONFIG["ENABLED"]:
            try:
                await self._single_websocket_connection(uri)

            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.WebSocketException,
                    OSError, 
                    ConnectionRefusedError,
                    asyncio.TimeoutError) as e:
                
                should_continue = await self._handle_connection_error(e)
                if not should_continue:
                    break
                    
            except KeyboardInterrupt:
                self.logger.info("Arrêt demandé par l'utilisateur")
                print("\n[ARRET] Arrêt demandé par l'utilisateur")
                self.is_running = False
                break
            except Exception as e:
                self.logger.error(f"Erreur inattendue: {e}", exc_info=True)
                print(f"\n[ERREUR] Erreur inattendue: {e}")
                
                should_continue = await self._handle_connection_error(e)
                if not should_continue:
                    break
    
    def stop(self) -> None:
        """Arrête le gestionnaire WebSocket"""
        self.logger.info("Arrêt du gestionnaire WebSocket demandé")
        self.is_running = False