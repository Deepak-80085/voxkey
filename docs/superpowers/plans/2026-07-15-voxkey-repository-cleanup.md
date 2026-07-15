# VoxKey Repository Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone `E:\voxkey` repository containing only the active VoxKey application, its tests, packaging, and current documentation.

**Architecture:** Preserve `E:\simplespeech` as the legacy SimpleSpeech repository. Push the approved cleanup documentation, clone the public VoxKey repository into a standalone checkout, remove inherited legacy files there, consolidate packaging validation around the Qt application, then verify tests and Windows packaging before removing the old worktree.

**Tech Stack:** Python 3.12, unittest, PySide6, faster-whisper, PyInstaller, Inno Setup 6, PowerShell, GitHub Actions.

## Global Constraints

- Preserve `E:\simplespeech` and its untracked `index.html` unchanged.
- Keep existing Git history; do not rewrite or force-push it.
- Do not change dictation behavior during repository cleanup.
- Do not delete or move the `v2.1.0` tag or replace its release assets.
- Do not publish a new release during cleanup.
- The standalone repository must work without access to `E:\simplespeech`.

---

### Task 1: Create The Standalone VoxKey Checkout

**Files:**
- Existing docs: `docs/superpowers/specs/2026-07-15-voxkey-repository-cleanup-design.md`
- Existing plan: `docs/superpowers/plans/2026-07-15-voxkey-repository-cleanup.md`
- Create checkout: `E:\voxkey\`

**Interfaces:**
- Consumes: local branch `voxkey-v2` and remote branch `origin/main`.
- Produces: standalone checkout `E:\voxkey` with its own `.git` directory.

- [ ] **Step 1: Verify source and destination paths**

```powershell
Resolve-Path E:\simplespeech
Resolve-Path E:\simplespeech-voxkey-v2
Test-Path E:\voxkey
git status --short --branch
git remote -v
```

Expected: both source paths resolve, `E:\voxkey` is absent, the worktree is clean, and `origin` is the VoxKey repository.

- [ ] **Step 2: Push the approved documentation commits**

```powershell
git push origin HEAD:main
```

Expected: `origin/main` advances without a force push.

- [ ] **Step 3: Clone VoxKey as a standalone repository**

Run from `E:\`:

```powershell
git clone https://github.com/Deepak-80085/voxkey.git E:\voxkey
```

Expected: clone completes and `E:\voxkey\.git` is a directory.

- [ ] **Step 4: Verify repository independence**

```powershell
git -C E:\voxkey status --short --branch
git -C E:\voxkey remote -v
git -C E:\voxkey rev-parse --git-dir
git -C E:\voxkey rev-parse --git-common-dir
```

Expected: branch is `main`, both Git directory commands return `E:/voxkey/.git`, and only the VoxKey remote is configured.

- [ ] **Step 5: Create an independent Python environment**

```powershell
py -3.12 -m venv E:\voxkey\.venv
E:\voxkey\.venv\Scripts\python.exe -m pip install --upgrade pip
E:\voxkey\.venv\Scripts\python.exe -m pip install -r E:\voxkey\requirements.txt pyinstaller
```

Expected: installation succeeds without using the SimpleSpeech environment.

---

### Task 2: Make Packaging Validation VoxKey-Only

**Files:**
- Modify: `tests/test_voxkey_packaging.py`
- Delete: `tests/test_packaging.py`
- Modify: `.github/workflows/release.yml`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `validate_frozen_app(app_dir: Path) -> list[str]`.
- Consumed by: `python tests/test_voxkey_packaging.py dist/VoxKey` locally and in CI.

- [ ] **Step 1: Replace the packaging test with a VoxKey validator**

Use this complete content for `tests/test_voxkey_packaging.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
REQUIRED_FROZEN_FILES = (
    Path("_internal") / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
)


def validate_frozen_app(app_dir: Path) -> list[str]:
    return [
        path.as_posix()
        for path in REQUIRED_FROZEN_FILES
        if not (app_dir / path).is_file()
    ]


