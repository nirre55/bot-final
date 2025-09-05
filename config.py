# Configuration principale
import os
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()

SYMBOL: str = "BTCUSDC"  # Symbole
TIMEFRAME: str = "1m"  # Timeframe

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
        1: {"OVERSOLD": 10, "OVERBOUGHT": 90},  # RSI 3: plus sensible
        2: {"OVERSOLD": 20, "OVERBOUGHT": 80},  # RSI 5: standard
        3: {"OVERSOLD": 30, "OVERBOUGHT": 70},  # RSI 7: moins sensible
    },
}

# Configuration des quantités de trading
TRADING_CONFIG: Dict[str, Any] = {
    "USE_FIXED_INITIAL_QUANTITY": True,  # True: utilise quantité fixe, False: utilise quantité minimale du symbole
    "INITIAL_QUANTITY": 0.002,  # Quantité de départ fixe (utilisée si USE_FIXED_INITIAL_QUANTITY = True)
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

# Configuration du système Take Profit
TP_CONFIG: Dict[str, Any] = {
    "ENABLED": True,  # Activer/désactiver le système TP
    "MULTIPLIER": 2.0,  # Multiplicateur pour la distance TP (distance = différence prix * multiplier)
    "INCREMENT_PERCENT": 0.001,  # Incrément de 0.1% à chaque ordre cascade
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
        "MAX_BYTES": 1048576,  # 1MB (plus petit pour éviter les gros fichiers)
        "BACKUP_COUNT": 3,
    },
    "CONSOLE_LOGGING": {
        "ENABLED": True,
    },
}
