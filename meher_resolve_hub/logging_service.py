"""Rotating application diagnostics without leaking media contents."""

import logging
from logging.handlers import RotatingFileHandler

from .preferences import user_data_dir


def build_logger():
    logger = logging.getLogger("meher_resolve_hub")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    try:
        folder = user_data_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(str(folder / "resolve-hub.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except Exception:
        logger.addHandler(logging.NullHandler())
    return logger

