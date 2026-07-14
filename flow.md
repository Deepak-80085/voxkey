# VoxKey Development Flow

> **Purpose:** a chronological engineering record of the work from the initial SimpleSpeech stabilization request through the current VoxKey build. It preserves decisions, defects, evidence, releases, constraints, and known limitations so work can resume without reconstructing context.
>
> **Last updated:** 2026-07-14
>
> **Status:** development is intentionally paused at the user's request.

---

## 1. Original request and constraints

The starting point was a working Windows dictation application named **SimpleSpeech**, located at:

```text
E:\simplespeech
```

The request was to stabilize the existing application without breaking it, then create a separate, polished, open-source successor called **VoxKey**.

The critical product constraints established during the conversation were:

- Windows desktop application.
- Offline-first / local-only: no cloud service, account, subscription, API key, or network transcription service.
- English only.
- Speech recognition must use **`small.en`**. `base.en` must not be downloaded, selected, or used as a fallback.
- Local text polishing must use the locally installed Ollama model:

  ```text
  qwen3.5:0.8b
  ```

- Do not paste the raw transcript if the local writer fails. The pipeline must either paste polished text or report a repairable failure.
- Preserve the original SimpleSpeech application; do not rewrite it in place.
- VoxKey data must be owned separately under:

  ```text
  %LOCALAPPDATA%\VoxKey
  ```

- Dictation must restore the app that was focused when recording began and paste there.
- Idle behavior should be tray-first. The feedback UI must not steal focus.
- The user initially approved a premium Siri-inspired transient HUD, but later explicitly revised this requirement to a tiny round indicator only while holding the hotkey, with no post-release visual UI.
- Sounds must be enabled by default, configurable/mutable from the tray/settings, and use the existing SimpleSpeech custom start/end sounds rather than Windows system beeps.
- The public GitHub repository target is:

  ```text
  https://github.com/Deepak-80085/voxkey
  ```

- The project uses the MIT license.

---

## 2. Repository isolation and SimpleSpeech stabilization

### 2.1 Isolating VoxKey

The original application remains in:

```text
E:\simplespeech
```

A separate Git worktree was created for VoxKey:

```text
E:\simplespeech-voxkey-v2
Branch: voxkey-v2
Git worktree directory: E:\simplespeech\.git\worktrees\simplespeech-voxkey-v2
```

This separation was intentional: changes to VoxKey could not overwrite or destabilize the already functioning SimpleSpeech project.

### 2.2 SimpleSpeech improvements completed before VoxKey work

SimpleSpeech was stabilized first. Work included:

- Startup reliability fixes.
- PyInstaller packaging fixes for Pillow/Tk functionality.
- Faster-whisper VAD asset packaging.
- Shutdown/lifecycle improvements.
- Benchmark tooling and release documentation.
- CI and installer validation.
- Detection and removal of only stale/corrupt Hugging Face model-cache entries after this failure:

  ```text
  RuntimeError: Unable to open file 'model.bin' in model
  ```

- Successful validation that the correct Faster Whisper `base.en` model artifact was rebuilt for the original app.

A SimpleSpeech release installer was produced:

```text
E:\simplespeech\release\SimpleSpeech-Setup-1.0.2.exe
SHA-256: 3FAE8FE0AB45B914B7D570C59B2D6B34918ADEACC6ABA3FFD394832F4111C255
```

The unrelated untracked file below was deliberately left untouched:

```text
E:\simplespeech\index.html
```

---

## 3. Hardware and local-runtime findings

The target system was inspected and confirmed to have:

```text
GPU: NVIDIA GeForce GTX 1650
VRAM: 4 GB
Driver: 591.44
Driver-reported CUDA capability: 13.1
```

Ollama already installed CUDA/cuDNN runtime DLLs locally, including:

```text
C:\Users\Deepak\AppData\Local\Programs\Ollama\lib\ollama\cuda_v12\cublas64_12.dll
C:\Users\Deepak\AppData\Local\Programs\Ollama\lib\ollama\cuda_v12\cublasLt64_12.dll
C:\Users\Deepak\AppData\Local\Programs\Ollama\lib\ollama\mlx_cuda_v13\cudnn64_9.dll
```

