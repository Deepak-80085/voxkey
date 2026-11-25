# VoxKey architecture

```text
Configurable hold-hotkey listener
  -> capture original foreground HWND
  -> sounddevice microphone capture
  -> local faster-whisper small.en by default or selected distil-large-v3 (GPU when available, same-model CPU fallback)
  -> transcript starts with "open"?
       yes -> second Whisper pass with command words -> voice_commands.parse
              -> CommandRunner: launch / focus app, search box, website in Chrome, or Terminal in a folder (nothing pasted)
       no, or not a known command -> rule-based formatting
  -> restore HWND and Ctrl+V formatted text
```

Before formatting, `PersonalMemory` applies literal correction rules. It stores the last 50 successful paste texts, up to 20 review suggestions, snippets, and app-specific formatting choices in `%LOCALAPPDATA%\VoxKey\personal-memory.json`. A saved snippet is pasted as is, and minimal/bullet-note styles use deterministic local formatting. The captured target process name selects app-specific rules. When the user enables edit learning, a separate Windows UI Automation worker reads the focused editable field for up to two minutes after a successful paste. For long documents it reads a bounded region near the caret. It saves close spelling edits and distinctive names for that app and leaves broad or conflicting changes for review.

The hotkey service and processing worker never access Qt widgets. They publish immutable lifecycle events to `EventBus`. The Qt main thread drains those events to drive the transient HUD, sound feedback, tray status, and settings view. This prevents worker-thread UI access and keeps overlay animation separate from speech latency.

The formatting stage (`writing_model.py`) is rule-based and keeps the speech model's recognized words in order: filler removal, capitalization, final punctuation, preferred vocabulary casing, and explicit spoken formatting commands. There is no language-model writer.

Voice commands run before formatting. `voxkey_controller.py` checks whether the transcript starts with "open". If so it transcribes the clip a second time with the command words in the Whisper prompt (built-in app names plus the `command_words` setting). `voice_commands.py` is pure rules with no Windows calls: it accepts only a whole sentence of the form "open NAME ..." with fuzzy name matching, and returns a command or nothing. `command_runner.py` runs it: it launches apps through their Start-menu entry, brings the window to front (`window_focus.py`), and for Slack, T3 Code, and WhatsApp opens the search shortcut and types the name only after UI Automation confirms a search box in that exact window. For the terminal it resolves a drive or a folder from an in-memory folder index (built in the background, all non-system fixed drives by default) and starts Windows Terminal there, optionally running `claude`. For a website, the parser resolves a built-in or saved name to an address and an optional account phrase to an email (`Known` is rebuilt from `settings.json` and Chrome's `Local State` on every command). `CommandRunner._site` refuses any address not starting with `http://` or `https://`, finds the Chrome profile folder whose `user_name` is that email (no account spoken: `default_account`; no profile found for it: no flag), then starts `chrome.exe [--profile-directory=<folder>] --new-window <address>` as an argument list and brings the new window to the front. Saved websites live in `personal-memory.json`; malformed or non-http(s) entries are dropped when it loads. A command never pastes. Success plays the "complete" chime; failure shows a tray notification and plays an error beep. The HUD orb shows only while the hotkey is held. A sentence that is not a command continues down the normal paste path.

A named Windows mutex permits one VoxKey instance per user session. Runtime data lives under `%LOCALAPPDATA%\VoxKey`; installation lives separately under `%LOCALAPPDATA%\Programs\VoxKey`. First-run setup downloads a pinned Ollama archive, verifies its SHA-256 digest, and extracts it under the VoxKey runtime directory. Ollama is not run; only its CUDA libraries are loaded so Whisper can use the GPU.
