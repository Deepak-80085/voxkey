# VoxKey Repository Cleanup Design

## Goal

Make VoxKey a standalone repository at `E:\voxkey` that can be developed,
tested, packaged, and released without depending on `E:\simplespeech`.
Preserve SimpleSpeech unchanged as a legacy project.

## Current State

`E:\simplespeech-voxkey-v2` is a Git worktree. Its Git metadata is stored in:

```text
E:\simplespeech\.git\worktrees\simplespeech-voxkey-v2
```

Deleting or moving `E:\simplespeech` first would break the VoxKey checkout.
The public VoxKey repository also contains the inherited SimpleSpeech source,
installer, packaging configuration, tests, and documentation.

## Chosen Approach

1. Preserve `E:\simplespeech` and its untracked `index.html` unchanged.
2. Clone `https://github.com/Deepak-80085/voxkey.git` into `E:\voxkey`.
3. Perform the cleanup in the standalone clone.
4. Keep the existing Git history; do not rewrite or force-push it.
5. Verify the standalone clone before removing the old VoxKey worktree.
6. Remove `E:\simplespeech-voxkey-v2` through `git worktree remove` only after
   the standalone clone passes tests and packaging validation.

## VoxKey Runtime Files

The standalone repository keeps the active VoxKey implementation:

```text
voxkey_app.py
voxkey_controller.py
voxkey_events.py
voxkey_runtime.py
voxkey_ui.py
speech_models.py
writing_model.py
vocabulary.py
VoxKey.spec
installer\VoxKey.iss
asset\
benchmark\
```

It also keeps VoxKey public documentation, release automation, and tests that
exercise the active runtime.

## Legacy Files To Remove From VoxKey

The following belong to SimpleSpeech or an abandoned VoxKey UI and are not
part of the active `voxkey_app.py` runtime:

```text
app.py
calibration.py
database.py
refiner.py
runtime.py
startup.py
transcriber.py
ui.py
SimpleSpeech.spec
SimpleSpeech_Overview (1).docx
installer\SimpleSpeech.iss
docs\windows-release-smoke-test.md
```

SimpleSpeech-only tests will also be removed:

```text
tests\test_hotkey_service.py
tests\test_paste.py
tests\test_runtime_and_refiner.py
tests\test_startup.py
```

## Packaging Validation

`tests\test_packaging.py` currently combines a useful frozen-package validator
with SimpleSpeech-specific assertions for Pillow ImageTk, `SimpleSpeech.spec`,
and `installer\SimpleSpeech.iss`.

The useful faster-whisper VAD file check will move into
`tests\test_voxkey_packaging.py`. The ImageTk checks will be deleted because
the Qt VoxKey application does not use Tkinter or `PIL.ImageTk`.

The GitHub Actions workflow will call the VoxKey packaging validator directly.

## Documentation Cleanup

Public documentation will describe the application that actually ships:

- the HUD is visible only while Right Ctrl is held;
- processing happens without a post-release HUD;
- only start and successful-paste sounds currently exist;
- the installer version and release instructions are internally consistent;
- SimpleSpeech build and release instructions are removed from VoxKey.

Historical design documents and `flow.md` may remain as engineering history,
but they must be clearly distinguished from current product documentation.

## Git And Release Safety

- Do not delete or rewrite the `v2.1.0` tag.
- Do not replace the existing `v2.1.0` release asset again.
- Do not publish a release during repository cleanup.
- Use a new version and immutable tag for the next public installer.
- Push the cleanup as ordinary commits to the existing VoxKey repository.

## Verification

The cleanup is complete only when all of the following pass from `E:\voxkey`:

1. No active source, test, workflow, or packaging file imports or references
   the removed SimpleSpeech modules.
2. The complete VoxKey unit-test suite passes.
3. PyInstaller builds `dist\VoxKey` successfully.
4. The VoxKey-specific frozen-package validator passes.
5. Inno Setup builds the installer successfully.
6. Git remote and branch configuration point only to the VoxKey repository.
7. Temporarily making `E:\simplespeech` unavailable does not affect tests,
   packaging, or application startup from `E:\voxkey`.

## Non-Goals

This cleanup does not change dictation behavior, redesign the UI, repair the
known capture-failure HUD bug, replace Ollama, sign the installer, or publish a
new release. Those changes require separate designs after the repository has a
clean baseline.
