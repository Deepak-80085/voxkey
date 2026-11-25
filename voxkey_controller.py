"""Ready-gated, one-mode VoxKey dictation pipeline."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from voxkey_events import EventBus, UiEvent
from voxkey_runtime import AppState
from writing_model import WritingModelUnavailable


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
        memory=None,
        edit_watcher=None,
        prepare_runtime: Callable[[Callable[[str], None]], None] | None = None,
    ):
        self.speech = speech
        self.logger = logger
        self.writer = writer
        self.paste = paste
        self.on_state = on_state or (lambda _state, _reason: None)
        self.events = events
        self.clock = clock
        self.memory = memory
        self.edit_watcher = edit_watcher
        self.prepare_runtime = prepare_runtime
        self.state = AppState.STARTING
        self.reason = None
        self._validation_lock = threading.Lock()

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
        self._validate(self.speech.health_check)

    def repair_models(self) -> None:
        self._validate(self.speech.repair)

    def _validate(self, speech_check) -> None:
        if not self._validation_lock.acquire(blocking=False):
            return
        try:
            if self.prepare_runtime:
                self._set_state(AppState.SETUP, "Preparing GPU speech runtime...")
                try:
                    self.prepare_runtime(lambda detail: self._set_state(AppState.SETUP, detail))
                except Exception:
                    # Without the GPU libraries speech still works on the CPU, just slower.
                    if self.logger:
                        self.logger.exception("GPU speech runtime unavailable; speech may use CPU")
            self._set_state(AppState.SETUP, "Preparing local speech model...")
            speech_status = speech_check()
            if not speech_status.ready:
                self._set_state(AppState.NEEDS_REPAIR, speech_status.reason)
                return
            self._set_state(AppState.READY)
        finally:
            self._validation_lock.release()

    def can_dictate(self) -> bool:
        return self.state is AppState.READY

    def process_audio(self, audio_path: Path, target_hwnd=None, app: str | None = None) -> bool:
        if self.state not in (AppState.READY, AppState.LISTENING):
            return False
        if self.edit_watcher:
            self.edit_watcher.cancel()
        started = self.clock()
        try:
            self._emit("transcribing", AppState.TRANSCRIBING)
            self._set_state(AppState.TRANSCRIBING)
            transcript = self.speech.transcribe(audio_path)
            transcribe_finished = self.clock()
            transcribe_ms = round((transcribe_finished - started) * 1000)
            if self.logger:
                self.logger.info(
                    "Transcription completed; chars=%d; elapsed_ms=%d",
                    len(transcript.strip()),
                    transcribe_ms,
                )
            if not transcript.strip():
                self._set_state(AppState.READY)
                return False

            if self.memory:
                try:
                    transcript = self.memory.correct(transcript, app)
                except Exception:
                    if self.logger:
                        self.logger.exception("Local correction memory unavailable")

            self._emit("polishing", AppState.POLISHING)
            self._set_state(AppState.POLISHING)
            snippet = self.memory.snippet_for(transcript) if self.memory else None
            style = self.memory.style_for(app) if self.memory else "standard"
            if snippet is not None:
                polished = snippet
            elif style != "standard":
                polished = self.writer.polish(transcript, style=style)
            else:
                polished = self.writer.polish(transcript)
            polish_finished = self.clock()
            polish_ms = round((polish_finished - transcribe_finished) * 1000)
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
                if self.memory:
                    try:
                        self.memory.remember_output(polished, app)
                    except Exception:
                        if self.logger:
                            self.logger.exception("Could not save local dictation history")
                self._emit("paste_succeeded", AppState.READY, elapsed_ms=elapsed_ms)
                if self.edit_watcher:
                    try:
                        self.edit_watcher.watch(target_hwnd, polished, app)
                    except Exception:
                        if self.logger:
                            self.logger.exception("Could not start edit learning")
            self._set_state(AppState.READY)
            return bool(pasted)
        except WritingModelUnavailable as exc:
            detail = str(exc) or "Local writer temporarily unavailable"
            if self.logger:
                self.logger.exception("Dictation processing failed")
            self._emit("pipeline_failed", AppState.READY, detail)
            self._set_state(AppState.READY)
            return False
        except Exception as exc:
            detail = str(exc) or "Dictation needs repair"
            if self.logger:
                self.logger.exception("Dictation processing failed")
            self._emit("pipeline_failed", AppState.NEEDS_REPAIR, detail)
            self._set_state(AppState.NEEDS_REPAIR, detail)
            return False
