# VoxKey architecture

```text
Right Ctrl listener
  -> capture original foreground HWND
  -> sounddevice microphone capture
  -> local faster-whisper small.en (GPU when available, same-model CPU fallback)
  -> local Ollama qwen3.5:0.8b writing polish
  -> restore HWND and Ctrl+V polished text
```

The hotkey service and processing worker never access Qt widgets. They publish immutable lifecycle events to `EventBus`. The Qt main thread drains those events to drive the transient HUD, sound feedback, tray status, and settings view. This prevents worker-thread UI access and keeps overlay animation separate from speech latency.

A named Windows mutex permits one VoxKey instance per user session. Runtime data lives under `%LOCALAPPDATA%\VoxKey`; installation lives separately under `%LOCALAPPDATA%\Programs\VoxKey`.
