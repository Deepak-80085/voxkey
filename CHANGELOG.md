# Changelog

## [Unreleased]

### Changed
- Run `small.en` on CPU only (3.46 s vs 3.51 s on CUDA for a 6.6 s clip); a CUDA context kept the NVIDIA GPU awake and hot for as long as VoxKey ran. `distil-large-v3` still uses CUDA when available.
- Remove the local LLM writer: it changed words in 14/14 benchmark samples and was always discarded, so formatting is now rule-based only. Startup drops from 28-83 s to about 4 s and about 1 GB RAM plus 1 GB VRAM is freed; Ollama is kept only as the CUDA library source for Whisper.
- Transcribe with int8 and read VoxKey WAVs directly (about 9% faster); write WAVs with the standard library instead of SciPy.
- Learn close spelling corrections directly from edits in the target app; read a bounded caret region in long documents and allow two minutes for the edit.
- Add opt-in local learning from short edits to VoxKey's own recent paste, with review for uncertain word changes.
- Add local, reviewable correction memory, bounded dictation history, snippets, and app-specific formatting styles with tray controls.
- Handle explicit single-word spoken backtracks while preserving unrelated dictated words.
- Use fast local formatting for long dictations, already formatted transcripts, and explicit spoken commands instead of rewriting dictated words.
- Guard local writer output against word changes, poor casing, missing punctuation, and truncation; restore preferred vocabulary casing.
- Add spoken bullet points and a local known-text accuracy recorder/benchmark.
- Manage a pinned portable Ollama runtime and `qwen3.5:0.8b` under the VoxKey data directory with no external install or command.
- Add resumable runtime download, SHA-256 verification, private port `11435`, streamed setup progress, and automatic first-run repair.
- Add live Right Ctrl, F8, and F9 hotkey selection plus per-user Windows autostart.
- Allow tagged releases without signing while clearly disclosing unsigned Windows artifacts and their Smart App Control/SmartScreen limitations.
- Remove VoxKey-owned runtime, models, settings, logs, recordings, and autostart state during uninstall.
- Begin microphone capture immediately on Right Ctrl press and discard short taps.
- Add live microphone selection with a system-default fallback.
- Keep `small.en` as the default and allow a per-user `distil-large-v3` selection after measuring its accuracy and GPU use on the target GTX 1650.
- Add automated local Ollama model repair through the installed CLI.
- Add a new VoxKey logo and Windows executable version metadata for 2.2.0.
- Prepare CI to sign the app and installer when certificate secrets are configured.
- Show the compact animated orb only while Right Ctrl is held.
- Use the bundled start and successful-paste MP3 cues.
- Keep the local Ollama writer resident between dictations to reduce warm latency.
- Remove inherited SimpleSpeech source, tests, installer, and packaging configuration.

### Fixed
- Explain first-run local model preparation instead of incorrectly showing the app as ready.
- Disable Hugging Face console progress in the frozen GUI so first-run speech-model downloads can complete.
- Run startup validation and repair outside the Qt main thread.
- Serialize validation and repair attempts.
- Replace corrupt speech-model assets during explicit repair.
- Close microphone streams on start, stop, and shutdown failures.
- Route capture failures through HUD cleanup.
- Isolate test logging from installed-user diagnostics and log unhandled exceptions.
- Log separate transcription, polishing, and total pipeline timings.

## [2.1.0] - 2026-07-14

### Added
- Native Qt system-tray experience and compact local settings window.
- Siri-inspired transient bottom-center dictation HUD for listening, local transcription, polishing, completion, and errors.
- Default-on local sound cues for capture start, successful paste, and actionable errors.
- Lifecycle event bus and stage/total timing diagnostics.
- Public-repository documentation: MIT license, privacy/security/contribution policy, architecture notes, CI/release workflow, and Windows smoke-test procedure.

### Changed
- Existing `small.en` local speech recognition, local Ollama `qwen3.5:0.8b` polishing, Right Ctrl trigger, target-focus restoration, strict no-raw-paste behavior, and single-instance protection remain in force.
- Installer version advances from `2.0.6-test` to `2.1.0` for a safe in-place Windows upgrade.

### Known limitations
- The installer is unsigned; verify its published SHA-256 checksum before installing.
- Windows secure desktop cannot accept input. An unelevated VoxKey process can be blocked by an elevated target application.
