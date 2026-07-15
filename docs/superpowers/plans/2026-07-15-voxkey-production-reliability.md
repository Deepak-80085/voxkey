# VoxKey Production Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make startup, repair, capture cleanup, and unexpected failures deterministic and locally diagnosable.

**Architecture:** Keep the existing controller and event bus. Use standard-library threads for blocking validation, a controller lock to serialize validation, forced model downloads for explicit repair, and runtime-owned rotating loggers with Python exception hooks.

**Tech Stack:** Python 3.12, PySide6, `threading`, `logging`, `unittest`, faster-whisper, huggingface-hub.

## Global Constraints

- Remain local-only: no telemetry or crash uploads.
- Keep `small.en`; do not add `base.en` or another speech model.
- Add no dependencies.
- Do not publish or replace `v2.1.0`.
- Preserve the existing EventBus worker-to-Qt boundary.

---

### Task 1: Isolate diagnostics and log unhandled exceptions

**Files:**
- Modify: `voxkey_runtime.py`
- Modify: `voxkey_app.py`
- Test: `tests/test_voxkey_runtime.py`

**Interfaces:**
- Produces: `VoxKeyRuntime.install_exception_logging() -> None`
- Produces: runtime-owned `VoxKeyRuntime.logger() -> logging.Logger`

- [ ] **Step 1: Write failing runtime tests**

Add tests that create two runtimes under different temporary `LOCALAPPDATA`
paths and assert their handlers target different `voxkey.log` files. Add a test
that installs hooks, invokes the thread hook with a synthetic exception, and
asserts the traceback text is written to the temporary log.

- [ ] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_voxkey_runtime -v`

Expected: failure because loggers share the global `VoxKey` handler and
`install_exception_logging` does not exist.

- [ ] **Step 3: Implement runtime-owned logging and exception hooks**

Initialize `self._logger = None`, create a direct `logging.Logger("VoxKey")`
with the existing rotating file handler, and install `sys.excepthook` plus
`threading.excepthook` callbacks that call:

```python
logger.error(
    "Unhandled exception in %s",
    origin,
    exc_info=(exception_type, exception, traceback),
)
```

Call `runtime.install_exception_logging()` in `main()` immediately after the
runtime is created.

- [ ] **Step 4: Verify Task 1**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_voxkey_runtime -v`

Expected: all runtime tests pass and temporary logs contain the synthetic
traceback.

### Task 2: Keep validation and repair off the Qt thread

**Files:**
- Modify: `voxkey_controller.py`
- Modify: `voxkey_app.py`
- Modify: `voxkey_ui.py`
- Test: `tests/test_dictation_pipeline.py`
- Test: `tests/test_voxkey_settings.py`

**Interfaces:**
- Produces: serialized `VoxKeyController.start()` and `repair_models()` calls.
- Produces: `SettingsActions.repair()` that dispatches repair on a daemon thread.

- [ ] **Step 1: Write failing concurrency and dispatch tests**

Add a controller test whose blocking speech health check allows a simultaneous
repair call and asserts only one health check runs. Patch `threading.Thread` in
the settings test and assert repair creates and starts a daemon thread instead
of calling the controller inline.

- [ ] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_dictation_pipeline tests.test_voxkey_settings -v`

Expected: direct repair invocation and duplicate validation are observed.

- [ ] **Step 3: Implement serialized background validation**

Add `self._validation_lock = threading.Lock()` to the controller and acquire it
non-blocking in `start()` and `repair_models()`, releasing it in `finally`.
Start `controller.start` from a daemon thread in `main()`. Change
`SettingsActions.repair()` to start `controller.repair_models` on a daemon
thread.

- [ ] **Step 4: Verify Task 2**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_dictation_pipeline tests.test_voxkey_settings -v`

Expected: all tests pass and no blocking operation is invoked directly by the
Qt action.

### Task 3: Force replacement during explicit speech-model repair

**Files:**
- Modify: `speech_models.py`
- Test: `tests/test_speech_models.py`

**Interfaces:**
- Extends: `SpeechModelManager.health_check(force_download: bool = False)`
- Keeps: `SpeechModelManager.repair() -> SpeechModelStatus`

- [ ] **Step 1: Write the failing repair test**

Create a non-empty corrupt `model.bin`, configure the loader to fail until the
mock downloader replaces it, call `repair()`, and assert the downloader receives
`force_download=True` before the successful load.

- [ ] **Step 2: Verify the test fails**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_speech_models -v`

Expected: repair reuses the existing non-empty file and never forces download.

- [ ] **Step 3: Implement forced repair**

Allow `_ensure_model(force_download=False)` and `health_check(force_download=False)`.
Skip reuse when forced and pass `force_download=force_download` to
`snapshot_download`. Implement `repair()` as reset plus
`health_check(force_download=True)`.

- [ ] **Step 4: Verify Task 3**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_speech_models -v`

Expected: all speech model tests pass.

### Task 4: Guarantee recorder and HUD cleanup on capture failure

**Files:**
- Modify: `voxkey_app.py`
- Modify: `voxkey_ui.py`
- Test: `tests/test_voxkey_hotkey.py`
- Test: `tests/test_voxkey_ui.py`

**Interfaces:**
- Keeps: `Recorder.start() -> bool`, `stop_and_save() -> Path`, `abort() -> None`
- Extends: `should_render_hud()` to route `capture_failed` to the hidden HUD view.

- [ ] **Step 1: Write failing cleanup tests**

Mock an input stream whose `start()` or `stop()` raises. Assert the stream is
closed, recorder state is cleared, and a `capture_failed` UI event is routed to
the HUD.

- [ ] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_voxkey_hotkey tests.test_voxkey_ui -v`

Expected: failed stream operations leave state or fail to hide the HUD.

- [ ] **Step 3: Implement minimal cleanup**

Assign `self.stream` only after a successful stream start. On stop/abort, always
attempt close and clear `stream` plus `chunks`, preserving the first stream
exception. Include `capture_failed` in the HUD lifecycle routing set.

- [ ] **Step 4: Verify Task 4**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_voxkey_hotkey tests.test_voxkey_ui -v`

Expected: all capture and HUD tests pass.

### Task 5: Full verification and physical checkpoint

**Files:**
- Modify: `docs/windows-v0.1.0-smoke-test.md`

- [ ] **Step 1: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Build and validate the frozen app**

Run:

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm VoxKey.spec
.\.venv\Scripts\python.exe tests\test_voxkey_packaging.py dist\VoxKey
```

Expected: PyInstaller exits zero and frozen dependency validation passes.

- [ ] **Step 3: Update and run the Windows smoke checkpoint**

Correct the smoke test to match the orb-only UI. Verify responsive startup,
forced repair of a deliberately corrupt model, capture failure cleanup, twenty
dictations, tray quit, and restart. Do not publish a release.
