"""
Logger setup untuk aplikasi
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR


def setup_logger(name: str = "tiktok_auto") -> logging.Logger:
    """
    Setup logger dengan file dan console handler
    """
    logger = logging.getLogger(name)
    
    # Cegah duplikasi handler
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler dengan rotasi
    log_file = LOGS_DIR / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


# Main logger
logger = setup_logger()
