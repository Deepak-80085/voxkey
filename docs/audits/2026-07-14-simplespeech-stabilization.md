# SimpleSpeech Stabilization Audit — 2026-07-14

## Scope

Read-only code audit plus targeted regression tests for the currently released SimpleSpeech application. VoxKey runtime migration was explicitly excluded.

## Verified evidence

- `python -m unittest discover -s tests -v`: 15 tests passed.
- `python -m compileall -q app.py transcriber.py refiner.py runtime.py startup.py benchmark`: passed.
- `pyinstaller --clean --noconfirm SimpleSpeech.spec`: passed.
- `python tests/test_packaging.py dist/SimpleSpeech`: passed.
- Frozen app validation confirmed the faster-whisper Silero VAD ONNX file and Pillow `_imagingtk` bridge exist.

## Regressions now covered

1. A `model.bin` startup failure is caught, logged, and converted into `Speech model needs repair` rather than escaping model construction.
2. An Alt hold shorter than the trigger interval does not start the microphone.
3. Alt used as a modifier for another key does not start dictation.
4. Stopping a service before it starts does not attempt to join an unstarted worker thread.
5. Empty text does not touch the clipboard or send paste keys.
6. Normal paste restores the prior clipboard contents after sending one paste chord.
7. Clipboard-read failure still permits paste and skips restoration.
8. Offline benchmark text normalization and word error rate calculations are deterministic.

## Remaining manual-only validation

The following require a real Windows desktop because they depend on device drivers, Windows focus policy, or global hooks:

- microphone capture across devices;
- hotkey registration with other desktop applications;
- focus restoration and paste into Notepad, browser, VS Code, elevated applications, and remote-desktop sessions;
- tray/icon lifecycle;
- actual GPU loading and GPU-to-CPU fallback;
- first model download and intentionally corrupted model-cache recovery.

## Known risks still present

- `app.py` remains a large multi-responsibility module (audio, hotkey, paste, tray, and overlay). This is a migration risk, not changed in stabilization.
- Paste/focus uses fixed timing delays; tests verify control flow but not timing reliability on every desktop target.
- The legacy startup guard prevents the top-level exception path but does not yet provide a visual repair UI; that is a VoxKey requirement.
- The existing SimpleSpeech model policy still uses its legacy GPU/CPU model settings. The new `small.en` policy belongs to separately tested VoxKey work.

## Go/no-go for VoxKey

**Go, with isolation:** begin VoxKey as a separate application/package only after preserving SimpleSpeech’s test suite and adding equivalent tests before each migration change. Do not rename or mutate the working SimpleSpeech release in place.
