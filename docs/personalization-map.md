# VoxKey personalization baseline (2026-10-04, before 2.4.0)

## Baseline Windows path

Hold hotkey -> `HoldToDictateService` captures the foreground window and 16 kHz
audio (`voxkey_app.py`) -> `VoxKeyController.process_audio` (`voxkey_controller.py`)
-> local `SpeechModelManager` (`speech_models.py`) -> local
`WritingModelClient.polish` (`writing_model.py`) -> clipboard paste into the
captured window (`voxkey_app.py`). The hotkey and worker publish events; the Qt
shell in `voxkey_ui.py` owns the tray and settings. Runtime state is under
`%LOCALAPPDATA%\VoxKey` (`voxkey_runtime.py`).

The writer preserves recognized word order and spelling. It uses a direct local
path for explicit formatting commands, long speech, and speech already
formatted by the recognizer. Other short speech goes to VoxKey's loopback
Ollama writer and falls back to a deterministic formatter if the result changes
words. Neither path can infer what the user intended when speech recognition
hears a different word.

## Baseline personal data

- `settings.json` contains model, hotkey, microphone, vocabulary, startup, and
  sound settings. The vocabulary editor is manual (`VoxKeyRuntime.default_settings`,
  `SettingsActions.set_vocabulary`). The same list biases speech recognition and
  restores preferred casing in the writer.
- `last-dictation.wav` is replaced after each attempt. Logs record lengths,
  timing, failures, and paste target, rather than transcript content
  (`HoldToDictateService._work`, `VoxKeyController.process_audio`).
- At this baseline, there was no correction rule store, snippet store, per-app
  style setting, or reviewable dictation history. These gaps drove the 2.4.0
  additions described in `docs/personal-memory-design.md`.

## Public Flow behavior relevant to this PC

| Behavior | Public evidence | VoxKey gap |
| --- | --- | --- |
| Learn a corrected spelling | [Flow features](https://wisprflow.ai/features) says corrected spellings are added to its dictionary; [dictionary help](https://docs.wisprflow.ai/articles/4052411709-teach-flow-your-words-with-the-dictionary) describes explicit wrong-to-right rules. | Manual vocabulary only. No record of a correction. |
| Snippets | [Flow features](https://wisprflow.ai/features) describes spoken cues that paste saved text. | None. |
| App-specific style | [Flow features](https://wisprflow.ai/features) describes styles by writing context on English desktop. | One global formatter. The target HWND is captured but no app identity reaches the writer. |
| Spoken self-correction | [Flow features](https://wisprflow.ai/features) gives a “2… actually 3” example. | Spoken punctuation and list commands exist; no self-correction handling. |
| History and separate notes | [Flow overview](https://docs.wisprflow.ai/articles/2772472373-what-is-flow) lists History in the Hub and Flow Notes as a separate app feature. | No user-facing history or notes. |

Flow's private model, prompts, correction-detection mechanism, and complete
production architecture are not public. A product feature can be matched
without claiming to reproduce those internals. Flow's overview says internet
is required for its transcription; VoxKey's normal dictation stays local.

## Measured starting point and unknowns

On three prompted clips from this user (32 reference words), `small.en` made
two benchmark word errors and `distil-large-v3` made five. One installed-app
Notepad dictation pasted in 1,594 ms from processing start. These measurements
are recorded in `docs/wispr-flow-research.md`; they do not establish a general
accuracy or speed advantage over Flow. Matched Flow output is unavailable.

Automatic observation of edits in arbitrary target apps has no current hook
and would require application access beyond the existing paste path. A local,
explicit correction action is the first verifiable learning path; ambiguous
sound-alike replacements such as “cash”/“cache” must not be applied globally.
