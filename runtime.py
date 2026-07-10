"""Runtime paths and logging for the installed Windows application."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

APP_NAME = "SimpleSpeech"


def app_data_dir() -> Path:
    """Return a per-user data directory without writing beside the executable."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    path = app_data_dir() / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_logging() -> logging.Logger:
    """Configure bounded local diagnostics once per process."""
    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        app_data_dir() / "simplespeech.log",
        maxBytes=512 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
