# VoxKey architecture

```text
Configurable hold-hotkey listener
  -> capture original foreground HWND
  -> sounddevice microphone capture
  -> local faster-whisper small.en (GPU when available, same-model CPU fallback)
  -> VoxKey-owned Ollama on 127.0.0.1:11435
  -> local qwen3.5:0.8b writing polish
  -> restore HWND and Ctrl+V polished text
```

The hotkey service and processing worker never access Qt widgets. They publish immutable lifecycle events to `EventBus`. The Qt main thread drains those events to drive the transient HUD, sound feedback, tray status, and settings view. This prevents worker-thread UI access and keeps overlay animation separate from speech latency.

A named Windows mutex permits one VoxKey instance per user session. Runtime data lives under `%LOCALAPPDATA%\VoxKey`; installation lives separately under `%LOCALAPPDATA%\Programs\VoxKey`. First-run setup downloads a pinned portable Ollama archive, verifies its SHA-256 digest, extracts it under the VoxKey runtime directory, starts it without a console window, and stores writer models separately from any system Ollama installation.
