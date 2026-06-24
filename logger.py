"""Centralized logging for Chaos Collection.

Console: INFO level, only chaos-collection logs (clean output).
File:    DEBUG level, everything including third-party libraries.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "chaos.log"

_initialized = False


def _setup() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # --- Console: INFO+, only our logs, always flush ---
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.addFilter(_ChaosFilter())
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # --- File: DEBUG+, everything ---
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(file_handler)


class _ChaosFilter(logging.Filter):
    """Only allow loggers from our own namespace."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(("main", "ai", "api", "db"))


def get_logger(name: str) -> logging.Logger:
    """Get a logger. All loggers inherit from the configured root."""
    _setup()
    return logging.getLogger(name)
