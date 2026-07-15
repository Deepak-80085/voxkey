# VoxKey

**Private, local voice typing for Windows.** Hold **Right Ctrl**, speak naturally, release, and VoxKey pastes polished English text back into the app you were using.

VoxKey stays out of sight while idle. A small animated orb appears only while
Right Ctrl is held; it disappears immediately on release while transcription,
polishing, and paste continue locally in the background.

## Local-first by design

- English-only speech recognition using local `small.en` (never `base.en`).
- Local writing polish through Ollama model `qwen3.5:0.8b`.
- No account, subscription, API key, cloud transcription, or raw-text fallback.
- Speech/writer failure means no paste—not an unpolished transcript.

## Requirements

- Windows 10/11 x64
- NVIDIA GPU is optional; VoxKey uses it when the local runtime is available and otherwise uses the same `small.en` model on CPU.
- [Ollama](https://ollama.com/) running locally with:

```powershell
ollama pull qwen3.5:0.8b
```

## Install and use

1. Download `VoxKey-Setup-2.1.0.exe` from Releases.
2. Install for the current Windows user.
3. Start VoxKey. It lives in the system tray when ready.
4. Click into any ordinary app, hold **Right Ctrl** for a moment, speak, then release it.

The tray menu opens settings, toggles sounds, repairs models, opens diagnostics, and quits VoxKey.

> **Unsigned pre-release:** Until the project is code-signed, Windows SmartScreen may show a warning. Verify the release SHA-256 checksum before installing.

## Limitations

- Windows secure-desktop screens (lock screen, UAC prompts, Ctrl+Alt+Del) cannot accept dictation.
- Windows may block input into an elevated application when VoxKey is not elevated. Run VoxKey as administrator only when you specifically need to dictate into an administrator-run app.
- Right Ctrl is currently the fixed dictation trigger. Configurable hotkeys,
  microphone selection, vocabulary editing, autostart, and onboarding are not
  implemented yet.

## Diagnostics and privacy

Settings and diagnostics are stored in `%LOCALAPPDATA%\VoxKey`. The latest diagnostic capture is `%LOCALAPPDATA%\VoxKey\last-dictation.wav`; delete it whenever you want. See [privacy details](docs/privacy.md).

## Build from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm VoxKey.spec
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\VoxKey.iss
```

See [architecture](docs/architecture.md), [Windows smoke testing](docs/windows-v0.1.0-smoke-test.md), [contributing](CONTRIBUTING.md), and [security](SECURITY.md).
