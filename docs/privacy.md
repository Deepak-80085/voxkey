# VoxKey privacy

## Local processing

No audio or text leaves your computer during dictation. VoxKey records from the selected microphone, transcribes on the local machine with faster-whisper `small.en`, asks the locally running Ollama service to polish text with `qwen3.5:0.8b`, then pastes the polished result into the captured target window.

VoxKey has no accounts, telemetry endpoint, analytics SDK, API key, or cloud transcription fallback.

## Local files

All mutable data belongs under `%LOCALAPPDATA%\VoxKey`:

- `settings.json`: local settings such as sound preference.
- `voxkey.log`: lifecycle, error, device, and timing diagnostics. It is rotated locally.
- `models\speech`: the VoxKey-owned `small.en` model cache.
- `last-dictation.wav`: the most recent capture retained for troubleshooting. It is overwritten by the next capture. You can delete it at any time.

## Network use

Normal dictation does not require external network access. Repairing/downloading the speech model deliberately contacts the configured model source; pulling the required writer model is explicitly performed through local Ollama (`ollama pull qwen3.5:0.8b`).

## Clipboard and focus

For paste, VoxKey temporarily places the polished text on the Windows clipboard, sends Ctrl+V to the original target, and attempts to restore the previous clipboard contents. Other applications can have their own clipboard monitoring behavior; VoxKey cannot control that.
