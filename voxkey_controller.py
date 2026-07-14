"""Ready-gated, one-mode VoxKey dictation pipeline."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from voxkey_events import EventBus, UiEvent
from voxkey_runtime import AppState


class VoxKeyController:
    def __init__(
        self,
        speech,
        writer,
        paste: Callable[..., bool],
        on_state=None,
        logger=None,
        events: EventBus | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.speech = speech
        self.logger = logger
        self.writer = writer
        self.paste = paste
        self.on_state = on_state or (lambda _state, _reason: None)
        self.events = events
        self.clock = clock
        self.state = AppState.STARTING
        self.reason = None

    def _emit(
        self,
        kind: str,
        state: AppState | None = None,
        detail: str | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        if self.events:
            self.events.publish(UiEvent(kind, state, detail, elapsed_ms))

    def _set_state(self, state: AppState, reason: str | None = None) -> None:
        if self.logger:
            self.logger.info("State: %s; reason=%s", state.value, reason)
        self.state = state
        self.reason = reason
        self._emit("state_changed", state, reason)
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
        started = self.clock()
        try:
            self._emit("transcribing", AppState.TRANSCRIBING)
            self._set_state(AppState.TRANSCRIBING)
            transcript = self.speech.transcribe(audio_path)
            transcribe_ms = round((self.clock() - started) * 1000)
            if self.logger:
                self.logger.info(
                    "Transcription completed; chars=%d; elapsed_ms=%d",
                    len(transcript.strip()),
                    transcribe_ms,
                )
            if not transcript.strip():
                self._set_state(AppState.READY)
                return False

            self._emit("polishing", AppState.POLISHING)
            self._set_state(AppState.POLISHING)
            polished = self.writer.polish(transcript)
            polish_ms = round((self.clock() - started) * 1000)
            if self.logger:
                self.logger.info(
                    "Polishing completed; chars=%d; elapsed_ms=%d",
                    len(polished.strip()),
                    polish_ms,
                )
            if not polished.strip():
                self._set_state(AppState.NEEDS_REPAIR, "Local writer returned no text")
                return False

            pasted = self.paste(polished, target_hwnd=target_hwnd)
            elapsed_ms = round((self.clock() - started) * 1000)
            if self.logger:
                self.logger.info(
                    "Paste attempted; success=%s; target=%s; total_ms=%d",
                    pasted,
                    target_hwnd,
                    elapsed_ms,
                )
            if pasted:
                self._emit("paste_succeeded", AppState.READY, elapsed_ms=elapsed_ms)
            self._set_state(AppState.READY)
            return bool(pasted)
        except Exception as exc:
            detail = str(exc) or "Dictation needs repair"
            if self.logger:
                self.logger.exception("Dictation processing failed")
            self._emit("pipeline_failed", AppState.NEEDS_REPAIR, detail)
            self._set_state(AppState.NEEDS_REPAIR, detail)
            return False
