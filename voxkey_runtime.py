"""VoxKey-owned local state, settings, and diagnostics."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import NamedTemporaryFile


class AppState(str, Enum):
    STARTING = "Starting"
    SETUP = "Setting up"
    VALIDATING = "Validating"
    READY = "Ready"
    LISTENING = "Listening"
    TRANSCRIBING = "Transcribing"
    POLISHING = "Polishing"
    NEEDS_REPAIR = "Needs repair"


class VoxKeyRuntime:
    """Own VoxKey data rather than relying on an opaque shared model cache."""

    app_name = "VoxKey"

    def __init__(self) -> None:
        self._logger: logging.Logger | None = None

    def data_dir(self) -> Path:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        path = (Path(base) if base else Path.home() / ".local" / "share") / self.app_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def settings_path(self) -> Path:
        return self.data_dir() / "settings.json"

    def models_dir(self) -> Path:
        path = self.data_dir() / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def recordings_dir(self) -> Path:
        path = self.data_dir() / "recordings"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def default_settings(self) -> dict:
        return {
            "speech_model": "small.en",
            "hotkey": "right_ctrl",
            "microphone": None,
            "ollama_model": "qwen3.5:0.8b",
            "vocabulary": [],
            "start_with_windows": False,
            "sounds_enabled": True,
        }

    def load_settings(self) -> dict:
        settings = self.default_settings()
        try:
            loaded = json.loads(self.settings_path().read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            pass
        return settings

    def save_settings(self, settings: dict) -> None:
        merged = self.default_settings()
        merged.update(settings)
        destination = self.settings_path()
        with NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=destination.parent, suffix=".tmp"
        ) as temporary:
            json.dump(merged, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)

    def logger(self) -> logging.Logger:
        if self._logger is not None:
            return self._logger
        logger = logging.Logger(self.app_name)
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            self.data_dir() / "voxkey.log",
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        self._logger = logger
        return self._logger

    def install_exception_logging(self) -> None:
        logger = self.logger()

        def log_exception(origin, exception_type, exception, traceback) -> None:
            logger.error(
                "Unhandled exception in %s",
                origin,
                exc_info=(exception_type, exception, traceback),
            )

        sys.excepthook = lambda exception_type, exception, traceback: log_exception(
            "main thread", exception_type, exception, traceback
        )
        threading.excepthook = lambda args: log_exception(
            f"thread {args.thread.name if args.thread else 'unknown'}",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
        )
