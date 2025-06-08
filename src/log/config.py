import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Constants and environment configs
DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "outreach.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
MAX_LOG_BYTES = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024))  # 5MB default
BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 2))

# Make sure the log directory exists
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Global logger instance
_logger = None


def get_logger(name: str = "scout") -> logging.Logger:
    global _logger

    if _logger:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    logger.propagate = False  # Avoid duplicate logs in some frameworks

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        )

        # Console handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # File handler (rotating)
        file_handler = RotatingFileHandler(
            DEFAULT_LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _logger = logger
    return logger
