"""Run spoken commands: open an app (1.2), search inside an app (1.3). Never pastes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from window_focus import focus_app, is_foreground
from voice_commands import AMBIGUOUS, UNKNOWN, Command, Known, parse

CHROME_STATE = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# app (lower case) -> shortcut that opens its search box; WhatsApp's box is cleared first (it once showed "//")
SEARCH_KEYS = {"slack": ("ctrl", "k"), "t3 code": ("ctrl", "k"), "whatsapp": ("ctrl", "alt", "/")}


class PynputKeys:
    """Real key sender. One event per call, so the runner can check the window before each."""
    _NAMES = {"ctrl": "ctrl", "alt": "alt", "enter": "enter"}

    def __init__(self):
        from pynput import keyboard
        self._kb, self._c = keyboard, keyboard.Controller()

    def _key(self, name):
        return getattr(self._kb.Key, name) if name in self._NAMES else name

    def chord(self, *names):
        keys = [self._key(n) for n in names]
        for k in keys:
            self._c.press(k)
        for k in reversed(keys):
            self._c.release(k)

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
                 keys=None, in_front=is_foreground, pause=time.sleep):
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
        if command.kind != "app":
            if command.account in (AMBIGUOUS, UNKNOWN):
                return False, "Account not clear"
            return False, "Not supported yet"
        return self._open(command.name)

    def _search(self, command: Command) -> tuple[bool, str]:
        name = command.name
        shortcut = SEARCH_KEYS.get(name.casefold())
        if not shortcut or not command.target:
            return False, f"Search in {name} not supported yet"
        if command.workspace:
            return False, "Workspace switch not supported yet"
        ok, detail = self._open(name)
        if not ok:
            return ok, detail
        if self._keys is None:
            self._keys = PynputKeys()
        k, wait = self._keys, self._pause
        steps = [(wait, (0.3,)), (k.chord, shortcut), (wait, (0.3,))]  # the search box needs a moment to open
        if name.casefold() == "whatsapp":
            steps += [(k.chord, ("ctrl", "a")), (wait, (0.15,))]
        steps += [(k.type_char, (c,)) for c in command.target] + [(wait, (0.4,)), (k.tap, ("enter",))]
        for send, args in steps:
            if send != wait and not self._in_front(name):  # safety: no key goes out unless the app is in front
                return False, f"Couldn't focus {name} — nothing typed"
            send(*args)
        return True, f"Searched {name} for {command.target}"

    def _open(self, name: str) -> tuple[bool, str]:
        self.warm()
        if not self._ready.wait(self._wait):
            return False, "Apps still loading \u2014 try again"
        app_id = self._app_id(name)
        if not app_id:
            return False, f"Couldn't open {name}"
        try:
            self._launch(["explorer.exe", rf"shell:AppsFolder\{app_id}"])
        except OSError:
            if self.logger:
                self.logger.exception("App launch failed")
            return False, f"Couldn't open {name}"
        if not self._focus(name):
            return False, f"Couldn't bring {name} to front"
        return True, f"Opened {name}"
