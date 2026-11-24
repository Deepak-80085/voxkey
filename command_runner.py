"""Run spoken commands: open an app, search inside an app, open a terminal in a folder. Never pastes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from window_focus import UiaSearchBox, focus_app, focus_new, is_foreground
from voice_commands import AMBIGUOUS, UNKNOWN, Command, Known, parse

CHROME_STATE = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# app (lower case) -> shortcut that opens its search box (WhatsApp's box once showed a stray "/")
SEARCH_KEYS = {"slack": ("ctrl", "k"), "t3 code": ("ctrl", "k"), "whatsapp": ("ctrl", "alt", "/")}
# Enter opens the top result. Not T3 Code: its Enter on no match made a "New thread"; it just shows results.
PRESS_ENTER = {"slack", "whatsapp"}
BOX_WAIT_S, POLL_S = 1.5, 0.05
NOTHING_TYPED = "Search box not found \u2014 nothing typed"
NOTHING_SENT = "Search box not found \u2014 nothing sent"


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
                 new_window=focus_new, drive_root=drive_root):
        self.logger = logger
        self.known = known or Known()
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
        self.focused_at: float | None = None  # clock time the app came to the front, for action_ms
        self._apps: list[dict] = []
        self._ready = threading.Event()
        self._loader: threading.Thread | None = None
        self._lock = threading.Lock()  # guards starting the loader only; never held while PowerShell runs

    def warm(self) -> None:
        """Read the Start apps list in the background (retrying if it fails); a command never waits long for it."""
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
        return parse(text, self.known)

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
        if command.kind != "app":
            if command.account in (AMBIGUOUS, UNKNOWN):
                return False, "Account not clear"
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

    def _terminal(self, command: Command) -> tuple[bool, str]:
        self.focused_at = None
        if not command.drive:
            return False, "Say which drive"
        root = self._drive_root(command.drive)
        if not root.is_dir():
            return False, f"Drive {command.drive.upper()}: not found"
        if command.words:
            return False, "Not supported yet"
        # Only a directory we resolved goes on the command line, never spoken text.
        argv = ["wt.exe", "-w", "new", "-d", str(root)] + (["cmd", "/k", "claude"] if command.run_claude else [])

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
