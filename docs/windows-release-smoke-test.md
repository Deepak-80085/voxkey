# Windows Release Smoke-Test Checklist

Run this checklist on a Windows machine or a separate Windows account before publishing a SimpleSpeech installer. Record each item as pass or fail, including a screenshot or the log excerpt for failures.

## Install and tray

1. Install `SimpleSpeech-Setup-1.0.2.exe`. Confirm the Start Menu shortcut, Windows Apps uninstall entry, and SimpleSpeech tray icon appear.
2. Open `%LOCALAPPDATA%\Programs\SimpleSpeech\_internal\PIL`. Confirm it contains an `_imagingtk*.pyd` file. The build pipeline verifies this too.

## Dictation workflow

3. Open Notepad, click its edit area, hold **Alt**, say `SimpleSpeech raw dictation test`, then release **Alt**. Confirm the transcription is pasted into Notepad.
4. Stop Ollama. In Notepad, hold **Alt + Shift**, say `fallback test`, then release. Confirm raw text is pasted and the status reports `Ollama unavailable — pasted raw text`.
5. Start Ollama and ensure `qwen3.5:0.8b` is installed. Repeat **Alt + Shift** dictation and confirm the refined text is pasted.
6. Use the tray menu to choose **Pause Dictation**. Confirm **Alt** does not start recording. Resume dictation and confirm it starts recording again.
7. Use the tray menu to choose **Quit**. Confirm the tray icon disappears and **Alt** no longer starts recording.

## Upgrade and uninstall

8. Before upgrading, confirm `%LOCALAPPDATA%\SimpleSpeech\simplespeech.log` exists. Run the same or a newer installer, launch the app, and confirm the log remains.
9. Uninstall SimpleSpeech from Windows Apps. Confirm `%LOCALAPPDATA%\Programs\SimpleSpeech` is removed while `%LOCALAPPDATA%\SimpleSpeech` remains for diagnostics.

## Failure reporting

10. If a check fails, use tray **Open Logs**, copy the relevant `%LOCALAPPDATA%\SimpleSpeech\simplespeech.log` lines, and attach them with the installer version and Windows version to a GitHub issue.
