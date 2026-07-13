# SimpleSpeech Stabilization and Offline Engine Benchmark Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing SimpleSpeech release testable and safe against known startup/pipeline failures before building VoxKey separately, while creating a reproducible English-only offline transcription benchmark for future engine decisions.

**Architecture:** Preserve the current SimpleSpeech user behavior during stabilization. Extract only narrow, testable startup and pipeline seams where an audit-confirmed failure requires it. The benchmark is a separate tool: it accepts local WAV fixtures and transcripts, measures each installed offline engine/model, and records word error rate and latency without modifying the release runtime.

**Tech Stack:** Python 3.12, unittest, faster-whisper/CTranslate2, pynput, sounddevice, PyInstaller, local WAV fixtures.

## Global Constraints

- Do not change the installed `SimpleSpeech 1.0.2` runtime behavior without a failing regression test.
- Do not rename or package VoxKey during this phase.
- Do not modify untracked `index.html`.
- No cloud APIs, user accounts, or hosted model inference.
- Do not claim hardware microphone/hotkey/paste validation is automated.

---

### Task 1: Add test seams for startup model initialization

**Files:**
- Create: `startup.py`
- Create: `tests/test_startup.py`
- Modify: `app.py`

**Interfaces:**
- `start_transcriber(factory: Callable[[], object]) -> tuple[object | None, str | None]`
- Returns `(transcriber, None)` on success or `(None, "Speech model needs repair")` on any model initialization exception after logging it.

- [ ] Write a failing test where `factory` raises `RuntimeError("Unable to open file model.bin")` and assert no exception escapes and the repair message is returned.
- [ ] Run `python -m unittest tests.test_startup -v`; verify RED.
- [ ] Implement `startup.py` and call it in `run_hotkey_mode()` before creating the service.
- [ ] On startup failure, show a user-readable message and keep the process alive long enough for tray/log access instead of allowing a PyInstaller exception dialog.
- [ ] Run the test again; verify GREEN.
- [ ] Commit `test: guard model startup failures`.

### Task 2: Cover hotkey state and queue behavior without a microphone

**Files:**
- Create: `tests/test_hotkey_service.py`
- Modify: `app.py` only if tests expose a real defect

**Interfaces:**
- Construct `HotkeyDictationService` with fake recorder/transcriber/refiner/indicator/paste controller.
- Verify state transitions through public event methods and `tick()`.

- [ ] Write a failing test confirming Alt held below `ALT_HOLD_TRIGGER_S` never starts recording.
- [ ] Write a failing test confirming Alt used with a non-modifier key is ignored.
- [ ] Write a failing test confirming a later pending recording removes the earlier temporary recording when `KEEP_ONLY_LATEST_PENDING_JOB` is enabled.
- [ ] Write a failing test confirming `stop()` signals the worker and does not hang when the queue is empty.
- [ ] Run the new test file; verify failures describe missing test seams or actual defects.
- [ ] Make minimum dependency-injection/extraction changes required for green tests; preserve current hotkey behavior.
- [ ] Run `python -m unittest tests.test_hotkey_service -v`; verify GREEN.
- [ ] Commit `test: cover hotkey queue lifecycle`.

### Task 3: Cover paste/focus/clipboard behavior

**Files:**
- Create: `tests/test_paste.py`
- Modify: `app.py` only if tests expose a real defect

**Interfaces:**
- Test `paste_text_at_cursor(text, key_controller, target_hwnd)` with mocked clipboard, Windows focus functions, sleep, and keyboard controller.

- [ ] Write a failing test confirming blank text does not access clipboard or send paste keys.
- [ ] Write a failing test confirming nonblank text restores clipboard when readable and sends exactly one paste chord.
- [ ] Write a failing test confirming clipboard read failure still pastes and does not attempt restoration.
- [ ] Run tests; verify RED.
- [ ] Correct only test-exposed behavior.
- [ ] Run tests; verify GREEN.
- [ ] Commit `test: cover paste and clipboard recovery`.

### Task 4: Guard packaged startup and runtime asset failures

**Files:**
- Modify: `tests/test_packaging.py`
- Modify: `docs/windows-release-smoke-test.md`

- [ ] Add a failing test that asserts the frozen folder has the VAD ONNX asset and Pillow `_imagingtk*.pyd` bridge.
- [ ] Add a testable release checklist entry: start the installed app before dictation and assert no exception dialog appears.
- [ ] Run packaging tests; verify RED if any required assertion is absent.
- [ ] Implement the assertions/checklist update.
- [ ] Build the app with PyInstaller, execute the frozen artifact validator, and run tests.
- [ ] Commit `test: guard packaged startup dependencies`.

### Task 5: Create an offline English transcription benchmark

**Files:**
- Create: `benchmark/README.md`
- Create: `benchmark/run_benchmark.py`
- Create: `benchmark/fixtures/manifest.json`
- Create: `tests/test_benchmark.py`

**Interfaces:**
- Manifest entries: `{ "audio": "fixtures/name.wav", "expected": "expected English transcript" }`.
- CLI: `python benchmark/run_benchmark.py --engine faster-whisper --model small.en --manifest benchmark/fixtures/manifest.json`.
- Output JSON includes model/engine, per-file elapsed seconds, expected text, actual text, normalized word error rate, median latency, and environment metadata.

- [ ] Write a failing unit test for English normalization: lowercase, collapse whitespace, remove punctuation only for WER comparison.
- [ ] Write a failing unit test for WER calculation using a known insertion/deletion/substitution example.
- [ ] Run `python -m unittest tests.test_benchmark -v`; verify RED.
- [ ] Implement pure normalization/WER functions and JSON report creation.
- [ ] Add a faster-whisper adapter but do not download or run models during unit tests.
- [ ] Run tests; verify GREEN.
- [ ] Document fixture recording rules: 16 kHz mono WAV; consented local recordings; include brand names, technical terms, fast speech, and quiet/noisy environments.
- [ ] Commit `feat: add offline transcription benchmark`.

### Task 6: Full regression verification and audit report

**Files:**
- Create: `docs/audits/2026-07-14-simplespeech-stabilization.md`

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python -m compileall -q app.py transcriber.py refiner.py runtime.py startup.py benchmark`.
- [ ] Build `SimpleSpeech.spec` cleanly and run `python tests/test_packaging.py dist/SimpleSpeech`.
- [ ] Record tested behavior, remaining manual-only checks, known risks, and no-go criteria for beginning VoxKey migration.
- [ ] Verify `git status --short` shows only intentional source/docs changes plus untouched untracked `index.html`.
- [ ] Commit `docs: record SimpleSpeech stabilization audit`.
