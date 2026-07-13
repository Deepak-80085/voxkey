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
from ui import VoxKeyControlCenter
from voxkey_controller import VoxKeyController
from voxkey_runtime import AppState, VoxKeyRuntime
from writing_model import WritingModelClient

SAMPLE_RATE = 16_000
HOLD_TRIGGER_S = 0.28
IS_WINDOWS = os.name == "nt"
_user32 = ctypes.windll.user32 if IS_WINDOWS else None
SW_RESTORE = 9


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
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=self._callback
            )
            self.stream.start()
        return True

    def stop_and_save(self) -> Path:
        with self.lock:
            stream, self.stream = self.stream, None
        if stream is None:
            raise RuntimeError("No active recording")
        stream.stop()
        stream.close()
        with self.lock:
            chunks, self.chunks = self.chunks, []
        if not chunks:
            raise RuntimeError("No audio captured")
        path = self.recordings_dir / f"recording-{uuid.uuid4().hex}.wav"
        write(str(path), SAMPLE_RATE, np.concatenate(chunks, axis=0))
        return path

    def abort(self) -> None:
        with self.lock:
            stream, self.stream, self.chunks = self.stream, None, []
        if stream is not None:
            stream.stop()
            stream.close()


class HoldToDictateService:
    """Single Alt hold hotkey; records only when VoxKey is Ready."""

    def __init__(self, controller: VoxKeyController, runtime: VoxKeyRuntime):
        self.controller = controller
        self.runtime = runtime
        self.recorder = Recorder(runtime.recordings_dir())
        self.alt_down = False
        self.recording = False
        self.alt_started_at = None
        self.ignore_cycle = False
        self.paste_target_hwnd = None
        self.listener = None
        self.jobs = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True)

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
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            if not self.alt_down:
                self.alt_down = True
                self.alt_started_at = time.monotonic()
                self.ignore_cycle = False
                self.paste_target_hwnd = get_foreground_window_handle()
        elif self.alt_down and not self.recording:
            self.ignore_cycle = True

    def _release(self, key) -> None:
        if key not in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            return
        self.alt_down = False
        self.alt_started_at = None
        if not self.recording:
            return
        self.recording = False
        target_hwnd, self.paste_target_hwnd = self.paste_target_hwnd, None
        try:
            self.jobs.put((self.recorder.stop_and_save(), target_hwnd))
        except Exception as exc:
            self.controller._set_state(AppState.NEEDS_REPAIR, f"Microphone needs repair: {exc}")

    def tick(self) -> None:
        if (
            self.controller.can_dictate()
            and self.alt_down
            and not self.recording
            and not self.ignore_cycle
            and self.alt_started_at is not None
            and time.monotonic() - self.alt_started_at >= HOLD_TRIGGER_S
        ):
            try:
                self.recording = self.recorder.start()
                if self.recording:
                    self.controller._set_state(AppState.LISTENING)
            except Exception as exc:
                self.controller._set_state(AppState.NEEDS_REPAIR, f"Microphone needs repair: {exc}")

    def _work(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            audio_path, target_hwnd = job
            try:
                self.controller.process_audio(audio_path, target_hwnd=target_hwnd)
            finally:
                try:
                    os.remove(audio_path)
                except OSError:
                    pass


def main() -> None:
    runtime = VoxKeyRuntime()
    settings = runtime.load_settings()
    speech = SpeechModelManager(
        runtime, vocabulary_provider=lambda: runtime.load_settings()["vocabulary"]
    )
    writer = WritingModelClient(settings["ollama_model"])
    controller = VoxKeyController(speech, writer, paste=paste_polished_text)
    controller.start()
    center = VoxKeyControlCenter(controller, runtime)
    service = HoldToDictateService(controller, runtime)
    service.start()

    try:
        while True:
            service.tick()
            center.process_events()
            time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


if __name__ == "__main__":
    import tkinter as tk

    main()