class VoxKeyPackagingTests(unittest.TestCase):
    def test_voxkey_spec_bundles_required_native_runtime_dependencies(self):
        contents = (ROOT / "VoxKey.spec").read_text(encoding="utf-8")
        self.assertIn("voxkey_app.py", contents)
        self.assertIn("PySide6.QtWidgets", contents)
        self.assertIn("faster_whisper", contents)
        self.assertIn("assets/*.onnx", contents)
        self.assertIn("name='VoxKey'", contents)
        self.assertNotIn("PIL.ImageTk", contents)
        self.assertNotIn("pystray", contents)

    def test_voxkey_installer_is_per_user(self):
        contents = (ROOT / "installer" / "VoxKey.iss").read_text(encoding="utf-8")
        self.assertIn('#define MyAppName "VoxKey"', contents)
        self.assertIn('#define MyAppVersion "2.1.0"', contents)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\{#MyAppName}', contents)
        self.assertIn('Source: "..\\dist\\VoxKey\\*"', contents)

    def test_frozen_validation_reports_missing_vad_model(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = validate_frozen_app(Path(temporary_directory))
        self.assertEqual(
            missing,
            ["_internal/faster_whisper/assets/silero_vad_v6.onnx"],
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} <frozen-app-directory>")
    missing = validate_frozen_app(Path(sys.argv[1]))
    if missing:
        print("Frozen application is missing required runtime dependencies:")
        print(*(f"- {path}" for path in missing), sep="\n")
        raise SystemExit(1)
    print("Frozen application contains all required runtime dependencies.")
```

- [ ] **Step 2: Delete the obsolete mixed packaging test**

```powershell
git rm tests\test_packaging.py
```

- [ ] **Step 3: Update CI**

Replace `python tests/test_packaging.py dist/VoxKey` with:

```powershell
python tests/test_voxkey_packaging.py dist/VoxKey
```

- [ ] **Step 4: Remove unused legacy UI dependencies**

Delete from `requirements.txt`:

```text
Pillow>=10.0.0
pystray==0.19.5
```

Remove them from the independent environment before verification:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y Pillow pystray
```

- [ ] **Step 5: Verify and commit packaging cleanup**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_voxkey_packaging -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git add -A
git commit -m "build: make packaging validation VoxKey-only"
```

Expected: focused and full suites pass, then one packaging cleanup commit is created.

---

### Task 3: Remove Legacy SimpleSpeech Source And Tests

**Files:**
- Delete: `app.py`, `calibration.py`, `database.py`, `refiner.py`
- Delete: `runtime.py`, `startup.py`, `transcriber.py`, `ui.py`
- Delete: `SimpleSpeech.spec`, `SimpleSpeech_Overview (1).docx`
- Delete: `installer/SimpleSpeech.iss`
- Delete: `tests/test_hotkey_service.py`, `tests/test_paste.py`
- Delete: `tests/test_runtime_and_refiner.py`, `tests/test_startup.py`
- Delete: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: active entry point `voxkey_app.py` and existing VoxKey tests.
- Produces: unittest discovery containing only active VoxKey and benchmark tests.

- [ ] **Step 1: Prove active modules do not import legacy modules**

Run `rg` across the active VoxKey modules and tests for imports of `app`,
`calibration`, `database`, `refiner`, `runtime`, `startup`, `transcriber`, or
`ui`. Expected: matches appear only inside tests scheduled for deletion.

```powershell
rg -n "from app|from calibration|from database|from refiner|from runtime|from startup|from transcriber|from ui" *.py tests
```

- [ ] **Step 2: Delete the legacy files through Git**

```powershell
git rm app.py calibration.py database.py refiner.py runtime.py startup.py transcriber.py ui.py
git rm SimpleSpeech.spec 'SimpleSpeech_Overview (1).docx' installer\SimpleSpeech.iss
git rm tests\test_hotkey_service.py tests\test_paste.py tests\test_runtime_and_refiner.py
git rm tests\test_startup.py tests\test_ui_state.py
```

Expected: every listed file is staged as deleted and no active VoxKey file is removed.

- [ ] **Step 3: Run the remaining tests**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all remaining tests pass because packaging validation was made VoxKey-only in Task 2.

- [ ] **Step 4: Commit the isolated legacy deletion**

```powershell
git add -A
git commit -m "chore: remove inherited SimpleSpeech application"
```

Expected: one commit containing only legacy source, installer, document, and test deletions.

---

### Task 4: Remove Legacy Documentation And Correct Product Copy

**Files:**
- Delete: `docs/windows-release-smoke-test.md`
- Delete: `docs/audits/2026-07-14-simplespeech-stabilization.md`
- Delete: `docs/superpowers/plans/2026-07-11-windows-release-reliability.md`
- Delete: `docs/superpowers/plans/2026-07-14-simplespeech-stabilization-and-benchmark.md`
- Delete: `docs/superpowers/specs/2026-07-11-pillow-imagetk-packaging-design.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: public documentation matching the capture-only HUD and start/completion sound behavior.

- [ ] **Step 1: Remove SimpleSpeech-only documentation**

```powershell
git rm docs\windows-release-smoke-test.md
git rm docs\audits\2026-07-14-simplespeech-stabilization.md
git rm docs\superpowers\plans\2026-07-11-windows-release-reliability.md
git rm docs\superpowers\plans\2026-07-14-simplespeech-stabilization-and-benchmark.md
git rm docs\superpowers\specs\2026-07-11-pillow-imagetk-packaging-design.md
```

- [ ] **Step 2: Correct the README interaction description**

Replace the stale HUD paragraph with:

```markdown
VoxKey stays out of sight while idle. A small animated orb appears only while
Right Ctrl is held; it disappears immediately on release while transcription,
polishing, and paste continue locally in the background.
```

Replace the future-feature limitation with:

```markdown
- Right Ctrl is currently the fixed dictation trigger. Configurable hotkeys,
  microphone selection, vocabulary editing, autostart, and onboarding are not
  implemented yet.
```

- [ ] **Step 3: Add an Unreleased changelog section**

Insert before `## [2.1.0]`:

```markdown
## [Unreleased]

### Changed
- Show the compact animated orb only while Right Ctrl is held.
- Use the bundled start and successful-paste MP3 cues.
- Keep the local Ollama writer resident between dictations to reduce warm latency.
- Remove inherited SimpleSpeech source, tests, installer, and packaging configuration.

### Fixed
- Log separate transcription, polishing, and total pipeline timings.
```

- [ ] **Step 4: Verify docs and commit**

```powershell
rg -n "SimpleSpeech\.spec|installer\\SimpleSpeech|Alt\+Shift|Hold Alt|PIL\.ImageTk" README.md CHANGELOG.md .github installer tests *.py *.spec
.\.venv\Scripts\python.exe -m unittest tests.test_public_docs -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git add -A
git commit -m "docs: align repository with current VoxKey product"
```

Expected: active public docs, automation, tests, and source contain no removed behavior; retained historical plans, specs, and `flow.md` may still describe prior work.

---

### Task 5: Verify Standalone Build And Retire The Old Worktree

**Files:**
- Build: `dist/VoxKey/`
- Build: `release/VoxKey-Setup-2.1.0.exe`
- Remove after verification: `E:\simplespeech-voxkey-v2`

**Interfaces:**
- Consumes: clean standalone repository and VoxKey-specific validator.
- Produces: verified standalone development checkout at `E:\voxkey`.

- [ ] **Step 1: Verify references and tests**

```powershell
rg -n "SimpleSpeech\.spec|installer\\SimpleSpeech|from (app|refiner|runtime|startup|transcriber|ui) import" .github installer tests *.py *.spec
git status --short --branch
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: no legacy references, a clean branch, and all tests passing.

- [ ] **Step 2: Build and validate the frozen application**

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm VoxKey.spec
.\.venv\Scripts\python.exe tests\test_voxkey_packaging.py dist\VoxKey
```

Expected: `dist\VoxKey\VoxKey.exe` exists and validation reports all dependencies present.

- [ ] **Step 3: Build the installer without publishing it**

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\VoxKey.iss
Get-FileHash release\VoxKey-Setup-2.1.0.exe -Algorithm SHA256
```

Expected: installer succeeds and a local SHA-256 is printed. Do not upload it.

- [ ] **Step 4: Push cleanup commits**

```powershell
git push origin main
```

Expected: an ordinary fast-forward push succeeds and CI starts.

- [ ] **Step 5: Verify absolute paths before worktree removal**

Run from `E:\voxkey`:

```powershell
$legacyRoot = (Resolve-Path E:\simplespeech).Path
$oldWorktree = (Resolve-Path E:\simplespeech-voxkey-v2).Path
$newRepository = (Resolve-Path E:\voxkey).Path
$legacyRoot
$oldWorktree
$newRepository
git -C E:\simplespeech worktree list --porcelain
```

Expected: paths are exactly `E:\simplespeech`, `E:\simplespeech-voxkey-v2`, and `E:\voxkey`; only the old VoxKey worktree is selected for removal.

- [ ] **Step 6: Remove only the old VoxKey worktree**

```powershell
git -C E:\simplespeech worktree remove E:\simplespeech-voxkey-v2
git -C E:\simplespeech worktree prune
```

Expected: SimpleSpeech and the new standalone VoxKey clone remain intact.

- [ ] **Step 7: Prove final independence**

```powershell
git -C E:\voxkey status --short --branch
git -C E:\voxkey rev-parse --git-common-dir
git -C E:\simplespeech status --short --branch
Test-Path E:\simplespeech\index.html
Test-Path E:\simplespeech-voxkey-v2
```

Expected: VoxKey uses `E:/voxkey/.git`; SimpleSpeech still has its original untracked `index.html`; the old worktree path is absent.