Instead of requiring a global CUDA installation, VoxKey adds those local directories to the process DLL search path before initializing Faster Whisper. This made CUDA inference available to the VoxKey process.

A retained real dictation was benchmarked with the strict `small.en` model:

```text
CPU small.en: 2.18 s
GPU small.en: 0.75 s
Transcript: "It's very slow compared to simple speech"
```

This demonstrated that the speech engine could be fast on the GTX 1650 and that later long perceived delays needed stage-by-stage diagnosis rather than a blind rewrite.

---

## 4. VoxKey's initial implementation

The foundation was built in the isolated worktree with these primary modules:

```text
voxkey_app.py          Windows entry point, hotkey, recording, paste behavior
voxkey_controller.py   ready-gated transcription/polish/paste state machine
voxkey_events.py       thread-safe UI event boundary
voxkey_runtime.py      local paths, persistent settings, logging, app states
voxkey_ui.py           PySide6 tray UI, settings, feedback overlay, sounds
speech_models.py       strict local `small.en` model management and CUDA support
writing_model.py       strict local Ollama writer client
vocabulary.py          user vocabulary normalization and prompt building
VoxKey.spec            PyInstaller build specification
installer\VoxKey.iss   Inno Setup installer
```

### 4.1 Required speech model policy

`SpeechModelManager` in `speech_models.py` enforces:

```text
Model: small.en
Repository: Systran/faster-whisper-small.en
Storage: %LOCALAPPDATA%\VoxKey\models\speech\
```

It does not use or fall back to `base.en`.

The model manager:

1. Validates its VoxKey-owned `model.bin`.
2. Adds Ollama CUDA directories, if present.
3. Attempts CUDA with `int8_float16`.
4. Falls back only to the **same `small.en` model** on CPU with `int8` if GPU initialization or runtime inference fails.
5. Leaves a repairable state if the model is missing/corrupt.

### 4.2 Required local writer policy

`WritingModelClient` requires the selected local Ollama model:

```text
qwen3.5:0.8b
```

The writer:

- Uses `http://127.0.0.1:11434`.
- Checks `/api/tags` during startup.
- Uses a preservation-oriented prompt: punctuation and capitalization are improved while names, numbers, facts, and meaning must stay intact.
- Sends:

  ```json
  {
    "stream": false,
    "think": false,
    "options": {
      "num_predict": 120,
      "temperature": 0
    }
  }
  ```

- Never falls back to raw transcript pasting when Ollama fails.

A key diagnosis was that this model could spend output budget in hidden reasoning. Setting `think: false` fixed that. A real result after the fix was:

```text
The Zudio shopping is cheap and good.
```

with an observed response of roughly `0.65 s` in an earlier warm run.

### 4.3 One-mode state machine

VoxKey is ready-gated. The state flow is:

```text
Starting → Validating → Ready
Ready → Listening → Transcribing → Polishing → Ready
Any unrecoverable local dependency/capture failure → Needs repair
```

It does not accept dictation until the local speech model and local writer are both healthy.

### 4.4 Single-instance protection

A named per-session mutex prevents duplicate VoxKey processes from competing for the microphone and Ollama:

```text
Local\VoxKeySingleInstance
```

Earlier, closing the old Tk control-center window merely hid it and left an invisible process holding this mutex. That lifecycle problem was fixed: explicit quit now releases the process/mutex cleanly.

---

## 5. Real-device and real-target validation

Component testing was not treated as enough proof. The application was instrumented and exercised with real Windows components.

### 5.1 Persistent diagnostics

VoxKey logs to:

```text
%LOCALAPPDATA%\VoxKey\voxkey.log
```

and retains the last microphone capture at:

```text
%LOCALAPPDATA%\VoxKey\last-dictation.wav
```

Log events include:

- hotkey press,
- recording start and save,
- processing start,
- transcription completion/time,
- polishing completion/time,
- paste attempt/result,
- active inference device,
- state changes,
- errors.

The retained WAV and logs proved real behavior in the installed app rather than only mocked/unit-test behavior.

### 5.2 Microphone and speech validation

The actual selected hardware was successfully captured:

```text
Input: Microphone Array (Realtek(R) Audio)
```

The actual `small.en` model transcribed a direct capture as:

```text
Hello, you can hear me right, whatever I'm saying, just check if this is working or not.
```

