# Configuration principale
import os
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()

SYMBOL: str = "BTCUSDC"  # Symbole
TIMEFRAME: str = "5m"  # Timeframe

# Configuration API Binance
BINANCE_API_KEY: Optional[str] = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY: Optional[str] = os.getenv("BINANCE_SECRET_KEY")

# Configuration WebSocket - FUTURES USDⓈ-M
WEBSOCKET_URL: str = "wss://fstream.binance.com/ws/"

# Configuration de reconnexion automatique
RECONNECTION_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver la reconnexion automatique
    "MAX_ATTEMPTS": 100,  # Nombre maximum de tentatives de reconnexion
    "DELAY_SECONDS": 30,  # Délai entre les tentatives (en secondes)
    "TIMEOUT_SECONDS": 3600,  # Timeout pour considérer la connexion comme perdue
}

# Configuration détection de signaux de trading
SIGNAL_CONFIG: Dict[str, Any] = {
    "RSI_ON_HA": True,  # True: calcul RSI sur données Heikin Ashi, False: calcul RSI normal
    "RSI_THRESHOLDS": {
        3: {"OVERSOLD": 10, "OVERBOUGHT": 90},  # RSI 3: plus sensible
        5: {"OVERSOLD": 20, "OVERBOUGHT": 80},  # RSI 5: standard
        7: {"OVERSOLD": 30, "OVERBOUGHT": 70},  # RSI 7: moins sensible
    },
}

# Configuration des quantités de trading
TRADING_CONFIG: Dict[str, Any] = {
    "QUANTITY_MODE": "MINIMUM",  # "MINIMUM", "FIXED", ou "PERCENTAGE"
    "INITIAL_QUANTITY": 0.002,  # Quantité de départ fixe (mode FIXED)
    "BALANCE_PERCENTAGE": 0.001,  # Pourcentage de la balance à risquer (mode PERCENTAGE) - 0.1%
    "PROGRESSION_MODE": "STEP",  # "DOUBLE" (actuel) ou "STEP" (incrémentation par pas)
}

# Configuration du système de hedging
HEDGING_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver le hedging automatique
    "LOOKBACK_CANDLES": 5,  # Nombre de bougies à analyser pour high/low
    "QUANTITY_MULTIPLIER": 2,  # Multiplicateur de quantité pour l'ordre hedge (2x)
}

# Configuration du système de cascade trading
CASCADE_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver le système de cascade
    "MAX_ORDERS": 10,  # Nombre maximum d'ordres cascade
    "POLLING_INTERVAL_SECONDS": 30,  # Intervalle de vérification des ordres (en secondes)
    "RETRY_ATTEMPTS": 3,  # Nombre de tentatives en cas d'erreur (hors fonds insuffisants)
    "RETRY_DELAY_SECONDS": 5,  # Délai entre les tentatives de retry
}

# Configuration des stratégies de trading
STRATEGY_CONFIG: Dict[str, Any] = {
    "STRATEGY_TYPE": "ACCUMULATOR",  # "ACCUMULATOR" ou "CASCADE_MASTER"
}

# Configuration stratégie ACCUMULATOR
ACCUMULATOR_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver la stratégie accumulator
    "TP_PERCENT": 0.003,  # Pourcentage TP (0.3% par défaut)
    "MAX_ACCUMULATIONS": 10,  # Nombre maximum d'accumulations par côté
    "PRICE_OFFSET": 0.001,  # Offset entre stopPrice et price pour l'ordre limite (0.1%)
}

# Configuration du système Take Profit (CASCADE_MASTER seulement)
TP_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver le système TP
    "BASE_MULTIPLIER": 1.0,  # Multiplicateur de base pour la distance TP (commence à 1x)
    "POSITION_INCREMENT": 0.001,  # Incrément de 0.1% appliqué sur le prix final à chaque position
    "PRICE_OFFSET": 0.001,  # Offset entre stopPrice et price pour l'ordre limite (0.1%)
}

# Configuration du système de logging
LOGGING_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver le logging
    "LEVEL": "INFO",  # Niveau de log: DEBUG, INFO, WARNING, ERROR, CRITICAL
    "FORMAT": "%(asctime)s | %(levelname)s | %(module)s.%(funcName)s | %(message)s",
    "DATE_FORMAT": "%Y-%m-%d %H:%M:%S",
    "FILE_LOGGING": {
        "ENABLED": True,
        "FILENAME": "logs/trading_bot.log",
        "MAX_BYTES": 10485760,  # 10MB (plus petit pour éviter les gros fichiers)
        "BACKUP_COUNT": 10,
    },
    "CONSOLE_LOGGING": {
        "ENABLED": True,
    },
}
