# VoxKey V2 Design

## Product

**VoxKey** is an English-only, privacy-first Windows voice typing application.

> Private voice typing. On your device.

It has no account, subscription, cloud transcription, or API key. After first-run model setup, all dictated audio and text processing occurs locally.

## Product contract

VoxKey provides one predictable workflow:

```text
Hold configured hotkey → speak → release → transcribe locally → polish locally → paste
```

VoxKey never exposes a raw dictation mode and never pastes an unpolished transcript. If the required speech or writing model is unavailable, corrupt, downloading, or unhealthy, VoxKey is not ready to dictate and presents a clear repair/setup action.

## Scope

### Included in V2

- English-only dictation.
- One configurable global hold-to-dictate hotkey.
- Local faster-whisper transcription using `small.en` as the required default model.
- CPU-first operation with optional NVIDIA GPU acceleration.
- Required local writing cleanup through a configured Ollama model.
- First-run setup, desktop control center, tray controls, and a floating status indicator.
- Local model health checks, repair actions, and bounded local diagnostics.
- Local personal vocabulary for names, brands, and technical terms.
- Start-with-Windows preference.

### Explicitly excluded from V2

- Raw dictation or a raw fallback.
- `base.en` fallback, download, or selection.
- Cloud transcription, hosted LLMs, accounts, API keys, and subscriptions.
- Non-English models and language selection.
- Dictation history, per-application modes, and voice commands.

## Model architecture

### Speech model

`small.en` is the only required speech model. It provides a better English accuracy baseline than the existing `base.en` model while remaining usable on ordinary CPU-only PCs.

The app manages the model in an explicit VoxKey-owned data directory rather than treating a Hugging Face cache as opaque application state. Before VoxKey becomes ready, it validates that the selected model resolves to a readable `model.bin` and can be opened by faster-whisper on the chosen execution device.

The runtime selects GPU acceleration when it is healthy and supported. GPU failure is logged and retried on CPU using the same `small.en` model. CPU failure does not produce an unhandled exception dialog; it transitions the app to `Needs repair`.

### Writing model

A local Ollama writing model is required before dictation is enabled. Setup detects the Ollama service, ensures a selected model exists, and sends a small health-check request. The writing prompt returns only polished dictated text, preserves names/numbers/facts/meaning, and may apply punctuation, capitalization, paragraph structure, and removal of clearly spoken filler.

If Ollama or its selected model is unavailable, VoxKey enters `Needs repair`. It does not paste an unpolished transcript.

### Personal vocabulary

A local editable vocabulary list supplies phrases such as `Zudio`, `Inno Setup`, and `VoxKey` as a transcription prompt/bias. The list is stored in VoxKey’s local app-data directory and is never uploaded.

## UX architecture

### First-run setup

1. Welcome screen explains local processing and English-only scope.
2. User selects and tests a microphone.
3. VoxKey downloads, validates, and opens `small.en`.
4. VoxKey detects/configures Ollama and validates the required local writing model.
5. User chooses one hold-to-dictate hotkey.
6. User completes a transcribe → polish → paste test in a safe test field.
7. VoxKey enters `Ready` only when all required checks pass.

### Control center

The control center replaces the current tray-only experience. It exposes:

- Current status: `Ready`, `Downloading`, `Listening`, `Transcribing`, `Polishing`, or `Needs repair`.
- Microphone selection/test.
- Hotkey configuration.
- Speech and writing model health with repair controls.
- Personal vocabulary editor.
- Start-with-Windows setting.
- Local-processing/privacy explanation.
- Link to local logs.

### Tray and overlay

The tray menu includes: Open VoxKey, Pause Dictation/Resume Dictation, Repair Models, Open Logs, and Quit.

The floating indicator uses concise states:

```text
● Listening
◌ Transcribing locally
✦ Polishing locally
✓ Pasted
! Needs repair
```

## Runtime state model

```text
Starting → Setting up / Validating → Ready
Ready → Listening → Transcribing → Polishing → Pasted → Ready
Any state → Needs repair
Needs repair → Repairing → Validating → Ready
```

The global hotkey is enabled only in `Ready`. All failure transitions preserve a human-readable reason, write detailed diagnostics to the rotating log, and show a recoverable UI state rather than an exception dialog.

## Data and privacy

VoxKey stores settings, logs, temporary recordings, downloaded-model metadata, and vocabulary below:

```text
%LOCALAPPDATA%\VoxKey\
```

Temporary recordings are deleted after processing. Audio and dictated text are not sent to hosted services. Installer upgrade and uninstall remove program files but intentionally preserve this user data for repair/diagnostics unless the user explicitly chooses data removal in a future release.

## Reliability and validation

- Startup must guard all model initialization errors.
- A model download is usable only after its expected files exist and faster-whisper can open it.
- GPU load errors retry the same `small.en` model on CPU.
- Writing-model health errors block dictation and provide repair guidance.
- Automated tests cover model state transitions, model integrity failure, GPU-to-CPU retry, writing-model unavailability, vocabulary prompt construction, and no-raw-paste behavior.
- Packaging tests validate the frozen app’s required native runtime dependencies.
- Release validation includes the documented physical Windows hotkey/microphone/paste smoke test.

## Acceptance criteria

1. A fresh Windows user can install VoxKey, complete setup, and dictate English using only local models.
2. `small.en` is used; `base.en` is absent from default configuration and fallback behavior.
3. A corrupt or missing speech model results in `Needs repair`, never a PyInstaller exception window.
4. GPU model loading failure falls back to CPU with `small.en`; CPU success reaches Ready.
5. Dictation cannot paste unless transcription and local polishing both succeed.
6. Personal vocabulary can improve recognition of user terms without network access.
7. The UI names and user-facing copy use VoxKey, not SimpleSpeech.
8. Existing core packaging regression checks remain intact through the migration.