The global `pynput` listener was separately proven to fire on this PC.

### 5.3 Hotkey decision: do not use Alt

Alt was originally explored as a hold-to-dictate trigger. This was rejected after real Notepad evidence showed that holding Alt activated Windows/Notepad access-key/menu navigation, with letter overlays visible on screen. This also interfered with target focus and paste.

The trigger was changed to:

```text
Hold Right Ctrl for at least 0.28 seconds.
Speak while held.
Release Right Ctrl to process and paste.
```

The persistent setting is:

```json
"hotkey": "right_ctrl"
```

A later regression was also fixed: synthetically releasing `keyboard.Key.ctrl_r` before paste could produce literal `r` characters on some layouts. VoxKey no longer synthesizes that release.

### 5.4 Target restoration and paste proof

VoxKey captures the foreground window handle at hotkey press, restores it immediately before Ctrl+V, and then sends paste. A real Notepad acceptance test using the actual `paste_polished_text()` function confirmed exact result transfer:

```text
NOTEPAD_RECEIVED= 'VOXKEY_RIGHT_CTRL_PASTE_TEST_9E72'
PASS: real Notepad accepted exact VoxKey paste
```

Known operating-system limitations remain:

- A target application running elevated may require VoxKey to run elevated.
- Secure desktop surfaces are unsupported.

---

## 6. PySide6/Qt UI transition

Tkinter was insufficient for the requested tray integration and transparent non-activating overlay behavior. The application was migrated to PySide6/Qt.

Installed dependency:

```text
PySide6 6.9.0
```

The event boundary is framework-independent:

```text
UiEvent
EventBus
```

Worker code emits immutable events. The Qt main thread drains them and updates UI/sounds/settings. This avoids mutating widgets from microphone/inference worker threads.

The initial Qt implementation included:

- tray icon,
- tray menu:
  - Open settings
  - Sounds on/off
  - Repair models
  - Open diagnostics
  - Quit VoxKey
- compact settings dialog,
- transparent bottom-center status HUD,
- animated orb/waveform,
- lifecycle text states (`Listening`, `Transcribing`, `Polishing`, `Done`, errors),
- Windows system sounds.

Two immediate Qt integration defects were found and corrected before release:

```text
AttributeError: 'VoxKeyShell' object has no attribute 'sound_action'
AttributeError: 'PySide6.QtWidgets.QCommonStyle' object has no attribute 'SP_ComputerIcon'
```

A success HUD lifecycle bug was also fixed: a later generic `state_changed/READY` event was hiding the success animation too early.

All Qt modules were included in `VoxKey.spec`:

```text
PySide6.QtCore
PySide6.QtGui
PySide6.QtWidgets
PySide6.QtMultimedia
```

The frozen Qt build successfully passed runtime package validation.

---

## 7. Public release preparation and publication

### 7.1 Public project material

Public materials were added:

```text
README.md
LICENSE
SECURITY.md
CONTRIBUTING.md
CHANGELOG.md
docs\privacy.md
docs\architecture.md
docs\windows-v0.1.0-smoke-test.md
.github\ISSUE_TEMPLATE\bug_report.yml
.github\workflows\release.yml
```

`.superpowers/` was added to `.gitignore` and must remain private/untracked.

The public documentation tests assert, among other things:

- MIT license is present.
- Local-only behavior is documented.
- `small.en` is documented.
- `qwen3.5:0.8b` is documented.

### 7.2 Version decision

There was already an installed test build:

```text
VoxKey 2.0.6-test
```

Publishing as `0.1.0` would have been an unsafe downgrade in Inno Setup. The release was therefore versioned as:

```text
VoxKey 2.1.0
```

This allows an in-place upgrade of the prior test build.

### 7.3 GitHub repository and CI

The public repository was created and pushed:

```text
https://github.com/Deepak-80085/voxkey
Default branch: main
```

Release workflow behavior:

1. Checkout.
2. Set up Python.
3. Install dependencies.
4. Run tests.
5. Install Inno Setup.
6. Build PyInstaller app.
7. Build installer.
8. Generate checksum.
9. Upload artifacts.
10. On tag, publish GitHub release assets.

