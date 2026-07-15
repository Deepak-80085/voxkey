"""VoxKey Windows entry point: one local-only hold-to-dictate workflow."""

from __future__ import annotations

import ctypes
import os
import queue
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pyperclip
import sounddevice as sd
from pynput import keyboard
from scipy.io.wavfile import write

from speech_models import SpeechModelManager
from voxkey_events import EventBus, UiEvent
from voxkey_ui import VoxKeyShell, create_qt_application
from voxkey_controller import VoxKeyController
from voxkey_runtime import AppState, VoxKeyRuntime
from writing_model import WritingModelClient

SAMPLE_RATE = 16_000
HOLD_TRIGGER_S = 0.28
# Right Ctrl is deliberately chosen: Alt activates Windows access-key menus in target apps.
DICTATION_KEYS = (keyboard.Key.ctrl_r,)
IS_WINDOWS = os.name == "nt"
_user32 = ctypes.windll.user32 if IS_WINDOWS else None
_kernel32 = ctypes.windll.kernel32 if IS_WINDOWS else None
SW_RESTORE = 9
_INSTANCE_MUTEX_NAME = "Local\\VoxKeySingleInstance"
_instance_mutex_handle = None


def claim_single_instance() -> bool:
    """Allow exactly one VoxKey process per Windows user session."""
    global _instance_mutex_handle
    if _kernel32 is None:
        return True
    _instance_mutex_handle = _kernel32.CreateMutexW(None, False, _INSTANCE_MUTEX_NAME)
    return bool(_instance_mutex_handle) and _kernel32.GetLastError() != 183


def get_foreground_window_handle() -> int | None:
    if _user32 is None:
        return None
    try:
        handle = _user32.GetForegroundWindow()
    except Exception:
        return None
    return int(handle) if handle else None


def restore_foreground_window_handle(target_hwnd: int | None) -> None:
    if _user32 is None or not target_hwnd:
        return
    try:
        if _user32.IsIconic(target_hwnd):
            _user32.ShowWindow(target_hwnd, SW_RESTORE)
        _user32.SetForegroundWindow(target_hwnd)
    except Exception:
        pass


def paste_polished_text(text: str, target_hwnd=None) -> bool:
    """Paste only already-polished text while preserving clipboard where possible."""
    payload = text.strip()
    if not payload:
        return False
    old_clipboard = None
    restore_clipboard = False
    try:
        old_clipboard = pyperclip.paste()
        restore_clipboard = True
    except pyperclip.PyperclipException:
        pass
    pyperclip.copy(payload)
    time.sleep(0.04)
    if target_hwnd:
        restore_foreground_window_handle(target_hwnd)
        time.sleep(0.10)
    controller = keyboard.Controller()
    # Alt was removed as a trigger. Do not synthesize releases for Right Ctrl:
    # pynput can emit a literal "r" when doing so on some Windows layouts.
    time.sleep(0.03)
    controller.press(keyboard.Key.ctrl)
    controller.press("v")
    controller.release("v")
    controller.release(keyboard.Key.ctrl)
    if restore_clipboard:
        time.sleep(0.35)
        try:
            pyperclip.copy(old_clipboard)
        except pyperclip.PyperclipException:
            pass
    return True


class Recorder:
    def __init__(self, recordings_dir: Path):
        self.recordings_dir = recordings_dir
        self.stream = None
        self.chunks = []
        self.lock = threading.Lock()

    def _callback(self, indata, _frames, _time_info, _status):
        with self.lock:
            self.chunks.append(indata.copy())

    def start(self) -> bool:
        with self.lock:
            if self.stream is not None:
                return False
            self.chunks = []
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=self._callback
            )
            try:
                stream.start()
            except Exception:
                try:
                    stream.close()
                finally:
                    self.chunks = []
                raise
            self.stream = stream
        return True

    @staticmethod
    def _stop_stream(stream) -> None:
        error = None
        try:
            stream.stop()
        except Exception as exc:
            error = exc
        try:
            stream.close()
        except Exception as exc:
            error = error or exc
        if error:
            raise error

    def stop_and_save(self) -> Path:
        with self.lock:
            stream, self.stream = self.stream, None
            chunks, self.chunks = self.chunks, []
        if stream is None:
            raise RuntimeError("No active recording")
        self._stop_stream(stream)
        if not chunks:
            raise RuntimeError("No audio captured")
        path = self.recordings_dir / f"recording-{uuid.uuid4().hex}.wav"
        write(str(path), SAMPLE_RATE, np.concatenate(chunks, axis=0))
        return path

    def abort(self) -> None:
        with self.lock:
            stream, self.stream, self.chunks = self.stream, None, []
        if stream is not None:
            try:
                self._stop_stream(stream)
            except Exception:
                pass


