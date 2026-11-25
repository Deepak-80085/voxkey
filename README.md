# VoxKey

<p align="center">
  <img src="asset/logo.png" alt="VoxKey logo" width="180">
</p>

**Private, local voice typing for Windows.** Hold your selected hotkey, speak naturally, release, and VoxKey pastes polished English text back into the app you were using.

VoxKey stays out of sight while idle. A small animated orb appears only while
the hotkey is held; it disappears immediately on release while transcription,
polishing, and paste continue locally in the background.

## Local-first by design

- English-only speech recognition using local `small.en` by default, with a local `distil-large-v3` option for this PC (never `base.en`).
- Fast rule-based formatting that never changes recognized words: filler removal, capitalization, final punctuation, and preferred vocabulary casing. Spoken “new line,” “new paragraph,” “bullet point,” “question mark,” “exclamation point,” and “full stop” format directly.
- Personal memory stores phrase corrections, the last 50 successful dictations, snippets, and app-specific formatting styles on this PC. Enable **Learn from edits** in Settings to learn from a brief edit to VoxKey's own paste. Open **Personal memory** from the tray to review suggestions or delete rules.
- A snippet cue spoken by itself pastes its saved text. Minimal and bullet-note app styles also format locally. Explicit single-word backtracks such as “two, actually three” keep the correction.
- No account, subscription, API key, cloud transcription, or failure-time raw-text fallback.
- Speech failure means no paste.

## Requirements

- Windows 10/11 x64
- NVIDIA GPU is optional; VoxKey uses it when the local runtime is available and otherwise uses the selected speech model on CPU.
- Internet access and several gigabytes of free disk space are required during first-run setup. Dictation works offline after setup.

## Install and use

1. Download the latest `VoxKey-Setup-*.exe` from Releases.
2. Install for the current Windows user.
3. Start VoxKey and keep it open while it downloads and verifies its private speech model and GPU speech runtime.
4. Wait for `Ready`, click into any ordinary app, hold **Right Ctrl**, **F8**, or **F9**, speak, then release it.

The tray menu opens settings, selects the microphone, toggles sounds, repairs
models, changes the hold hotkey, edits custom vocabulary and personal memory, enables Windows autostart, opens diagnostics,
and quits VoxKey. No separate Ollama installation or command is required.

> Releases may be unsigned until a trusted signing configuration is available. Unsigned Windows builds can be blocked by Smart App Control or SmartScreen; always verify the release checksum and read the release security notice.

## Voice commands

Hold the hotkey and start with "open" to run a command instead of typing. Everything else is typed as before, and so is "open" followed by a name VoxKey does not know. A command that fails shows a tray notification, plays an error beep, and types nothing.

- Apps: "open Slack", "open T3 Code", "open Claude", "open ChatGPT", "open WhatsApp".
- Search inside an app: "open the design channel in Slack", "open the Sam chat in WhatsApp", "open the release thread in T3 Code". VoxKey opens the app, types the name into its search box, and presses Enter. In T3 Code it shows the results without pressing Enter.
- Websites: "open YouTube", "open YouTube Music", "open GitHub", "open Gmail", "open Google Meet". VoxKey opens the address in a new Chrome window. Add your own on **Personal memory → Websites**: a spoken name and an `http(s)://` address, for example "alex board" = `https://board.example.com`. Then "open alex board" opens it. A saved name that matches an app name is refused, and an app name wins over a website with the same name.
- Chrome account: add an account phrase to pick the Chrome profile whose signed-in email matches. "open Gmail in my account" and plain "open Gmail" both use `default_account`. "open Gmail in Sam account" uses the profile of the one email whose leading letters are "sam" (like sam@example.com). Add an org word from `orgs` ("open Gmail in my work account", "open Gmail in Sam work account") to pick `<person>@<that org's domain>`. VoxKey reads the profile emails from Chrome's `Local State` file; there is nothing to set up. If `default_account` is empty or has no Chrome profile, VoxKey adds no profile and Chrome uses its own choice.
- Terminal: "open the terminal in D drive", "open Claude Code in myproject" (finds a folder by name and starts `claude` there), "open the terminal in E drive, clients folder, demo, and run Claude Code".

