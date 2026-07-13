# SimpleSpeech

**Offline push-to-talk dictation for Windows.** Hold a hotkey, speak, release it, and SimpleSpeech pastes the transcript into the app you are already using.

## Download and install

1. Open the latest [GitHub Release](https://github.com/Deepak-80085/simplespeech/releases/latest).
2. Download **`SimpleSpeech-Setup-<version>.exe`**.
3. Run the installer and launch SimpleSpeech.
4. Click in any editable field—Notepad, VS Code, a browser, Slack, etc.—then dictate.

The installer creates a Start Menu entry, an uninstaller, and starts the app in the Windows system tray. No Python, terminal, ZIP extraction, or account is required.

> **Windows SmartScreen:** a new unsigned open-source Windows application may display an “Unknown publisher” warning. Only download installers from this repository's GitHub Releases page. Release checksums are published with each release.

## Use

| Action | Result |
| --- | --- |
| Hold **Alt** | Record and paste the raw local transcript. |
| Hold **Alt + Shift** | Record, transcribe locally, then optionally clean the text with local Ollama before pasting. |
| Tray icon → Pause Dictation | Temporarily disable recording. |
| Tray icon → Open Logs | Open local diagnostics if something fails. |
| Tray icon → Quit | Stop SimpleSpeech. |

Hold the hotkey for about 0.3 seconds before speaking. Release **Alt** to finish. The app restores the window that was active when recording began, then pastes the result.

## Privacy and local processing

- Raw dictation uses **faster-whisper** on your computer. Audio is not sent to a transcription API.
- The Whisper model is downloaded once on first use and stored in the normal local model cache. Subsequent transcription works offline.
- Temporary recordings are created under your per-user SimpleSpeech data directory and deleted after processing.
- **Refined mode is optional.** It sends text only to the Ollama server configured on your own machine (`http://localhost:11434` by default); it never calls a hosted LLM service.
- SimpleSpeech writes a small rotating diagnostic log at `%LOCALAPPDATA%\SimpleSpeech\simplespeech.log`. It does not retain transcripts.

## System requirements

- Windows 10 or Windows 11
- A working microphone
- Internet only for the first Whisper-model download (unless its cache is already present)
- NVIDIA GPU optional; SimpleSpeech automatically falls back to CPU
- Ollama plus `qwen3.5:0.8b` only for **Alt + Shift** refined mode

SimpleSpeech is intentionally **Windows-first** today. macOS, Linux, and Android are not supported releases yet.

## Refined mode (optional)

Raw dictation works without Ollama. To enable refinement:

```powershell
ollama pull qwen3.5:0.8b
ollama serve
```

If Ollama is unavailable, SimpleSpeech safely pastes the raw local transcript and shows a brief status message.

The refiner model can be changed for local development with:

```powershell
$env:OLLAMA_MODEL = "qwen3.5:0.8b"
```

## Development

```powershell
# Windows PowerShell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

### Build the desktop application

```powershell
pip install pyinstaller==6.19.0
pyinstaller --clean --noconfirm SimpleSpeech.spec
```

The application folder is created at `dist\SimpleSpeech\`. It is an input to the installer, not the end-user distribution format.

### Build the one-click installer

Install [Inno Setup](https://jrsoftware.org/isinfo.php), then run:

```powershell
ISCC installer\SimpleSpeech.iss
```

This creates `release\SimpleSpeech-Setup-1.0.2.exe`.

Upgrades replace the installed program files under `%LOCALAPPDATA%\Programs\SimpleSpeech` while preserving `%LOCALAPPDATA%\SimpleSpeech`, including its log and temporary-recording folder. Uninstall removes the program files and intentionally preserves that per-user diagnostic data.

## Architecture

```text
app.py          hotkey workflow, recording, clipboard paste, indicator, tray menu
transcriber.py  local faster-whisper model loading and GPU-to-CPU fallback
refiner.py      optional local Ollama/qwen3.5:0.8b cleanup
runtime.py      per-user application paths and bounded diagnostic logging
installer/      Inno Setup script for a normal Windows installer
```

## Troubleshooting

- **No transcript / microphone error:** check Windows Settings → Privacy & security → Microphone and confirm the selected/default input device works.
- **Slow first launch:** the local Whisper model may be downloading or loading for the first time.
- **GPU unavailable:** this is safe; SimpleSpeech uses CPU automatically.
- **Alt shortcut conflict:** SimpleSpeech ignores Alt cycles used with another non-modifier key before recording starts. Use the tray menu to pause it if needed.
- **Refined mode pastes raw text:** make sure Ollama is running and `qwen3.5:0.8b` is installed. Raw dictation is unaffected.
- **Paste fails in an elevated application:** run SimpleSpeech with the same Windows privilege level as the target app.
- **Status overlay error:** install the current release; it includes Pillow’s Tk runtime files required by the status indicator.

Before publishing a release, run the [Windows release smoke-test checklist](docs/windows-release-smoke-test.md) on a Windows machine or separate Windows account.

## License

[MIT](LICENSE)
