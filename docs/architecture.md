# VoxKey architecture

```text
Configurable hold-hotkey listener
  -> capture original foreground HWND
  -> sounddevice microphone capture
  -> local faster-whisper small.en by default or selected distil-large-v3 (GPU when available, same-model CPU fallback)
  -> local rule-based formatting (no language model)
  -> restore HWND and Ctrl+V polished text
```

Before writing polish, `PersonalMemory` applies literal correction rules. It stores the last 50 successful paste texts, up to 20 review suggestions, snippets, and app-specific formatting choices in `%LOCALAPPDATA%\VoxKey\personal-memory.json`. A saved snippet bypasses formatting, and minimal/bullet-note styles use lighter local formatting. The captured target process name selects app-specific rules. When the user enables edit learning, a separate Windows UI Automation worker reads the focused editable field for up to two minutes after a successful paste. For long documents it reads a bounded region near the caret. It saves close spelling edits and distinctive names for that app and leaves broad or conflicting changes for review.

The hotkey service and processing worker never access Qt widgets. They publish immutable lifecycle events to `EventBus`. The Qt main thread drains those events to drive the transient HUD, sound feedback, tray status, and settings view. This prevents worker-thread UI access and keeps overlay animation separate from speech latency.

The writing stage keeps the speech model's recognized words in order. It removes vocal fillers, applies explicit spoken formatting commands and single-word corrections, then adds local punctuation and capitalization. No language model rewrites the text.

A named Windows mutex permits one VoxKey instance per user session. Runtime data lives under `%LOCALAPPDATA%\VoxKey`; installation lives separately under `%LOCALAPPDATA%\Programs\VoxKey`. First-run setup downloads a pinned portable Ollama archive, verifies its SHA-256 digest, and extracts it under the VoxKey runtime directory only for the CUDA libraries the GPU speech model needs. VoxKey never starts Ollama.
