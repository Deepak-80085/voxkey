"""Validated, local-only management for VoxKey's selected English speech model."""

from __future__ import annotations

import ctypes
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download
from huggingface_hub.utils import tqdm as HuggingFaceTqdm

from vocabulary import build_initial_prompt
from voxkey_runtime import VoxKeyRuntime

MODEL_NAME = "small.en"
MODEL_REPOSITORY = "Systran/faster-whisper-small.en"
SUPPORTED_MODELS = {
    MODEL_NAME: (MODEL_REPOSITORY, "speech", "int8"),  # ~6% faster than int8_float16 on a GTX 1650, same WER
    "distil-large-v3": (
        "Systran/faster-distil-whisper-large-v3",
        "speech-distil-large-v3",
        "int8",
    ),
}


def _read_recording(audio_path: Path):
    """VoxKey's own 16 kHz mono int16 WAVs load directly; anything else goes through FFmpeg."""
    try:
        with wave.open(str(audio_path), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16_000, 1, 2):
                return np.frombuffer(wav.readframes(wav.getnframes()), np.int16).astype(np.float32) / 32768.0
    except (OSError, wave.Error, EOFError):
        pass
    return str(audio_path)


class _SilentTqdm(HuggingFaceTqdm):
    def __init__(self, *args, **kwargs):
        kwargs['disable'] = True
        super().__init__(*args, **kwargs)


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
        dll_directory_adder=None,
        model_name: str = MODEL_NAME,
    ):
        self.runtime = runtime
        self.vocabulary_provider = vocabulary_provider or (lambda: [])
        self.model_loader = model_loader
        self.downloader = downloader
        self.cuda_checker = cuda_checker or self._missing_cuda_runtime
        self.dll_directory_adder = dll_directory_adder or getattr(os, "add_dll_directory", None)
        self.model_name = model_name
        self._dll_directory_handles = []
        self.model = None
        self.device = None
        self.logger = runtime.logger()

    def _model_directory(self) -> Path:
        return self.runtime.models_dir() / SUPPORTED_MODELS[self.model_name][1]

    def _ensure_model(self, force_download: bool = False) -> Path:
        model_dir = self._model_directory()
        if self._valid_model_directory(model_dir) and not force_download:
            return model_dir
        self.downloader(
            repo_id=SUPPORTED_MODELS[self.model_name][0],
            local_dir=str(model_dir),
            force_download=force_download,
            tqdm_class=_SilentTqdm,
        )
        return model_dir

    def _configure_cuda_runtime_search_path(self) -> None:
        """Reuse Ollama's installed CUDA runtime when it is available locally."""
        if not self.dll_directory_adder:
            return
        roots = [self.runtime.runtime_dir() / "ollama" / "lib" / "ollama"]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            roots.append(Path(local_app_data) / "Programs" / "Ollama" / "lib" / "ollama")
        for runtime_root in roots:
            for directory_name in ("cuda_v12", "mlx_cuda_v13"):
                directory = runtime_root / directory_name
                if directory.is_dir():
                    try:
                        self._dll_directory_handles.append(self.dll_directory_adder(str(directory)))
                    except OSError:
                        self.logger.exception("Could not add Ollama CUDA runtime directory: %s", directory)

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

    def health_check(self, force_download: bool = False) -> SpeechModelStatus:
        try:
            if self.model_name not in SUPPORTED_MODELS:
                raise ValueError(f"Unsupported local speech model: {self.model_name}")
            model_dir = self._ensure_model(force_download=force_download)
            if not self._valid_model_directory(model_dir):
                raise RuntimeError("VoxKey speech model is missing or empty")

            self._configure_cuda_runtime_search_path()
            if not self.cuda_checker():
                try:
                    self.model = self._load(model_dir, "cuda", SUPPORTED_MODELS[self.model_name][2])
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
        status = self.health_check()
        if status.ready:
            return status
        return self.health_check(force_download=True)

    def transcribe(self, audio_path: Path, beam_size: int = 1) -> str:
        if self.model is None:
            raise RuntimeError("Speech model needs repair")
        try:
            return self._transcribe_once(audio_path, beam_size)
        except Exception:
            if self.device != "cuda":
                raise
            self.logger.exception("GPU transcription failed; retrying CPU")
            model_dir = self._model_directory()
            self.model = self._load(model_dir, "cpu", "int8")
            self.device = "cpu"
            return self._transcribe_once(audio_path, beam_size)

    def _transcribe_once(self, audio_path: Path, beam_size: int) -> str:
        self.logger.info("Transcribing with device=%s", self.device)
        segments, _ = self.model.transcribe(
            _read_recording(audio_path),
            language="en",
            beam_size=beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=build_initial_prompt(self.vocabulary_provider()),
        )
        return " ".join(segment.text for segment in segments).strip()
