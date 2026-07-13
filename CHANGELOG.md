# Changelog

## 1.0.2 — 2026-07-11

- Fix Windows installer packaging by explicitly bundling Pillow’s `ImageTk` module and native `_imagingtk` bridge required by the status overlay.
- Verify frozen release artifacts contain the Silero VAD model and required Pillow/Tk files before installer creation.

## 1.0.1 — 2026-07-11

- Fix Windows installer packaging by including the faster-whisper Silero VAD ONNX asset required for voice activity detection.

## 1.0.0 — 2026-07-11

- First Windows installer release.
- Offline push-to-talk dictation with local faster-whisper transcription.
- Global **Alt** raw dictation and optional **Alt + Shift** local Ollama refinement.
- NVIDIA GPU acceleration with automatic CPU fallback.
- System-tray controls, status indicator, bounded local diagnostics, and reliable temporary-recording cleanup.
