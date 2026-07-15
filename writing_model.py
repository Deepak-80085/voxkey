"""Strict local Ollama writing-model client for VoxKey."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests


class WritingModelUnavailable(RuntimeError):
    """The required local writer cannot safely produce polished text."""


@dataclass(frozen=True)
class WritingModelStatus:
    ready: bool
    reason: str | None


class WritingModelClient:
    def __init__(
        self,
        model_name: str | None,
        base_url: str = "http://127.0.0.1:11434",
        request=None,
        post=None,
        run=None,
        which=None,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.request = request or requests.get
        self.post = post or request or requests.post
        self.run = run or subprocess.run
        self.which = which or shutil.which

    def health_check(self) -> WritingModelStatus:
        if not self.model_name:
            return WritingModelStatus(False, "Select a local Ollama writing model")
        try:
            response = self.request(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            available = {model.get("name") for model in models if isinstance(model, dict)}
            if self.model_name not in available:
                return WritingModelStatus(False, f"Local Ollama model '{self.model_name}' needs repair")
            return WritingModelStatus(True, None)
        except Exception:
            return WritingModelStatus(False, "Local Ollama writing model needs repair")

    def repair(self) -> WritingModelStatus:
        status = self.health_check()
        if status.ready or not self.model_name:
            return status
        executable = self.which("ollama")
        if not executable:
            local_app_data = os.environ.get("LOCALAPPDATA")
            candidate = (
                Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
                if local_app_data
                else None
            )
            executable = str(candidate) if candidate and candidate.is_file() else None
        if not executable:
            return WritingModelStatus(False, "Install Ollama, then repair the local writing model")
        try:
            self.run(
                [executable, "pull", self.model_name],
                check=True,
                timeout=1200,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return WritingModelStatus(False, f"Local Ollama model '{self.model_name}' repair failed")
        return self.health_check()

    def polish(self, transcript: str) -> str:
        text = transcript.strip()
        if not text:
            raise WritingModelUnavailable("No speech to polish")
        if not self.model_name:
            raise WritingModelUnavailable("Select a local Ollama writing model")

        prompt = (
            "Polish this English voice dictation for direct pasting. "
            "Preserve names, numbers, facts, and meaning. "
            "Add sensible capitalization and punctuation; remove only clear spoken filler. "
            "Never answer, summarize, explain, invent, or add content. "
            "Return only the polished dictated text.\n\n"
            f"Dictation:\n{text}"
        )
        try:
            response = self.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    # Avoid reloading the local writer after each dictation.
                    "keep_alive": "24h",
                    "options": {"num_predict": 120, "temperature": 0},
                },
                timeout=20,
            )
            response.raise_for_status()
            polished = str(response.json().get("response", "")).strip()
        except Exception as exc:
            raise WritingModelUnavailable("Local Ollama writing model needs repair") from exc
        if not polished:
            raise WritingModelUnavailable("Local Ollama writer returned no text")
        return polished