GitHub Actions builds passed. GitHub warned that actions using Node.js 20 were being forced to run under Node.js 24; this is an upstream action runtime warning, not a VoxKey test/package failure.

### 7.4 SmartScreen and Edge warnings

The installer is unsigned. Consequently:

- Edge can say the executable is not commonly downloaded.
- Windows Defender SmartScreen can say the app is unrecognized and block it until the user chooses **More info → Run anyway**.

This is expected for a newly published unsigned Windows executable. It is not an Edge bug or a VoxKey runtime defect. Proper Authenticode code signing and download reputation are needed to reduce/remove these warnings.

---

## 8. UI feedback changes driven by real screenshots

### 8.1 Initial release mismatch

The user tested the initial public release and supplied screenshots. They showed:

- Edge download-reputation warning.
- SmartScreen warning.
- A very large VoxKey text/status HUD during and after dictation.

The user clarified the actual desired behavior:

- while holding Right Ctrl: only a round UI;
- no text;
- after release: no UI at all;
- audible start/end feedback, matching SimpleSpeech.

This contradicted the earlier approved multi-state Siri-style HUD. The implementation was revised to follow the newest explicit requirement.

### 8.2 Removing post-release HUDs

The HUD state mapping was changed so that:

```text
capture_started → visible orb
capture_stopped → hide
transcribing → hide
polishing → hide
paste_succeeded → hide
pipeline_failed → hide
state_changed → hide/no HUD effect
```

Sounds still occur independently of HUD visibility:

```text
capture_started → start sound
paste_succeeded → completion sound
capture_failed/pipeline_failed → error cue policy (currently not custom MP3-mapped)
```

### 8.3 Correcting size and sounds

The first attempt only reduced the text HUD container from `360×220` to `132×132`, but the user correctly reported it was still visually huge.

The orb was then reduced to a `52×52` transparent widget with a roughly 36–42 pixel rendered circle. It has:

- no text,
- no panel,
- no waveform,
- no UI shown after release.

The earlier system-beep implementation used `winsound.MessageBeep`, which was wrong for the requested experience. The project already contained SimpleSpeech audio assets:

```text
asset\starrt.mp3  (about 1.071 s)
asset\end.mp3     (about 0.504 s)
```

VoxKey now uses Windows MCI (`winmm.mciSendStringW`) on a background thread to play those exact MP3 assets without blocking the dictation pipeline:

```text
start capture → starrt.mp3
successful paste → end.mp3
```

The frozen installer package was checked to ensure both files are included at:

```text
%LOCALAPPDATA%\Programs\VoxKey\_internal\asset\starrt.mp3
%LOCALAPPDATA%\Programs\VoxKey\_internal\asset\end.mp3
```

---

## 9. Latency investigation and current findings

The user reported VoxKey felt very slow. Real logs confirmed it, rather than dismissing it as subjective.

One installed-app dictation run measured:

```text
Recording saved: 3.4 s capture (user-controlled hold duration)
Transcription: 3.36 s
Polishing: 5.98 s
Paste/clipboard/focus: about 0.55 s
Total from processing start: 9.89 s
```

This showed the perceived delay was real and came predominantly from speech + writer stages.

### 9.1 Speech CUDA verification

New logging was added before transcription:

```text
Transcribing with device=cuda
```

A direct current test with the retained real capture showed:

```text
SpeechModelStatus(ready=True, device='cuda', reason=None)
DEVICE=cuda
SECONDS=0.772
TEXT='Can you hear me?'
```

Therefore, the core speech model is able to use CUDA and transcribe the same retained audio quickly. The earlier 3.36 second installed run may have involved first-run/context overhead or a different workload, so future performance conclusions should use fresh logs containing the device line and stage durations.

### 9.2 Ollama warm-model result

A direct Ollama experiment showed a large difference between model-loading and warm requests. After instructing Ollama to retain the model:

```text
keep_alive: "24h"
```

measured writer calls were:

```text
writer_run=1: 1.859 s
writer_run=2: 0.816 s
```

`WritingModelClient` now sends `keep_alive: "24h"` on generation requests so repeated dictations should not repeatedly reload the local writer model.

Important: this keeps the model resident and consumes local RAM/VRAM while Ollama is running. It is a deliberate latency-vs-residency tradeoff. The user approved a local performance-oriented workflow.

