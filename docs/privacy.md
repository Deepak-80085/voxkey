# VoxKey privacy

## Local processing

No audio or text leaves your computer during dictation. VoxKey records from the selected microphone, transcribes on the local machine with faster-whisper `small.en` or the selected local `distil-large-v3`, asks its private local Ollama runtime to format text with `qwen3.5:0.8b`, then pastes the result into the captured target window.

VoxKey has no accounts, telemetry endpoint, analytics SDK, API key, or cloud transcription fallback.

## Local files

All mutable data belongs under `%LOCALAPPDATA%\VoxKey`:

- `settings.json`: local settings such as sound preference.
- `personal-memory.json`: correction rules, up to 20 suggested edits, snippets, app styles, and the last 50 successfully pasted texts. The Personal memory screen can delete rules, suggested edits, snippets, styles, or all saved dictation history.
- `voxkey.log`: lifecycle, error, device, and timing diagnostics. It is rotated locally.
- `models\speech` and `models\speech-distil-large-v3`: VoxKey-owned local speech models.
- `models\writer`: the VoxKey-owned writing model.
- `runtime\ollama`: the pinned, checksum-verified local writer runtime.
- `last-dictation.wav`: the most recent capture retained for troubleshooting. It is overwritten by the next capture. You can delete it at any time.

VoxKey reads the target application's process name when dictation starts to choose any saved app-specific rule or style. If you opt into **Learn from edits**, after a successful paste VoxKey checks the focused editable field in that same window for up to two minutes. It ignores password fields and windows without the pasted text. For long documents, it reads up to 5,000 characters around the caret. It compares that text with the paste to identify a short edit inside that paste. Distinctive names and known vocabulary terms can apply across apps; close ordinary spelling edits apply only in the app where you made them. Broad rewrites and conflicting edits are stored as suggestions until you approve them. Text stays local. Reading pauses while the document is unfocused, and starting another dictation stops the check. Some apps do not expose editable text to Windows UI Automation, so learning may not work there.

## Network use

Normal dictation does not require external network access. First-run setup and repair download the pinned Ollama runtime, speech model, and writing model from their configured upstream sources. Downloads contain runtime/model assets only; VoxKey does not upload recordings or dictated text.

## Clipboard and focus

For paste, VoxKey temporarily places the polished text on the Windows clipboard, sends Ctrl+V to the original target, and attempts to restore the previous clipboard contents. Other applications can have their own clipboard monitoring behavior; VoxKey cannot control that.
