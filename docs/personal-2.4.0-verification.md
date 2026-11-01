# VoxKey 2.4.0 personal verification (2026-10-04)

## Build and installed app

- `python -m unittest discover -s tests -q`: 114 tests passed after the 2.4.0
  version and CI paths were updated.
- PyInstaller built `dist/VoxKey`, and Inno Setup compiled
  `release/VoxKey-Setup-2.4.0.exe`. Installer SHA-256:
  `7A57D0FC5FE877A95CFE3FE182F5BB9714B258DE0772C59A23A09DBC690C9DB8`.
- The silent local installer exited 0. The installed `VoxKey.exe` reports
  version 2.4.0 and matches the PyInstaller executable by SHA-256.
- The final installed process PID 13580 reached `Ready` in
  `%LOCALAPPDATA%\VoxKey\voxkey.log` at 01:25:28 local time, after logging start
  at 01:25:17. This is one startup observation, not a median.

## Accuracy and speed

- The three consented prompted recordings (32 reference words) still scored
  6.25% WER on `small.en` with beam 1. Clips transcribed in 1.688, 0.916, and
  0.916 seconds on the GPU. The writer's fast path took 2–3 ms per clip. No
  recognition model changed in this feature update.
- A 100-rule local correction lookup took 0.182 ms per call in a 1,000-call
  synthetic run. This measures string processing, not disk persistence or
  end-to-end dictation.
- At one final-build `Ready` observation, VoxKey used 401.5 MiB working set and the GTX
  1650 had 2,256 MiB GPU memory free. These are point-in-time values.

## Remaining verification

- At 01:31 local time, the installed 2.4.0 app captured a user dictation into
  `chatgpt.exe`: 75 output characters, 1,610 ms speech recognition, 15 ms
  formatting, and a successful paste 2,156 ms after processing began. The text
  matched the user's visible chat message. A reference recording of intended
  words is unavailable, so this does not measure word accuracy.
- Three later successful live pastes took 1,625 ms (83 characters), 2,141 ms
  (252 characters), and 2,000 ms (209 characters) after processing began. The
  latest of these spent 1,453 ms in speech recognition and 15 ms in formatting.
  An additional 62 ms empty-audio attempt produced no paste and is excluded.
  The earlier 2.3.0 example took 1,594 ms for 52 characters; these are
  different utterances, so they do not establish a speed gain or regression.
- Confirmation that the packaged Personal memory tabs open is still pending.
  Automated Qt tests cover the dialog, but do not prove tray use in the
  installed executable.
- No matched Wispr Flow output exists for these recordings. No claim of an
  accuracy or latency win over Flow is supported.