### 9.3 Corrected timing logs

The controller initially logged "polishing elapsed" as cumulative time from pipeline start. It now logs distinct durations:

```text
Transcription completed; chars=<n>; elapsed_ms=<transcription duration>
Polishing completed; chars=<n>; elapsed_ms=<polishing-only duration>
Paste attempted; success=<bool>; target=<hwnd>; total_ms=<full processing duration>
```

---

## 10. Orb animation iterations and current state

### 10.1 Original animation

The initial Qt orb used a Python-driven `QTimer` every 40 ms, custom `paintEvent` math, a changing gradient, and a waveform. The user found it visually laggy/stuttery.

### 10.2 Opacity-animation attempt

The first replacement removed the timer and animated `windowOpacity` using Qt `QPropertyAnimation`. This was intended to make a low-cost compositor animation suitable for CPU-only systems.

Real screenshot feedback showed that the orb remained visibly static on the target Windows compositor. The opacity change either was not perceptible or was not applied in the expected way to the transparent top-level window.

### 10.3 Current radius-animation implementation

The current implementation uses a Qt `QPropertyAnimation` on the custom `orbRadius` property instead of `windowOpacity`:

```text
Duration: 900 ms
Radius: 15 px → 21 px → 15 px
Loop: infinite while held
Easing: InOutSine
```

The animation is stopped and the widget hidden immediately upon key release.

The property setter calls `update()` only when Qt advances the animated radius. There is no manually scheduled Python `QTimer` loop and no waveform/gradient rebuilding. The drawing area is only `52×52` pixels.

A direct local Qt event-loop probe verified the animation actually advances:

```text
radius at start: 15.0
radius at 500 ms: 20.37282922039408
animation state: Running
hidden after release: True
animation state: Stopped
```

This proves the property animation runs inside the Qt event loop. Physical visual smoothness still needs user desktop testing, because a numeric property change alone cannot prove how a specific Windows compositor presents a transparent top-level widget.

---

## 11. Current release/install state

### Repository

```text
Repository: https://github.com/Deepak-80085/voxkey
Remote branch: origin/main
Working branch: voxkey-v2
```

### Local installation

```text
C:\Users\Deepak\AppData\Local\Programs\VoxKey\VoxKey.exe
```

The latest locally installed build was launched and logged:

```text
VoxKey starting
State: Validating
State: Ready
```

### Current Git tip

At pause time, current history ends with:

```text
40b4155 fix: visibly animate hold orb radius
784c500 perf: use compositor animation for hold orb
aec45e5 perf: keep local writer loaded between dictations
7c942b5 fix: match SimpleSpeech feedback and diagnose latency
48f9d4c fix: use orb-only hold feedback
```

### GitHub release tag caveat

The `v2.1.0` tag was created earlier at:

```text
b2be4b6 fix: render HUD text inside translucent overlay
```

Subsequent commits replaced the **same `VoxKey-Setup-2.1.0.exe` GitHub release asset** without moving the tag. Thus the current release installer asset contains later fixes than the tag commit. This is workable for testing but not ideal release hygiene. A future formal release should use a new immutable version/tag (for example `v2.1.1`) rather than replacing a published binary under the same version number.

### Latest GitHub installer asset

Current published release URL:

```text
https://github.com/Deepak-80085/voxkey/releases/tag/v2.1.0
```

At the time this document was written, latest uploaded installer asset metadata was:

```text
File: VoxKey-Setup-2.1.0.exe
SHA-256: 79EA9C3D6D4A9C69FC4E146865905E415598F5755772A4BF6910CC3457C9EF48
```

The release checksum companion file is also uploaded. The installer is still unsigned.

---

## 12. Test and package evidence

The automated suite grew from an initial baseline of 46 tests to 58, then 59, then 62 tests as UI, event, device logging, timing, sound asset, and animation behavior were covered.

At the current pause point:

```text
62 automated tests passed
```

Key validated areas include:

- strict `small.en` policy;
- no `base.en` fallback;
- local application paths;
- vocabulary normalization;
- writer availability and no raw-text fallback;
- hotkey rules;
- target focus restoration before Ctrl+V;
- single-instance mutex;
- event ordering;
- lifecycle/timing events;
- sound preference persistence;
- SimpleSpeech MP3 asset mapping;
- compact text-free orb;
- only capture lifecycle events render/hide the HUD;
- Qt-driven radius animation, without a manual repaint timer;
- public documentation assertions;
- PyInstaller package assertions.

