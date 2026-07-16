# VoxKey Windows acceptance test

Run this on a disposable or dedicated clean Windows 10/11 x64 account without Ollama installed. The test downloads several gigabytes and removes all VoxKey data during uninstall.

## Install and trust

1. Verify the installer checksum and Authenticode signature:

   ```powershell
   Get-FileHash .\VoxKey-Setup.exe -Algorithm SHA256
   Get-AuthenticodeSignature .\VoxKey-Setup.exe | Format-List Status,SignerCertificate
   ```

2. Require signature status `Valid`. Install for the current user and launch VoxKey.
3. Confirm settings opens automatically and reports speech/runtime/model setup progress instead of appearing frozen.
4. Interrupt the network during the writer-runtime download, restart VoxKey, and confirm the download resumes.
5. Confirm setup reaches `Ready` without installing a separate Ollama application.
6. Confirm VoxKey owns these paths:

   ```text
   %LOCALAPPDATA%\VoxKey\runtime\ollama\ollama.exe
   %LOCALAPPDATA%\VoxKey\models\speech
   %LOCALAPPDATA%\VoxKey\models\writer
   ```

7. Confirm the managed writer listens only on `127.0.0.1:11435`.

## Dictation

1. In Notepad, hold Right Ctrl, speak, and release. Confirm the orb appears only while held and polished text is pasted once.
2. Repeat with the F8 and F9 hotkey choices. Confirm the previous hotkey stops triggering immediately.
3. Select another microphone and confirm it takes effect without restarting.
4. Test short taps, long dictations, empty audio, writer failure, and twenty consecutive dictations. Confirm there is no raw-transcript fallback, stuck orb, duplicate paste, or microphone leak.
5. Verify start/completion sounds, then disable sounds and confirm the setting persists after restart.

## Windows integration

1. Enable **Start VoxKey with Windows**, sign out and back in, and confirm exactly one VoxKey process starts.
2. Disable it and confirm the `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoxKey` value is removed.
3. Test Notepad, a browser text box, Microsoft Office, and one Electron application.
4. Test an elevated target separately and document Windows integrity-level limitations.

## Diagnostics and repair

1. Corrupt a copied test speech model and confirm **Repair models** replaces it.
2. Confirm `%LOCALAPPDATA%\VoxKey\voxkey.log` contains setup, device, transcription, polishing, paste, and failure details.
3. Quit from the tray and confirm VoxKey and its managed Ollama child process exit.

## Uninstall

1. Run the VoxKey uninstaller.
2. Confirm the application directory, `%LOCALAPPDATA%\VoxKey`, shortcuts, autostart registry value, VoxKey process, and managed Ollama process are gone.
3. Reinstall once more to confirm a true clean setup succeeds.

Record Windows version, CPU, GPU, RAM, microphone, setup duration, and every failure before approving a release tag.
