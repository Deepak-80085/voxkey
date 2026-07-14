# Contributing to VoxKey

1. Create a branch from `main`.
2. Keep changes local-first: do not add cloud transcription, accounts, telemetry, or a raw-text paste fallback.
3. Add a failing regression test before production code for behavior changes.
4. Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

5. For UI, packaging, hotkey, audio, or paste changes, complete `docs/windows-v0.1.0-smoke-test.md` on Windows before opening a pull request.

Do not commit `%LOCALAPPDATA%` data, recordings, model files, installers, build directories, credentials, or `.superpowers` brainstorming artifacts.