class HoldToDictateService:
    """Single Right Ctrl hold hotkey; records only when VoxKey is Ready."""

    def __init__(self, controller: VoxKeyController, runtime: VoxKeyRuntime, logger=None, events=None):
        self.controller = controller
        self.runtime = runtime
        self.logger = logger or runtime.logger()
        self.events = events
        self.recorder = Recorder(runtime.recordings_dir())
        self.hotkey_down = False
        self.recording = False
        self.hotkey_started_at = None
        self.ignore_cycle = False
        self.paste_target_hwnd = None
        self.listener = None
        self.jobs = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True)

    def _emit(self, kind: str, state=None, detail: str | None = None) -> None:
        if self.events:
            self.events.publish(UiEvent(kind, state, detail))

    def start(self) -> None:
        self.worker.start()
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.start()

    def stop(self) -> None:
        if self.listener:
            self.listener.stop()
        self.recorder.abort()
        self.jobs.put(None)
        if self.worker.is_alive():
            self.worker.join(timeout=5)

    def _press(self, key) -> None:
        if key in DICTATION_KEYS:
            if not self.hotkey_down:
                self.hotkey_down = True
                self.hotkey_started_at = time.monotonic()
                self.ignore_cycle = False
                self.paste_target_hwnd = get_foreground_window_handle()
                self.logger.info("Right Ctrl pressed; paste target=%s", self.paste_target_hwnd)
        elif self.hotkey_down and not self.recording:
            self.ignore_cycle = True

    def _release(self, key) -> None:
        if key not in DICTATION_KEYS:
            return
        self.hotkey_down = False
        self.hotkey_started_at = None
        if not self.recording:
            return
        self.recording = False
        target_hwnd, self.paste_target_hwnd = self.paste_target_hwnd, None
        try:
            audio_path = self.recorder.stop_and_save()
            self.logger.info("Recording saved: %s; target=%s", audio_path, target_hwnd)
            self.jobs.put((audio_path, target_hwnd))
            self._emit("capture_stopped", AppState.TRANSCRIBING)
        except Exception as exc:
            self.logger.exception("Recording stop failed")
            detail = f"Microphone needs repair: {exc}"
            self._emit("capture_failed", AppState.NEEDS_REPAIR, detail)
            self.controller._set_state(AppState.NEEDS_REPAIR, detail)

    def tick(self) -> None:
        if (
            self.controller.can_dictate()
            and self.hotkey_down
            and not self.recording
            and not self.ignore_cycle
            and self.hotkey_started_at is not None
            and time.monotonic() - self.hotkey_started_at >= HOLD_TRIGGER_S
        ):
            try:
                self.recording = self.recorder.start()
                if self.recording:
                    self.logger.info("Recording started")
                    self._emit("capture_started", AppState.LISTENING)
                    self.controller._set_state(AppState.LISTENING)
            except Exception as exc:
                self.logger.exception("Recording start failed")
                detail = f"Microphone needs repair: {exc}"
                self._emit("capture_failed", AppState.NEEDS_REPAIR, detail)
                self.controller._set_state(AppState.NEEDS_REPAIR, detail)

    def _work(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            audio_path, target_hwnd = job
            try:
                self.logger.info("Processing recording: %s", audio_path)
                pasted = self.controller.process_audio(audio_path, target_hwnd=target_hwnd)
                self.logger.info("Recording processed; pasted=%s", pasted)
            except Exception:
                self.logger.exception("Unexpected worker failure")
            finally:
                # Preserve the most recent capture for diagnostics; replace it on the next attempt.
                try:
                    latest = self.runtime.data_dir() / "last-dictation.wav"
                    os.replace(audio_path, latest)
                    self.logger.info("Diagnostic recording retained: %s", latest)
                except OSError:
                    pass


def dispatch_ui_events(events: EventBus, shell: VoxKeyShell) -> None:
    """Run in Qt's main thread; pipeline workers only publish immutable events."""
    for event in events.drain():
        shell.handle_event(event)


def main() -> None:
    if not claim_single_instance():
        return
    app = create_qt_application()
    runtime = VoxKeyRuntime()
    runtime.install_exception_logging()
    settings = runtime.load_settings()
    speech = SpeechModelManager(
        runtime, vocabulary_provider=lambda: runtime.load_settings()["vocabulary"]
    )
    writer = WritingModelClient(settings["ollama_model"])
    logger = runtime.logger()
    logger.info("VoxKey starting")
    events = EventBus()
    controller = VoxKeyController(
        speech, writer, paste=paste_polished_text, logger=logger, events=events
    )
    threading.Thread(target=controller.start, daemon=True).start()
    service = HoldToDictateService(controller, runtime, logger=logger, events=events)
    stopped = False

    def shutdown() -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        logger.info("VoxKey shutting down")
        service.stop()
        shell.close()
        app.quit()

    shell = VoxKeyShell(controller, runtime, shutdown)
    service.start()

    from PySide6.QtCore import QTimer

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(service.tick)
    timer.timeout.connect(lambda: dispatch_ui_events(events, shell))
    timer.start()
    app.aboutToQuit.connect(shutdown)
    try:
        app.exec()
    except KeyboardInterrupt:
        shutdown()
    finally:
        shutdown()


if __name__ == "__main__":
    main()
