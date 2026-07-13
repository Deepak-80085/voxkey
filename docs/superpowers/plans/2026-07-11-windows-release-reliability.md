# Windows Release Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Windows installer that deterministically bundles SimpleSpeech’s VAD and Pillow/Tk runtime dependencies, preserves user data on upgrades, and documents repeatable release validation.

**Architecture:** PyInstaller’s spec is the source of truth for explicit runtime imports. Unit tests assert the spec declarations; release automation builds the frozen folder and asserts the exact shipped files before compiling the Inno Setup installer. Inno Setup uses a stable per-user application ID and does not touch `%LOCALAPPDATA%\SimpleSpeech`, where runtime data belongs.

**Tech Stack:** Python 3.12, unittest, PyInstaller 6.19, Pillow, faster-whisper, Inno Setup, GitHub Actions.

## Global Constraints

- Preserve SimpleSpeech’s Windows-only, offline-first dictation workflow.
- Keep user logs, recordings, model caches, and runtime data outside the install directory at `%LOCALAPPDATA%\SimpleSpeech`.
- Do not modify the untracked root `index.html`.
- Do not claim physical microphone, global hotkey, or clipboard integration is automated; provide a manual smoke test.
- Code signing is deferred until a signing certificate or Azure Trusted Signing account exists.

---

### Task 1: Lock Pillow/Tk imports into the PyInstaller specification

**Files:**
- Modify: `SimpleSpeech.spec:16`
- Modify: `tests/test_packaging.py:5-14`

**Interfaces:**
- Consumes: PyInstaller `Analysis(hiddenimports=[...])` configuration.
- Produces: an explicit `hiddenimports` list containing `PIL.ImageTk` and `PIL._imagingtk`.

- [ ] **Step 1: Write the failing test**

```python
def test_spec_collects_pillow_tk_runtime(self):
    spec = Path(__file__).parents[1] / "SimpleSpeech.spec"
    contents = spec.read_text(encoding="utf-8")

    self.assertIn("PIL.ImageTk", contents)
    self.assertIn("PIL._imagingtk", contents)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging.PackagingSpecTests.test_spec_collects_pillow_tk_runtime -v
```

Expected: `FAIL` because `PIL.ImageTk` and `PIL._imagingtk` are not both explicitly present in `SimpleSpeech.spec`.

- [ ] **Step 3: Write the minimal implementation**

Replace the spec’s `hiddenimports` list with:

```python
hiddenimports=['pystray', 'PIL.Image', 'PIL.ImageTk', 'PIL._imagingtk'],
```

- [ ] **Step 4: Run the packaging-spec tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging -v
```

Expected: every test passes.

- [ ] **Step 5: Commit**

```powershell
git add SimpleSpeech.spec tests/test_packaging.py
git commit -m "fix: bundle Pillow Tk runtime"
```

### Task 2: Validate files produced by a clean PyInstaller build

**Files:**
- Modify: `tests/test_packaging.py:1-25`
- Modify: `.github/workflows/release.yml:20-22`

**Interfaces:**
- Consumes: frozen folder path passed on the command line, for example `dist\SimpleSpeech`.
- Produces: exit status 0 only when VAD, `PIL\ImageTk.py`, and `PIL\_imagingtk*.pyd` exist in the frozen folder.

- [ ] **Step 1: Write the failing test/helper contract**

Add this testable helper to `tests/test_packaging.py`:

```python
def required_frozen_paths(app_dir: Path) -> list[Path]:
    pil_dir = app_dir / "_internal" / "PIL"
    return [
        app_dir / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
        pil_dir / "ImageTk.py",
    ]
```

Then add a test that creates a temporary fake frozen folder containing only the VAD file and asserts the missing `ImageTk.py` is reported.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging.PackagingSpecTests.test_frozen_validation_reports_missing_pillow_tk_files -v
```

Expected: `FAIL` because no frozen-folder validation exists.

- [ ] **Step 3: Implement a build-artifact validator**

Implement `validate_frozen_app(app_dir: Path) -> list[str]` in `tests/test_packaging.py`. It must report a missing path for every required static file and report `PIL/_imagingtk*.pyd` when no matching bridge binary is present. Add a `__main__` command-line mode that exits nonzero and prints every missing path.

- [ ] **Step 4: Run the packaging tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging -v
```

Expected: every test passes.

- [ ] **Step 5: Add CI validation after PyInstaller build**

Add this workflow step immediately after `Build application folder`:

```yaml
      - name: Verify frozen runtime dependencies
        run: python tests/test_packaging.py dist/SimpleSpeech
```

- [ ] **Step 6: Build locally and validate the real artifact**

Run:

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm SimpleSpeech.spec
.\.venv\Scripts\python.exe tests\test_packaging.py dist\SimpleSpeech
```

Expected: the validator exits 0.

- [ ] **Step 7: Commit**

```powershell
git add tests/test_packaging.py .github/workflows/release.yml
git commit -m "test: verify frozen runtime dependencies"
```

### Task 3: Make upgrade behavior explicit and release a patch installer

**Files:**
- Modify: `installer/SimpleSpeech.iss:2-4,17-31`
- Modify: `CHANGELOG.md:3`
- Modify: `README.md:67-83`

**Interfaces:**
- Consumes: `dist\SimpleSpeech\*` generated by PyInstaller.
- Produces: `release\SimpleSpeech-Setup-1.0.2.exe` installed per user under `%LOCALAPPDATA%\Programs\SimpleSpeech` with the same `AppId` as prior releases.

- [ ] **Step 1: Write the failing installer-spec test**

