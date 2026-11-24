"""Run spoken commands. Slice 1.2: open an app. Nothing here types or pastes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from window_focus import focus_app
from voice_commands import AMBIGUOUS, UNKNOWN, Command, Known, parse

CHROME_STATE = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


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
                 launch=subprocess.Popen, focus=focus_app, wait: float = 0.5, retry_delay: float = 5.0):
        self.logger = logger
        self.known = known or Known()
        self._start_apps = start_apps
        self._launch = launch
        self._focus = focus
        self._wait = wait
        self._retry_delay = retry_delay
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
        if command.kind != "app":
            if command.account in (AMBIGUOUS, UNKNOWN):
                return False, "Account not clear"
            return False, "Not supported yet"
        self.warm()
        if not self._ready.wait(self._wait):
            return False, "Apps still loading \u2014 try again"
        app_id = self._app_id(command.name)
        if not app_id:
            return False, f"Couldn't open {command.name}"
        try:
            self._launch(["explorer.exe", rf"shell:AppsFolder\{app_id}"])
        except OSError:
            if self.logger:
                self.logger.exception("App launch failed")
            return False, f"Couldn't open {command.name}"
        if not self._focus(command.name):
            return False, f"Couldn't bring {command.name} to front"
        return True, f"Opened {command.name}"
