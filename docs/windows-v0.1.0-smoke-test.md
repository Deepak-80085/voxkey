# VoxKey Windows reliability smoke test

Run against the installer-created application, not only the source tree.

1. Verify the locally built installer checksum. Do not upload it under the
   existing `v2.1.0` release:
   ```powershell
    Get-FileHash .\VoxKey-Setup-2.2.0.exe -Algorithm SHA256
    Get-Content .\VoxKey-Setup-2.2.0.exe.sha256
   ```
2. Install and launch VoxKey. Confirm the tray and settings open immediately
   while startup remains `Validating`, then reaches `Ready` without freezing Qt.
3. With Notepad focused, hold Right Ctrl for over 0.28 seconds. Verify only the
   small orb appears, Notepad keeps focus, and the listening cue plays.
4. Speak a short English sentence and release Right Ctrl. Verify the orb hides
   immediately, processing remains invisible, the exact polished result is
   pasted into Notepad, and the completion cue plays.
5. Repeat dictation twenty times, including short and long holds. Confirm no
   stuck orb, stuck microphone, duplicate paste, or unexplained process exit.
6. Trigger a microphone start or stop failure. Confirm the orb hides, the
   microphone is released, VoxKey enters `Needs repair`, and the traceback is
   present in `%LOCALAPPDATA%\VoxKey\voxkey.log`.
7. Back up the speech model, replace `model.bin` with a non-empty invalid file,
   and choose tray **Repair models**. Confirm settings remains responsive and
   repair downloads a fresh model before returning to `Ready`. Restore the
   backup only if repair fails.
8. Stop Ollama and dictate once. Confirm no raw transcript is pasted, VoxKey
   enters `Needs repair`, and restarting Ollama plus **Repair models** restores
   `Ready`.
9. Toggle sounds off, restart VoxKey, and confirm the preference persists.
   Open diagnostics and verify lifecycle timings plus `device=cuda` or the
   same-model CPU fallback.
10. Click tray **Quit VoxKey**, verify `VoxKey.exe` exits, then launch it twice.
    Confirm exactly one instance remains and startup returns to `Ready`.
11. Run a target as administrator. Verify VoxKey does not crash and document
    whether Windows blocks its input. Do not test secure-desktop screens.