Add a test to `tests/test_packaging.py` that reads `installer/SimpleSpeech.iss` and asserts:

```python
self.assertIn('#define MyAppVersion "1.0.2"', contents)
self.assertIn('AppId={{3E4567F6-0A13-4F53-AE91-C135AE8E869B}', contents)
self.assertIn('DefaultDirName={localappdata}\\Programs\\{#MyAppName}', contents)
self.assertNotIn('SimpleSpeech\\recordings', contents)
self.assertNotIn('simplespeech.log', contents)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging.PackagingSpecTests.test_installer_uses_stable_per_user_upgrade_identity -v
```

Expected: `FAIL` because the installer version is still `1.0.1`.

- [ ] **Step 3: Implement the patch-release metadata**

Change the installer version to `1.0.2`. Add this changelog entry:

```markdown
## 1.0.2 — 2026-07-11

- Fix Windows installer packaging by explicitly bundling Pillow’s `ImageTk` module and native `_imagingtk` bridge required by the status overlay.
- Verify frozen release artifacts contain the Silero VAD model and required Pillow/Tk files before installer creation.
```

Update README’s installer output example to `SimpleSpeech-Setup-1.0.2.exe`, and add an upgrade/uninstall note: upgrades replace program files but preserve `%LOCALAPPDATA%\SimpleSpeech` logs and temporary-recording directory; uninstall removes program files and also preserves that user data.

- [ ] **Step 4: Run the packaging tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_packaging -v
```

Expected: every test passes.

- [ ] **Step 5: Build the installer and inspect it**

Run:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\SimpleSpeech.iss
Get-FileHash release\SimpleSpeech-Setup-1.0.2.exe -Algorithm SHA256
```

Expected: the installer exists and PowerShell prints a SHA-256 value.

- [ ] **Step 6: Commit**

```powershell
git add installer/SimpleSpeech.iss CHANGELOG.md README.md tests/test_packaging.py
git commit -m "release: prepare 1.0.2 installer"
```

### Task 4: Add an end-to-end Windows release smoke-test checklist

**Files:**
- Create: `docs/windows-release-smoke-test.md`
- Modify: `README.md:83-95`

**Interfaces:**
- Consumes: `SimpleSpeech-Setup-1.0.2.exe` on a Windows user account.
- Produces: a documented pass/fail record for installer, tray, microphone, hotkey, raw dictation, refined fallback, paste behavior, upgrade, and uninstall.

- [ ] **Step 1: Write the checklist document**

Create a checklist with these numbered acceptance tests:

```markdown
1. Install `SimpleSpeech-Setup-1.0.2.exe`; confirm Start Menu, Apps uninstall entry, and tray icon appear.
2. In Notepad, hold Alt, say “SimpleSpeech raw dictation test”, release Alt; confirm that text is pasted into Notepad.
3. With Ollama stopped, hold Alt+Shift, say “fallback test”, release; confirm raw text is pasted and the status says `Ollama unavailable — pasted raw text`.
4. Start Ollama with `qwen3.5:0.8b`; repeat Alt+Shift and confirm the refined text is pasted.
5. Use tray Pause Dictation; confirm Alt produces no recording. Resume and confirm it records again.
6. Quit from the tray; confirm the tray icon disappears and no dictation occurs.
7. Upgrade by running the same or newer installer; confirm the app launches and `%LOCALAPPDATA%\SimpleSpeech\simplespeech.log` remains.
8. Uninstall from Windows Apps; confirm `%LOCALAPPDATA%\Programs\SimpleSpeech` is removed while `%LOCALAPPDATA%\SimpleSpeech` remains.
```

- [ ] **Step 2: Link the checklist from README**

Add:

```markdown
Before publishing a release, run the [Windows release smoke-test checklist](docs/windows-release-smoke-test.md) on a Windows machine or separate Windows account.
```

- [ ] **Step 3: Commit**

```powershell
git add docs/windows-release-smoke-test.md README.md
git commit -m "docs: add Windows release smoke test"
```

### Task 5: Final verification and release handoff

**Files:**
- Verify: `tests/test_runtime_and_refiner.py`
- Verify: `tests/test_packaging.py`
- Verify: `dist\SimpleSpeech\_internal\PIL\ImageTk.py`
- Verify: `dist\SimpleSpeech\_internal\PIL\_imagingtk*.pyd`
- Verify: `release\SimpleSpeech-Setup-1.0.2.exe`

**Interfaces:**
- Consumes: completed implementation and local build tools.
- Produces: verified release candidate plus manual test instructions.

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Rebuild and revalidate the frozen application**

Run:

```powershell
Remove-Item -Recurse -Force build\SimpleSpeech, dist\SimpleSpeech -ErrorAction SilentlyContinue
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm SimpleSpeech.spec
.\.venv\Scripts\python.exe tests\test_packaging.py dist\SimpleSpeech
```

Expected: clean build succeeds and the validator exits 0.

- [ ] **Step 3: Build and checksum the installer**

Run:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\SimpleSpeech.iss
Get-FileHash release\SimpleSpeech-Setup-1.0.2.exe -Algorithm SHA256
```

Expected: installer and checksum exist.

- [ ] **Step 4: Perform manual tests before publishing**

Use `docs\windows-release-smoke-test.md`. The user performs microphone, global-hotkey, focus restoration, and target-app paste tests because they require the real desktop session.

- [ ] **Step 5: Commit verified changes**

```powershell
git status --short
git log --oneline -5
```

Expected: only the intentional commits are present; untracked `index.html` remains untouched.
