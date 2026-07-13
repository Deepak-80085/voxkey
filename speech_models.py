"""Validated, local-only management for VoxKey's required small.en model."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

from vocabulary import build_initial_prompt
from voxkey_runtime import VoxKeyRuntime

MODEL_NAME = "small.en"
MODEL_REPOSITORY = "Systran/faster-whisper-small.en"


@dataclass(frozen=True)
class SpeechModelStatus:
    ready: bool
    device: str | None
    reason: str | None


class SpeechModelManager:
    """Download and open one explicitly-owned English speech model."""

    def __init__(
        self,
        runtime: VoxKeyRuntime,
        vocabulary_provider: Callable[[], list[str]] | None = None,
        model_loader=WhisperModel,
        downloader=snapshot_download,
        cuda_checker=None,
    ):
        self.runtime = runtime
        self.vocabulary_provider = vocabulary_provider or (lambda: [])
        self.model_loader = model_loader
        self.downloader = downloader
        self.cuda_checker = cuda_checker or self._missing_cuda_runtime
        self.model = None
        self.device = None
        self.logger = runtime.logger()

    def _model_directory(self) -> Path:
        return self.runtime.models_dir() / "speech"

    def _ensure_model(self) -> Path:
        model_dir = self._model_directory()
        self.downloader(
            repo_id=MODEL_REPOSITORY,
            local_dir=str(model_dir),
        )
        return model_dir

    @staticmethod
    def _missing_cuda_runtime() -> list[str]:
        if not hasattr(ctypes, "WinDLL"):
            return ["Windows CUDA loader"]
        missing = []
        for dll_name in ("cublas64_12.dll", "cudnn64_9.dll"):
            try:
                ctypes.WinDLL(dll_name)
            except OSError:
                missing.append(dll_name)
        return missing

    @staticmethod
    def _valid_model_directory(model_dir: Path) -> bool:
        model_file = model_dir / "model.bin"
        return model_file.is_file() and model_file.stat().st_size > 0

    def _load(self, model_dir: Path, device: str, compute_type: str):
        return self.model_loader(
            model_size_or_path=str(model_dir),
            device=device,
            compute_type=compute_type,
        )

    def health_check(self) -> SpeechModelStatus:
        try:
            model_dir = self._ensure_model()
            if not self._valid_model_directory(model_dir):
                raise RuntimeError("VoxKey speech model is missing or empty")

            if not self.cuda_checker():
                try:
                    self.model = self._load(model_dir, "cuda", "int8_float16")
                    self.device = "cuda"
                    return SpeechModelStatus(True, self.device, None)
                except Exception:
                    self.logger.exception("GPU speech model load failed; retrying CPU")

            self.model = self._load(model_dir, "cpu", "int8")
            self.device = "cpu"
            return SpeechModelStatus(True, self.device, None)
        except Exception:
            self.logger.exception("Speech model validation failed")
            self.model = None
            self.device = None
            return SpeechModelStatus(False, None, "Speech model needs repair")

    def repair(self) -> SpeechModelStatus:
        self.model = None
        self.device = None
        return self.health_check()

    def transcribe(self, audio_path: Path) -> str:
        if self.model is None:
            raise RuntimeError("Speech model needs repair")
        try:
            return self._transcribe_once(audio_path)
        except Exception:
            if self.device != "cuda":
                raise
            self.logger.exception("GPU transcription failed; retrying CPU")
            model_dir = self._model_directory()
            self.model = self._load(model_dir, "cpu", "int8")
            self.device = "cpu"
            return self._transcribe_once(audio_path)

    def _transcribe_once(self, audio_path: Path) -> str:
        segments, _ = self.model.transcribe(
            str(audio_path),
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=build_initial_prompt(self.vocabulary_provider()),
        )
        return " ".join(segment.text for segment in segments).strip()
