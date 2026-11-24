"""Run spoken commands: open an app, search inside an app, open a terminal in a folder. Never pastes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

from window_focus import UiaSearchBox, focus_app, focus_new, is_foreground
from voice_commands import AMBIGUOUS, UNKNOWN, Command, Known, parse

CHROME_STATE = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State"
# wt.exe is an app alias in WindowsApps; a process started without that folder on PATH (measured) can't find it by name.
WT = shutil.which("wt.exe") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# app (lower case) -> shortcut that opens its search box (WhatsApp's box once showed a stray "/")
SEARCH_KEYS = {"slack": ("ctrl", "k"), "t3 code": ("ctrl", "k"), "whatsapp": ("ctrl", "alt", "/")}
# Enter opens the top result. Not T3 Code: its Enter on no match made a "New thread"; it just shows results.
PRESS_ENTER = {"slack", "whatsapp"}
BOX_WAIT_S, POLL_S = 1.5, 0.05
NOTHING_TYPED = "Search box not found \u2014 nothing typed"
NOTHING_SENT = "Search box not found \u2014 nothing sent"


REFRESH_S = 15 * 60
SKIP_DIRS = {"node_modules", ".git", "$recycle.bin", "system volume information", "__pycache__",
             ".venv", "venv", "dist", "build", ".next"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


class FolderIndex:
    """Folder names -> paths, built in the background and refreshed every REFRESH_S. A command only reads it."""

    def __init__(self, roots, logger=None, refresh_s=REFRESH_S):
        self._roots, self._logger, self._refresh_s = roots, logger, refresh_s
        self._names: dict[str, list[str]] = {}
        self.ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                self.build()
            except Exception:
                if self._logger:
                    self._logger.exception("Folder index build failed")
            time.sleep(self._refresh_s)

    def build(self) -> None:
        started, names = time.monotonic(), {}
        for root in self._roots():
            stack = [str(root)]
            while stack:
                try:
                    with os.scandir(stack.pop()) as entries:
                        for e in entries:
                            if not e.is_dir(follow_symlinks=False) or e.is_junction():
                                continue
                            if key := _norm(e.name):
                                names.setdefault(key, []).append(e.path)
                            # a skipped or dot folder's own name stays findable; we just don't go inside
                            if e.name.casefold() not in SKIP_DIRS and not e.name.startswith("."):
                                stack.append(e.path)
                except OSError:
                    continue
        self._names = names
        self.ready.set()
        if self._logger:
            self._logger.info("Folder index built; ms=%d; entries=%d",
                              (time.monotonic() - started) * 1000, sum(map(len, names.values())))

    def find(self, words, under=None) -> list[Path]:
        """Folders whose normalized name equals the last word and whose parent path holds the earlier words in order."""
        *hints, last = [_norm(w) for w in words]
        prefix = os.path.normcase(str(under)).rstrip("\\/") if under else None
        found = []
        for path in self._names.get(last, ()):
            if prefix and not os.path.normcase(path).startswith(prefix + os.sep):
                continue
            parts = iter(_norm(p) for p in Path(path).parent.parts[1:])
            if all(h in parts for h in hints):  # `in` on an iterator keeps the order
                found.append(Path(path))
        return found


def fixed_drives() -> list[Path]:
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    roots = [f"{chr(65 + i)}:\\" for i in range(26) if mask >> i & 1]
    return [Path(r) for r in roots if ctypes.windll.kernel32.GetDriveTypeW(r) == 3]  # 3 = fixed disk


def default_index_roots(folder_roots, drive_root, drives=fixed_drives, system_drive=None) -> list[Path]:
    """The folder_roots setting if set, else every fixed drive except the system drive."""
    if folder_roots:
        return [drive_root(str(r)[:1]) for r in folder_roots if str(r)[:1].isalpha()]
    system = (system_drive or os.environ.get("SystemDrive", "C:")).upper()
    return [d for d in drives() if str(d)[:2].upper() != system]


def drive_root(letter: str) -> Path:
    return Path(f"{letter.upper()}:\\")


class _FocusLost(Exception):
    pass


class PynputKeys:
    """Real key sender. One event per call, so the runner can check the window before each."""
    _NAMES = {"ctrl", "alt", "shift", "enter", "esc", "backspace", "f13"}

    def __init__(self, controller=None):
        from pynput import keyboard
        self._kb, self._c = keyboard, controller or keyboard.Controller()

    def _key(self, name):
        return getattr(self._kb.Key, name) if name in self._NAMES else name

    def chord(self, *names):
        pressed = []
        try:
            for name in names:
                key = self._key(name)
                self._c.press(key)
                pressed.append(key)
        finally:
            for key in reversed(pressed):
                self._c.release(key)

    def release_modifiers(self):
        for key in (self._kb.Key.ctrl, self._kb.Key.alt, self._kb.Key.shift):
            self._c.release(key)

    def type_char(self, char):
        self._c.type(char)

    def tap(self, name):
        self._c.tap(self._key(name))


def known_from(settings: dict, chrome_state: dict | None) -> Known:
    """Personal names come from settings.json (self_name, default_account, orgs, workspaces) and Chrome."""
    def text(key):
        value = settings.get(key)
        return value if isinstance(value, str) else ""

    orgs = settings.get("orgs")
    spaces = settings.get("workspaces")
    try:
        cache = chrome_state["profile"]["info_cache"].values()
        accounts = tuple(sorted({p["user_name"] for p in cache if p.get("user_name")}))
    except (TypeError, KeyError, AttributeError):
        accounts = ()
    return Known(
        accounts=accounts,
        self_name=text("self_name"),
        default_account=text("default_account"),
        orgs={str(k).casefold(): str(v) for k, v in orgs.items()} if isinstance(orgs, dict) else {},
        workspaces=tuple(str(w) for w in spaces) if isinstance(spaces, list) else (),
    )


def read_chrome_state(path: Path = CHROME_STATE) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def chrome_profile(state: dict | None, email: str) -> str | None:
    """The Chrome profile folder ("Profile 7") whose signed-in email is this one, or None."""
    try:
        for folder, info in state["profile"]["info_cache"].items():
            if str(info.get("user_name", "")).casefold() == email.casefold():
                return folder
    except (TypeError, KeyError, AttributeError):
        pass
    return None


def _app_paths_chrome() -> str | None:
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                return winreg.QueryValueEx(key, "")[0]
        except OSError:
            continue
    return None


def find_chrome(registry=_app_paths_chrome, exists=os.path.isfile, env=os.environ) -> str | None:
    """chrome.exe from the App Paths registry key, else the usual install folders."""
    candidates = [registry()] + [os.path.join(env[var], "Google", "Chrome", "Application", "chrome.exe")
                                 for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if env.get(var)]
    return next((c for c in candidates if c and exists(c)), None)


def get_start_apps() -> list[dict]:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"],
        capture_output=True, timeout=60, creationflags=_NO_WINDOW,
    ).stdout
    data = json.loads(out.decode("utf-8"))
    return data if isinstance(data, list) else [data]


class CommandRunner:
    def __init__(self, logger=None, known: Known | None = None, start_apps=get_start_apps,
                 launch=subprocess.Popen, focus=focus_app, wait: float = 0.5, retry_delay: float = 5.0,
                 keys=None, in_front=is_foreground, pause=time.sleep, box=None, clock=time.monotonic,
                 new_window=focus_new, drive_root=drive_root, folder_roots=lambda: (), index_roots=None,
                 sites_provider=lambda: {}, chrome_state=read_chrome_state, chrome_path=find_chrome, known_provider=None):
        self.logger = logger
        self.known = known or Known()
        self._known_provider = known_provider  # rebuilt on every command: new Chrome profiles and settings apply without restart
        self._chrome_state, self._chrome_path = chrome_state, chrome_path
        self._sites = sites_provider  # saved websites, read on every command so edits apply without restart
        self._start_apps = start_apps
        self._launch = launch
        self._focus = focus
        self._wait = wait
        self._retry_delay = retry_delay
        self._keys = keys
        self._in_front = in_front
        self._pause = pause
        self._box = box
        self._clock = clock
        self._new_window = new_window
        self._drive_root = drive_root
        self._folder_roots = folder_roots
        self._index = FolderIndex(
            index_roots or (lambda: default_index_roots(self._folder_roots(), self._drive_root)), logger)
        self.focused_at: float | None = None  # clock time the app came to the front, for action_ms
        self._apps: list[dict] = []
        self._ready = threading.Event()
        self._loader: threading.Thread | None = None
        self._lock = threading.Lock()  # guards starting the loader only; never held while PowerShell runs

    def warm(self) -> None:
        """Read the Start apps list and index folders in the background; a command never waits long for them."""
        self._index.start()
        with self._lock:
            if self._loader is None:
                self._loader = threading.Thread(target=self._load_until_ready, daemon=True)
                self._loader.start()

    def _load_until_ready(self) -> None:
        while True:
            try:
                apps = [a for a in self._start_apps() if a.get("Name") and a.get("AppID")]
            except Exception:
                if self.logger:
                    self.logger.exception("Could not read Start apps; retrying")
                time.sleep(self._retry_delay)
                continue
            self._apps = apps
            self._ready.set()
            return

    def parse(self, text: str) -> Command | None:
        if self._known_provider:
            self.known = self._known_provider()
        return parse(text, replace(self.known, sites={**self.known.sites, **self._sites()}))

    def _app_id(self, name: str) -> str | None:
        wanted = name.casefold()
        apps = [(a["Name"].casefold(), a["AppID"]) for a in self._apps]
        for match in (lambda n: n == wanted, lambda n: n.startswith(wanted), lambda n: wanted in n):
            found = [(len(n), n, i) for n, i in apps if match(n)]
            if found:
                return min(found)[2]  # shortest name wins inside a tier
        return None

    def run(self, command: Command) -> tuple[bool, str]:
        if command.kind == "search":
            return self._search(command)
        if command.kind == "terminal":
            return self._terminal(command)
        if command.kind == "site":
            return self._site(command)
        if command.kind != "app":
            return False, "Not supported yet"
        return self._open(command.name)[:2]

    def _poll(self, check):
        """check() until it gives something truthy, at most BOX_WAIT_S."""
        deadline = self._clock() + BOX_WAIT_S
        while True:
            found = check()
            if found or self._clock() >= deadline:
                return found
            self._pause(POLL_S)

    def _search(self, command: Command) -> tuple[bool, str]:
        name = command.name
        shortcut = SEARCH_KEYS.get(name.casefold())
        if not shortcut or not command.target:
            return False, f"Search in {name} not supported yet"
        if command.workspace:
            return False, "Workspace switch not supported yet"
        ok, detail, hwnd = self._open(name)
        if not ok:
            return ok, detail
        if self._keys is None:
            self._keys = PynputKeys()
        if self._box is None:
            self._box = UiaSearchBox()  # created on the worker thread that uses it
        k, box, target = self._keys, self._box, command.target

        def send(key_event, *args):
            if not self._in_front(hwnd):  # safety: no key goes out unless that exact window is in front
                raise _FocusLost
            key_event(*args)

        def text(element):
            return (box.value_of(element) or "").strip()

        def give_up(detail):
            if self._in_front(hwnd):
                k.tap("esc")
            return False, detail

        def typed():
            return box.same(hwnd, element) and text(element) == target.strip()

        try:
            send(k.chord, *shortcut)
            if not self._poll(lambda: box.find(hwnd)):
                return give_up(NOTHING_TYPED)
            # Clear it even when it reads empty: WhatsApp's own "/" lands ~0.1 s after its box opens (measured).
            # Keys arrive in order, so this also removes a "/" that UI Automation has not shown yet.
            send(k.chord, "ctrl", "a")
            send(k.tap, "backspace")
            element = self._poll(lambda: (found := box.find(hwnd)) and not text(found) and found)
            if not element:
                return give_up(NOTHING_TYPED)
            for char in target:
                send(k.type_char, char)
            if not self._poll(typed):
                return give_up(NOTHING_SENT)
            if name.casefold() in PRESS_ENTER:
                if not typed():  # re-check right before Enter
                    return give_up(NOTHING_SENT)
                send(k.tap, "enter")
        except _FocusLost:
            return False, f"Couldn't focus {name} \u2014 nothing typed"
        except Exception:
            k.release_modifiers()
            raise
        return True, f"Searched {name} for {target}"

    def _site(self, command: Command) -> tuple[bool, str]:
        """Open the URL in Chrome in the profile of the spoken account (none spoken: the default account's profile)."""
        self.focused_at = None
        if command.account in (AMBIGUOUS, UNKNOWN):
            return False, f"Account not clear: {command.heard}"
        if not re.match(r"https?://", command.url):  # trust boundary: the URL goes on Chrome's command line
            return False, "Website address not allowed"
        flag = []
        state = self._chrome_state()
        if command.account:
            folder = chrome_profile(state, command.account)
            if not folder:
                return False, f"No Chrome profile for {command.account}"
        else:  # no person spoken = the user; no default or no profile for it: no flag, Chrome picks
            folder = chrome_profile(state, self.known.default_account) if self.known.default_account else None
        if folder:
            flag = [f"--profile-directory={folder}"]
        chrome = self._chrome_path()
        if not chrome:
            return False, "Couldn't find Chrome"
        # --new-window: without it a running Chrome opens a tab in an old window and no new window appears to focus (measured)
        argv = [chrome, *flag, "--new-window", command.url]  # a list, never a shell string

        def start():
            self._launch(argv)

        # ponytail: focus_new takes the newest Chrome window; a Chrome window opened by someone else in the same moment could be picked. Ceiling accepted; fix by matching the window title to the URL.
        try:
            hwnd = self._new_window("chrome", start)
        except OSError:
            if self.logger:
                self.logger.exception("Chrome launch failed")
            return False, f"Couldn't open {command.name}"
        if not hwnd:
            return False, "Couldn't bring Chrome to front"
        self.focused_at = self._clock()
        return True, f"Opened {command.name}"

    def _terminal(self, command: Command) -> tuple[bool, str]:
        self.focused_at = None
        under = None
        if command.drive:
            under = self._drive_root(command.drive)
            if not under.is_dir():
                return False, f"Drive {command.drive.upper()}: not found"
        if command.words:
            self._index.start()
            if not self._index.ready.wait(self._wait):
                return False, "Still indexing folders — try again in a moment"
            started = self._clock()
            matches = self._index.find((command.phrase,), under) if command.phrase else []
            matches = matches or self._index.find(command.words, under)
            matches = sorted(set(matches))
            if self.logger:
                self.logger.info("Folder search; ms=%d; matches=%d", (self._clock() - started) * 1000, len(matches))
            if not matches:
                return False, "Folder not found"
            if len(matches) > 1:
                return False, "Several folders match: " + "; ".join(str(m) for m in matches[:3])
            root = matches[0]
        elif under:
            root = under
        else:
            roots = default_index_roots(self._folder_roots(), self._drive_root, lambda: [])
            if len(roots) != 1:
                return False, "Say which drive"
            root = roots[0]
        if ";" in str(root):  # wt.exe splits its command line at ';'
            return False, "Folder name has ';' — can't open in Terminal"
        # Only a directory we resolved goes on the command line, never spoken text.
        argv = [WT, "-w", "new", "-d", str(root)] + (["cmd", "/k", "claude"] if command.run_claude else [])

        def start():
            self._launch(argv)

        try:
            hwnd = self._new_window("terminal", start)
        except OSError:
            if self.logger:
                self.logger.exception("Terminal launch failed")
            return False, "Couldn't open Terminal"
        if not hwnd:
            return False, "Couldn't bring Terminal to front"
        self.focused_at = self._clock()
        return True, f"Opened Terminal in {root}"

    def _open(self, name: str) -> tuple[bool, str, int | None]:
        self.focused_at = None
        self.warm()
        if not self._ready.wait(self._wait):
            return False, "Apps still loading \u2014 try again", None
        app_id = self._app_id(name)
        if not app_id:
            return False, f"Couldn't open {name}", None
        try:
            self._launch(["explorer.exe", rf"shell:AppsFolder\{app_id}"])
        except OSError:
            if self.logger:
                self.logger.exception("App launch failed")
            return False, f"Couldn't open {name}", None
        hwnd = self._focus(name)
        if not hwnd:
            return False, f"Couldn't bring {name} to front", None
        self.focused_at = self._clock()
        return True, f"Opened {name}", hwnd
