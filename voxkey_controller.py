"""Ready-gated, one-mode VoxKey dictation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from voxkey_runtime import AppState


class VoxKeyController:
    def __init__(self, speech, writer, paste: Callable[..., bool], on_state=None):
        self.speech = speech
        self.writer = writer
        self.paste = paste
        self.on_state = on_state or (lambda _state, _reason: None)
        self.state = AppState.STARTING
        self.reason = None

    def _set_state(self, state: AppState, reason: str | None = None) -> None:
        self.state = state
        self.reason = reason
        self.on_state(state, reason)

    def start(self) -> None:
        self._set_state(AppState.VALIDATING)
        speech_status = self.speech.health_check()
        if not speech_status.ready:
            self._set_state(AppState.NEEDS_REPAIR, speech_status.reason)
            return
        writer_status = self.writer.health_check()
        if not writer_status.ready:
            self._set_state(AppState.NEEDS_REPAIR, writer_status.reason)
            return
        self._set_state(AppState.READY)

    def repair_models(self) -> None:
        self._set_state(AppState.VALIDATING)
        speech_status = self.speech.repair()
        if not speech_status.ready:
            self._set_state(AppState.NEEDS_REPAIR, speech_status.reason)
            return
        writer_status = self.writer.health_check()
        if not writer_status.ready:
            self._set_state(AppState.NEEDS_REPAIR, writer_status.reason)
            return
        self._set_state(AppState.READY)

    def can_dictate(self) -> bool:
        return self.state is AppState.READY

    def process_audio(self, audio_path: Path, target_hwnd=None) -> bool:
        if self.state not in (AppState.READY, AppState.LISTENING):
            return False
        try:
            self._set_state(AppState.TRANSCRIBING)
            transcript = self.speech.transcribe(audio_path)
            if not transcript.strip():
                self._set_state(AppState.READY)
                return False

            self._set_state(AppState.POLISHING)
            polished = self.writer.polish(transcript)
            if not polished.strip():
                self._set_state(AppState.NEEDS_REPAIR, "Local writer returned no text")
                return False

            pasted = self.paste(polished, target_hwnd=target_hwnd)
            self._set_state(AppState.READY)
            return bool(pasted)
        except Exception as exc:
            self._set_state(AppState.NEEDS_REPAIR, str(exc) or "Dictation needs repair")
            return False
