# src/log/config.py
"""Logger construction.

Nothing runs at import time: the log directory is created when the first logger
is actually requested, not when this module is imported (E-001).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

from src import config

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "outreach.log"

_loggers: Dict[str, logging.Logger] = {}


def get_logger(name: str = "scout") -> logging.Logger:
    """Return a configured logger for `name`, cached per name.

    The previous implementation cached a single `_logger` global and returned it
    for every subsequent call regardless of the name requested. Because
    `src/log/__init__.py` logged a banner at import, the first logger built was
    always named `src.log` — so every module's log line was attributed to
    `src.log`, and the `name` argument was silently inert. Caching per name
    fixes the attribution.
    """
    cached = _loggers.get(name)
    if cached is not None:
        return cached

    level_name = config.get(config.LOG_LEVEL).upper()
    max_bytes = config.get_int(config.LOG_MAX_BYTES)
    backup_count = config.get_int(config.LOG_BACKUP_COUNT)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level_name, logging.DEBUG))
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            DEFAULT_LOG_FILE, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger
