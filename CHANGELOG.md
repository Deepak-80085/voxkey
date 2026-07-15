# Changelog

## [Unreleased]

### Changed
- Show the compact animated orb only while Right Ctrl is held.
- Use the bundled start and successful-paste MP3 cues.
- Keep the local Ollama writer resident between dictations to reduce warm latency.
- Remove inherited SimpleSpeech source, tests, installer, and packaging configuration.

### Fixed
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
