# VoxKey privacy

## Local processing

No audio or text leaves your computer during dictation. VoxKey records from the selected microphone, transcribes on the local machine with faster-whisper `small.en`, asks its private local Ollama runtime to polish text with `qwen3.5:0.8b`, then pastes the polished result into the captured target window.

VoxKey has no accounts, telemetry endpoint, analytics SDK, API key, or cloud transcription fallback.

## Local files

All mutable data belongs under `%LOCALAPPDATA%\VoxKey`:

- `settings.json`: local settings such as sound preference.
- `voxkey.log`: lifecycle, error, device, and timing diagnostics. It is rotated locally.
- `models\speech`: the VoxKey-owned `small.en` model cache.
- `models\writer`: the VoxKey-owned writing model.
- `runtime\ollama`: the pinned, checksum-verified local writer runtime.
- `last-dictation.wav`: the most recent capture retained for troubleshooting. It is overwritten by the next capture. You can delete it at any time.

## Network use

Normal dictation does not require external network access. First-run setup and repair download the pinned Ollama runtime, speech model, and writing model from their configured upstream sources. Downloads contain runtime/model assets only; VoxKey does not upload recordings or dictated text.

## Clipboard and focus

For paste, VoxKey temporarily places the polished text on the Windows clipboard, sends Ctrl+V to the original target, and attempts to restore the previous clipboard contents. Other applications can have their own clipboard monitoring behavior; VoxKey cannot control that.
