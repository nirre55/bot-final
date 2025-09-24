"""
Service de détection de signaux de trading
Responsabilité unique : Gestion de la logique de signaux RSI + HA en 2 étapes
"""
from typing import Dict, Optional, Any, Tuple, List
from enum import Enum
from collections import deque

import config
from core.logger import get_module_logger


class SignalState(Enum):
    """États possibles du système de signaux"""
    WAITING = "waiting"  # Attente de condition RSI
    RSI_CONDITION_MET = "rsi_condition_met"  # RSI satisfait, attente confirmation HA
    SIGNAL_CONFIRMED = "signal_confirmed"  # Signal complet validé


class SignalType(Enum):
    """Types de signaux possibles"""
    LONG = "long"
    SHORT = "short"


class SignalService:
    """Service de détection de signaux de trading à 2 étapes"""
    
    def __init__(self, cascade_service=None, tp_service=None) -> None:
        """Initialise le service de signaux"""
        self.logger = get_module_logger("SignalService")

        # Référence au service cascade (injection de dépendance)
        self.cascade_service = cascade_service

        # Référence au service TP (injection de dépendance)
        self.tp_service = tp_service

        # État du système de signaux
        self.current_state: SignalState = SignalState.WAITING
        self.pending_signal_type: Optional[SignalType] = None
        self.confirmed_signal: Optional[Dict[str, Any]] = None

        # Configuration RSI depuis config
        self.rsi_periods = list(config.SIGNAL_CONFIG["RSI_THRESHOLDS"].keys())  # [3, 5, 7]

        # Historique des volumes pour validation
        volume_config = config.SIGNAL_CONFIG.get("VOLUME_VALIDATION", {})
        self.volume_validation_enabled = volume_config.get("ENABLED", False)
        self.volume_lookback_candles = volume_config.get("LOOKBACK_CANDLES", 14)
        self.volume_history: deque = deque(maxlen=self.volume_lookback_candles + 1)  # +1 pour la bougie courante

        self.logger.debug("SignalService initialisé")
        self.logger.info(f"RSI periods configurés: {self.rsi_periods}")
        if self.volume_validation_enabled:
            self.logger.info(f"Validation volume activée: {self.volume_lookback_candles} bougies")

    def update_volume_history(self, volume: float) -> None:
        """
        Met à jour l'historique des volumes

        Args:
            volume: Volume de la bougie fermée
        """
        self.logger.debug(f"update_volume_history called with volume={volume}")

        if self.volume_validation_enabled:
            self.volume_history.append(volume)
            self.logger.debug(f"Volume ajouté à l'historique: {volume:.2f} (total: {len(self.volume_history)})")

    def _validate_volume_condition(self, current_volume: float) -> bool:
        """
        Valide que le volume courant est supérieur à la moyenne des volumes précédents

        Args:
            current_volume: Volume de la bougie de confirmation

        Returns:
            True si validation réussie, False sinon
        """
        self.logger.debug(f"_validate_volume_condition called with current_volume={current_volume}")

        if not self.volume_validation_enabled:
            self.logger.debug("Validation volume désactivée")
            return True

        if len(self.volume_history) < self.volume_lookback_candles:
            self.logger.warning(f"Historique volume insuffisant: {len(self.volume_history)}/{self.volume_lookback_candles}")
            return True  # On laisse passer si pas assez d'historique

        # Calculer la moyenne des volumes précédents (sans la bougie courante)
        previous_volumes = list(self.volume_history)[:-1] if len(self.volume_history) > 0 else []

        if not previous_volumes:
            self.logger.warning("Aucun volume précédent disponible")
            return True

        avg_volume = sum(previous_volumes) / len(previous_volumes)

        volume_valid = current_volume > avg_volume

        self.logger.info(
            f"Validation volume: {current_volume:.2f} vs moyenne {avg_volume:.2f} "
            f"({'VALIDE' if volume_valid else 'INVALIDE'})"
        )

        return volume_valid

    def _check_rsi_oversold_condition(self, rsi_data: Dict[str, Dict]) -> bool:
        """
        Vérifie si TOUS les RSI sont en oversold
        
        Args:
            rsi_data: Données RSI calculées
            
        Returns:
            True si tous les RSI sont oversold
        """
        self.logger.debug("_check_rsi_oversold_condition called")
        
        for period in self.rsi_periods:
            rsi_key = f"RSI_{period}"
            if rsi_key not in rsi_data:
                self.logger.warning(f"RSI {period} manquant dans les données")
                return False
            
            rsi_value = rsi_data[rsi_key]["value"]
            oversold_threshold = config.SIGNAL_CONFIG["RSI_THRESHOLDS"][period]["OVERSOLD"]
            
            # Vérifier que rsi_value n'est pas None
            if rsi_value is None:
                self.logger.warning(f"RSI {period} est None - ignoré")
                return False
            
            if rsi_value > oversold_threshold:
                self.logger.debug(f"RSI {period}: {rsi_value} > {oversold_threshold} (pas oversold)")
                return False
        
        self.logger.info("Condition OVERSOLD satisfaite pour tous les RSI")
        return True
    
    def _check_rsi_overbought_condition(self, rsi_data: Dict[str, Dict]) -> bool:
        """
        Vérifie si TOUS les RSI sont en overbought
        
        Args:
            rsi_data: Données RSI calculées
            
        Returns:
            True si tous les RSI sont overbought
        """
        self.logger.debug("_check_rsi_overbought_condition called")
        
        for period in self.rsi_periods:
            rsi_key = f"RSI_{period}"
            if rsi_key not in rsi_data:
                self.logger.warning(f"RSI {period} manquant dans les données")
                return False
            
            rsi_value = rsi_data[rsi_key]["value"]
            overbought_threshold = config.SIGNAL_CONFIG["RSI_THRESHOLDS"][period]["OVERBOUGHT"]
            
            # Vérifier que rsi_value n'est pas None
            if rsi_value is None:
                self.logger.warning(f"RSI {period} est None - ignoré")
                return False
            
            if rsi_value < overbought_threshold:
                self.logger.debug(f"RSI {period}: {rsi_value} < {overbought_threshold} (pas overbought)")
                return False
        
        self.logger.info("Condition OVERBOUGHT satisfaite pour tous les RSI")
        return True
    
    def _check_ha_confirmation(self, ha_data: Dict[str, str]) -> Optional[SignalType]:
        """
        Vérifie la confirmation HA selon le signal en attente
        
        Args:
            ha_data: Données HA (couleur de bougie)
            
        Returns:
            SignalType si confirmation OK, None sinon
        """
        self.logger.debug("_check_ha_confirmation called")
        
        if not self.pending_signal_type or not ha_data:
            return None
        
        ha_color = ha_data.get("color")
        
        if self.pending_signal_type == SignalType.LONG and ha_color == "green":
            self.logger.info("Confirmation HA VERTE pour signal LONG")
            return SignalType.LONG
        elif self.pending_signal_type == SignalType.SHORT and ha_color == "red":
            self.logger.info("Confirmation HA ROUGE pour signal SHORT")
            return SignalType.SHORT
        else:
            self.logger.debug(f"Pas de confirmation HA: {ha_color} pour signal {self.pending_signal_type.value}")
            return None
    
    def process_market_data(
        self,
        rsi_data: Optional[Dict[str, Dict]],
        ha_data: Optional[Dict[str, str]],
        current_volume: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Traite les données de marché pour détecter les signaux

        Args:
            rsi_data: Données RSI calculées
            ha_data: Données HA (couleur bougie)
            current_volume: Volume de la bougie courante (pour validation)

        Returns:
            Dictionnaire avec signal confirmé ou None
        """
        self.logger.debug(f"process_market_data called - État: {self.current_state.value}")
        
        # Vérifier si cascade active - bloquer les nouveaux signaux
        if self.cascade_service and self.cascade_service.is_cascade_active():
            self.logger.debug("Cascade active - nouveaux signaux ignorés")
            return None
        
        # Vérifier si des TPs sont encore actifs - bloquer les nouveaux signaux
        if self.tp_service and self._are_tp_orders_active():
            self.logger.debug("TPs actifs - nouveaux signaux ignorés")
            return None
        
        if not rsi_data or not ha_data:
            self.logger.debug("Données manquantes - pas de traitement")
            return None
        
        # Machine d'état pour la logique séquentielle
        if self.current_state == SignalState.WAITING:
            return self._handle_waiting_state(rsi_data)
        
        elif self.current_state == SignalState.RSI_CONDITION_MET:
            return self._handle_rsi_condition_met_state(ha_data, current_volume)
        
        elif self.current_state == SignalState.SIGNAL_CONFIRMED:
            # Signal déjà confirmé - attendre qu'il soit consommé
            return self.confirmed_signal
        
        return None
    
    def _handle_waiting_state(self, rsi_data: Dict[str, Dict]) -> Optional[Dict[str, Any]]:
        """Gère l'état d'attente des conditions RSI"""
        self.logger.debug("_handle_waiting_state called")
        
        # Vérifier condition OVERSOLD pour LONG
        if self._check_rsi_oversold_condition(rsi_data):
            self.current_state = SignalState.RSI_CONDITION_MET
            self.pending_signal_type = SignalType.LONG
            self.logger.info("🔄 RSI OVERSOLD détecté - Attente confirmation HA VERTE")
            return None
        
        # Vérifier condition OVERBOUGHT pour SHORT
        elif self._check_rsi_overbought_condition(rsi_data):
            self.current_state = SignalState.RSI_CONDITION_MET
            self.pending_signal_type = SignalType.SHORT
            self.logger.info("🔄 RSI OVERBOUGHT détecté - Attente confirmation HA ROUGE")
            return None
        
        return None
    
    def _handle_rsi_condition_met_state(self, ha_data: Dict[str, str], current_volume: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Gère l'état d'attente de confirmation HA avec validation du volume"""
        self.logger.debug("_handle_rsi_condition_met_state called")

        confirmed_signal_type = self._check_ha_confirmation(ha_data)

        if confirmed_signal_type:
            # Vérifier la condition de volume si configurée
            if current_volume is not None and not self._validate_volume_condition(current_volume):
                self.logger.info(f"❌ Signal {confirmed_signal_type.value.upper()} REJETÉ - Volume insuffisant")
                return None

            # Signal confirmé avec toutes les validations !
            self.current_state = SignalState.SIGNAL_CONFIRMED
            self.confirmed_signal = {
                "type": confirmed_signal_type.value,
                "rsi_periods": self.rsi_periods,
                "ha_color": ha_data.get("color"),
                "volume": current_volume,
                "volume_validated": self.volume_validation_enabled and current_volume is not None,
                "timestamp": None  # Sera ajouté par l'appelant
            }

            volume_info = f" + Volume validé" if self.volume_validation_enabled and current_volume else ""
            self.logger.info(f"✅ SIGNAL {confirmed_signal_type.value.upper()} CONFIRMÉ!{volume_info}")
            return self.confirmed_signal

        return None
    
    def _are_tp_orders_active(self) -> bool:
        """
        Vérifie si des ordres TP sont encore actifs
        
        Returns:
            True si au moins un TP est actif
        """
        self.logger.debug("_are_tp_orders_active called")
        
        if not self.tp_service:
            return False
        
        try:
            tp_status = self.tp_service.get_tp_status()
            
            # Vérifier s'il y a des TPs actifs
            long_tp_active = tp_status.get("long_tp_active", False)
            short_tp_active = tp_status.get("short_tp_active", False)
            
            if long_tp_active or short_tp_active:
                self.logger.info(f"TPs actifs détectés - LONG: {long_tp_active}, SHORT: {short_tp_active}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des TPs actifs: {e}", exc_info=True)
            return False
    
    def reset_signal(self) -> None:
        """Remet à zéro le système de signaux"""
        self.logger.info("Reset du système de signaux")
        self.current_state = SignalState.WAITING
        self.pending_signal_type = None
        self.confirmed_signal = None
    
    def get_current_status(self) -> Dict[str, Any]:
        """
        Retourne l'état actuel du système de signaux
        
        Returns:
            Dictionnaire avec l'état actuel
        """
        return {
            "state": self.current_state.value,
            "pending_signal_type": self.pending_signal_type.value if self.pending_signal_type else None,
            "has_confirmed_signal": self.confirmed_signal is not None
        }
    
    def format_signal_display(self, signal: Optional[Dict[str, Any]]) -> str:
        """
        Formate un signal pour l'affichage
        
        Args:
            signal: Signal confirmé
            
        Returns:
            Chaîne formatée pour l'affichage
        """
        self.logger.debug("format_signal_display called")
        
        if not signal:
            return "Signal: N/A"
        
        signal_type = signal["type"].upper()
        ha_color = signal["ha_color"]
        
        # Emojis selon le type de signal
        if signal_type == "LONG":
            emoji = "🟢📈"
        else:  # SHORT
            emoji = "🔴📉"
        
        result = f"SIGNAL: {signal_type} {emoji} (HA: {ha_color})"
        self.logger.debug(f"Signal formaté: {result}")
        
        return result