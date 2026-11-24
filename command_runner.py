"""Run spoken commands. Slice 1.2: open an app. Nothing here types or pastes."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

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
        ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"],
        capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW,
    ).stdout
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


class CommandRunner:
    def __init__(self, logger=None, known: Known | None = None, start_apps=get_start_apps, launch=subprocess.Popen):
        self.logger = logger
        self.known = known or Known()
        self._start_apps = start_apps
        self._launch = launch
        self._apps: list[dict] | None = None
        self._lock = threading.Lock()

    def warm(self) -> None:
        """Read the Start apps list in the background so the first command is fast."""
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> list[dict]:
        with self._lock:
            if self._apps is None:
                try:
                    self._apps = [a for a in self._start_apps() if a.get("Name") and a.get("AppID")]
                except Exception:
                    if self.logger:
                        self.logger.exception("Could not read Start apps")
                    return []  # try again on the next command
            return self._apps

    def parse(self, text: str) -> Command | None:
        return parse(text, self.known)

    def _app_id(self, name: str) -> str | None:
        wanted = name.casefold()
        apps = [(a["Name"].casefold(), a["AppID"]) for a in self._load()]
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
        app_id = self._app_id(command.name)
        if not app_id:
            return False, f"Couldn't open {command.name}"
        try:
            self._launch(["explorer.exe", rf"shell:AppsFolder\{app_id}"])
        except OSError:
            if self.logger:
                self.logger.exception("App launch failed")
            return False, f"Couldn't open {command.name}"
        return True, f"Opened {command.name}"
