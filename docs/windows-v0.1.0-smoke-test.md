# VoxKey v2.1.0 Windows smoke test

Run against the installer-created application, not only the source tree.

1. Verify the release checksum:
   ```powershell
   Get-FileHash .\VoxKey-Setup-2.1.0.exe -Algorithm SHA256
   Get-Content .\VoxKey-Setup-2.1.0.exe.sha256
   ```
2. Install, launch VoxKey, and verify its tray icon appears. Open settings and check Ready/Needs repair state, local data location, fixed Right Ctrl guidance, and sound toggle.
3. With Notepad focused, hold Right Ctrl for over 0.28 seconds. Verify the HUD appears without Notepad losing focus and the listening cue plays.
4. Speak a short English sentence, release Right Ctrl, and verify processing HUD states appear. Confirm the polished result is pasted in Notepad. Copy it back and compare exactly.
5. Verify the completion cue plays and HUD fades. Toggle sounds off, repeat, restart VoxKey, and confirm sounds stay off.
6. Trigger a writer or microphone failure. Verify the error cue/HUD is readable and no raw transcription is pasted.
7. Use tray **Repair models** and **Open diagnostics**. Confirm `%LOCALAPPDATA%\VoxKey\voxkey.log` contains lifecycle timings and selected device evidence.
8. Click tray **Quit VoxKey**, verify `VoxKey.exe` exits, then launch it again. Verify exactly one instance starts.
9. If GPU is available, confirm the fresh packaged-app log says the `small.en` speech model device is `cuda`; otherwise confirm same-model CPU fallback is logged.
10. Run a target as administrator. Verify VoxKey does not crash and document whether Windows blocks its input. Do not test secure-desktop screens.