The packaged application also passed:

```text
Frozen application contains all required runtime dependencies.
```

The installer has been repeatedly built, silently installed over prior builds, and launch-smoke-tested. The live Windows tray/hotkey/microphone/paste workflow still benefits from a human physical check after each behavior-oriented build.

---

## 13. Known limitations and follow-up work

### Must be verified manually after resume

1. Hold Right Ctrl and assess whether the latest radius pulse is visually smooth on the real desktop.
2. Confirm the start sound is exactly the SimpleSpeech `starrt.mp3` cue.
3. Confirm the completion sound is exactly the SimpleSpeech `end.mp3` cue after successful paste.
4. Confirm no UI remains after Right Ctrl is released.
5. Run several real dictations and inspect `voxkey.log` for:

   ```text
   Transcribing with device=cuda
   Transcription completed ...
   Polishing completed ...
   Paste attempted ...
   ```

6. Measure cold vs warm writer behavior after the new `keep_alive: "24h"` setting.
7. Test tray **Quit VoxKey** manually. Earlier PowerShell tray-menu probing had quoting/API issues and was not accepted as proof.
8. Test target apps running elevated, with VoxKey elevated as needed.

### Open product/engineering concerns

- The current `v2.1.0` release asset has been replaced multiple times. Cut a new version/tag for the next public release.
- Authenticode signing is not configured. SmartScreen/download-reputation warnings are expected.
- CPU-only visual smoothness should be checked physically. The current animation is small and event-loop driven, but no honest claim can cover every GPU driver, compositor configuration, or CPU load condition.
- The custom MP3 map currently provides start and successful-completion sounds. The prior Windows error sound was intentionally eliminated alongside `winsound`; decide whether errors should remain silent/tray-log only or receive a dedicated custom error asset.
- The strict writer policy protects against raw unpolished paste but means an unavailable/wedged Ollama service prevents output.
- Long initial requests can still occur if the writer model must load; subsequent requests should be faster while the model is retained for 24 hours.

---

## 14. Useful commands for resuming work

### Run the full test suite

```powershell
cd E:\simplespeech-voxkey-v2
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Build the frozen application and validate it

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm VoxKey.spec
.\.venv\Scripts\python.exe tests\test_packaging.py dist\VoxKey
```

### Build the installer and checksum

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\VoxKey.iss
Get-FileHash release\VoxKey-Setup-2.1.0.exe -Algorithm SHA256
```

### Install silently over the local build

```powershell
Get-Process VoxKey -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process .\release\VoxKey-Setup-2.1.0.exe `
  -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait
Start-Process "$env:LOCALAPPDATA\Programs\VoxKey\VoxKey.exe"
```

### Inspect current live logs

```powershell
Get-Content "$env:LOCALAPPDATA\VoxKey\voxkey.log" -Tail 80
```

### Inspect the retained capture

```text
%LOCALAPPDATA%\VoxKey\last-dictation.wav
```

### Check current process

```powershell
Get-Process VoxKey -ErrorAction SilentlyContinue |
  Select-Object Id, Responding, Path, StartTime
```

---

## 15. Final pause summary

VoxKey is a separate public, local-only Windows dictation application with a strict `small.en` speech policy, Ollama `qwen3.5:0.8b` text polishing, retained logs/audio diagnostics, focus restoration, real Notepad paste validation, GPU support through locally installed Ollama CUDA libraries, a tray-first Qt shell, and SimpleSpeech-compatible start/end MP3 feedback.

The current UI direction is intentionally minimal:

```text
Hold Right Ctrl  → tiny animated orb + custom start sound
Release Right Ctrl → orb disappears immediately; local processing occurs invisibly
Successful paste → custom SimpleSpeech end sound
```

The latest implementation replaced a visually static opacity animation with a verified Qt-driven radius animation. The app is paused immediately after packaging, installing, publishing, and documenting that revision. The next action should be a real desktop visual test of this final orb behavior, followed by a new immutable release version if it is accepted.