Add personal names to `%LOCALAPPDATA%\VoxKey\settings.json`. All keys are optional; the values below are examples.

```json
{
  "self_name": "alex",
  "default_account": "alex@example.com",
  "orgs": {"work": "example.com"},
  "workspaces": ["example"],
  "command_words": ["Acme", "Sam"],
  "folder_roots": ["D:\\", "E:\\"]
}
```

`command_words` are extra names the speech model listens for on "open ..." sentences only. `folder_roots` limits where folders are searched; by default VoxKey indexes every fixed drive except the system drive, in memory, and refreshes the list every 15 minutes. `workspaces` lists Slack workspace names. These settings, saved websites, and Chrome's profile list are read again on every command, so changes apply without a restart. `folder_roots` is read when the folder list is rebuilt (every 15 minutes), so restart VoxKey to apply a change now.

Safety: VoxKey types only into a search box it has confirmed through Windows UI Automation, and only while the target window is in front. It never types into message boxes and never sends messages.

Errors: "Account not clear" means the words you said match no one profile, or more than one. "No Chrome profile for <email>" means Chrome has no profile signed in with that email. VoxKey refuses a saved website whose address does not start with `http://` or `https://`.

Limits: switching Slack workspaces is not supported yet. VoxKey brings to the front the newest Chrome window; if another Chrome window opens at the same moment it can pick that one.

## Limitations

- Windows secure-desktop screens (lock screen, UAC prompts, Ctrl+Alt+Del) cannot accept dictation.
- Windows may block input into an elevated application when VoxKey is not elevated. Run VoxKey as administrator only when you specifically need to dictate into an administrator-run app.
- A custom vocabulary can improve names and preferred casing, but it cannot guarantee that the speech model hears a similar sounding word correctly.
- Automatic learning is opt-in. It checks the focused field for two minutes after a successful paste; some apps do not expose editable text to Windows UI Automation. Distinctive names and terms already in your vocabulary apply across apps. Close ordinary spelling edits apply in the app where you made them. Broad rewrites and conflicting changes wait for approval in **Personal memory**.

To test: turn on **Learn from edits** in Settings, dictate “Open git hub” into a document, then change “git hub” to “GitHub” in that document within two minutes. Open **Personal memory → Corrections** to see the learned rule, then dictate the same phrase again. Close single-word spelling edits such as “cash” to “cache” also learn in that app without a second edit.

## Diagnostics and privacy

Settings and diagnostics are stored in `%LOCALAPPDATA%\VoxKey`. The latest diagnostic capture is `%LOCALAPPDATA%\VoxKey\last-dictation.wav`; delete it whenever you want. See [privacy details](docs/privacy.md).

## Build from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm VoxKey.spec
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\VoxKey.iss
```

See [architecture](docs/architecture.md), [Windows smoke testing](docs/windows-v0.1.0-smoke-test.md), [contributing](CONTRIBUTING.md), and [security](SECURITY.md).

## Local accuracy check

To collect known-text clips on your PC, run `.\.venv\Scripts\python.exe -m benchmark.record_prompts` from the repository and read each displayed sentence exactly. The clips and reference manifest are saved under ignored `benchmark/local_samples/personal/`. Compare with the same model settings used by VoxKey:

```powershell
.\.venv\Scripts\python.exe -m benchmark.run_benchmark --model small.en --manifest benchmark\local_samples\personal\manifest.json
.\.venv\Scripts\python.exe -m benchmark.run_benchmark --model distil-large-v3 --manifest benchmark\local_samples\personal\manifest.json --with-writer  # adds formatted text to each result
```

If you already have Wispr Flow output for the same spoken clips, add a `flow` string to each manifest entry. The benchmark then reports its word error rate beside VoxKey's. VoxKey does not send these recordings to Flow.
