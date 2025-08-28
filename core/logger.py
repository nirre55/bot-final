"""
Module de logging centralisé
Responsabilité unique : Configuration et gestion des logs
"""
import logging
import logging.handlers
import os
import sys
from typing import Optional

import config


def setup_logging() -> logging.Logger:
    """
    Configure le système de logging centralisé
    
    Returns:
        Logger configuré selon les paramètres de config
    """
    logger = logging.getLogger("TradingBot")
    
    if not config.LOGGING_CONFIG["ENABLED"]:
        logger.disabled = True
        return logger
    
    logger.setLevel(getattr(logging, config.LOGGING_CONFIG["LEVEL"]))
    
    # Supprimer les handlers existants pour éviter les doublons
    if logger.handlers:
        logger.handlers.clear()
    
    # Enhanced format avec module et fonction
    enhanced_format = "%(asctime)s | %(levelname)s | %(module)s.%(funcName)s | %(message)s"
    formatter = logging.Formatter(
        enhanced_format,
        datefmt=config.LOGGING_CONFIG["DATE_FORMAT"]
    )
    
    # Console logging
    if config.LOGGING_CONFIG["CONSOLE_LOGGING"]["ENABLED"]:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File logging
    if config.LOGGING_CONFIG["FILE_LOGGING"]["ENABLED"]:
        _setup_file_logging(logger, formatter)
    
    return logger


def _setup_file_logging(logger: logging.Logger, formatter: logging.Formatter) -> None:
    """
    Configure le logging vers fichier
    
    Args:
        logger: Logger à configurer
        formatter: Formatter à utiliser
    """
    # Créer le dossier logs s'il n'existe pas
    log_dir = os.path.dirname(config.LOGGING_CONFIG["FILE_LOGGING"]["FILENAME"])
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOGGING_CONFIG["FILE_LOGGING"]["FILENAME"],
        maxBytes=config.LOGGING_CONFIG["FILE_LOGGING"]["MAX_BYTES"],
        backupCount=config.LOGGING_CONFIG["FILE_LOGGING"]["BACKUP_COUNT"],
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def get_module_logger(module_name: str) -> logging.Logger:
    """
    Obtient un logger pour un module spécifique
    
    Args:
        module_name: Nom du module
        
    Returns:
        Logger configuré pour le module
    """
    logger = logging.getLogger(module_name)
    
    if not logger.handlers:
        # Hérite du logger parent (TradingBot)
        parent_logger = setup_logging()
        logger.parent = parent_logger
        logger.setLevel(parent_logger.level)
    
    return logger