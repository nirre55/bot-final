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
SIGNAL_CONFIG: Dict[str, Dict[int, Dict[str, int]]] = {
    "RSI_THRESHOLDS": {
        3: {"OVERSOLD": 10, "OVERBOUGHT": 90},  # RSI 3: plus sensible
        5: {"OVERSOLD": 20, "OVERBOUGHT": 80},  # RSI 5: standard
        7: {"OVERSOLD": 30, "OVERBOUGHT": 70},  # RSI 7: moins sensible
    }
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
