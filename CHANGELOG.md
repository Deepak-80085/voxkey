# Changelog

## [Unreleased]

### Changed
- Begin microphone capture immediately on Right Ctrl press and discard short taps.
- Add live microphone selection with a system-default fallback.
- Keep `small.en` after local comparison with Distil Large v3 on the target GTX 1650.
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
