"""User-reviewed, local dictation corrections and recent output."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


class PersonalMemory:
    STYLES = ("standard", "minimal", "bullet notes")

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = {"corrections": [], "suggestions": [], "history": [], "snippets": [], "styles": {}}
        self.load_error = None
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in self._data:
                    if isinstance(loaded.get(key), type(self._data[key])):
                        self._data[key] = loaded[key]
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.load_error = str(exc)

    def _save(self) -> None:
        if self.load_error:
            raise OSError("Personal memory file could not be read; open diagnostics to inspect it")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self.path.parent, suffix=".tmp") as file:
            json.dump(self._data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            temporary = Path(file.name)
        temporary.replace(self.path)

    def _check_editable(self) -> None:
        if self.load_error:
            raise OSError("Personal memory file could not be read; open diagnostics to inspect it")

    @staticmethod
    def _phrase(value: str, field: str) -> str:
        value = value.strip()
        if not value or len(value) > 60 or "\n" in value or not any(char.isalnum() for char in value):
            raise ValueError(f"{field} must be 1–60 characters and contain a letter or number")
        return value

    @staticmethod
    def _app(value: str | None) -> str | None:
        return value.casefold().strip() if value else None

    def list_corrections(self) -> list[dict]:
        with self._lock:
            return [dict(rule) for rule in self._data["corrections"]]

    def add_correction(self, heard: str, intended: str, app: str | None = None,
                       source: str | None = None) -> None:
        heard = self._phrase(heard, "Heard phrase")
        intended = self._phrase(intended, "Intended phrase")
        app = self._app(app)
        if heard.casefold() == intended.casefold() and heard == intended:
            raise ValueError("The correction must change the phrase")
        with self._lock:
            self._check_editable()
            rules = self._data["corrections"]
            key = (heard.casefold(), app)
            rules[:] = [rule for rule in rules if (rule["heard"].casefold(), rule.get("app")) != key]
            rule = {"heard": heard, "intended": intended, "app": app}
            if source:
                rule["source"] = source
            rules.append(rule)
            self._save()

    def delete_correction(self, heard: str, app: str | None = None) -> None:
        key = (heard.casefold(), self._app(app))
        with self._lock:
            self._check_editable()
            rules = self._data["corrections"]
            rules[:] = [rule for rule in rules if (rule["heard"].casefold(), rule.get("app")) != key]
            self._save()

    def list_suggestions(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._data["suggestions"]]

    def suggest_correction(self, heard: str, intended: str, app: str | None = None) -> None:
        heard = self._phrase(heard, "Heard phrase")
        intended = self._phrase(intended, "Intended phrase")
        if heard == intended:
            return
        app = self._app(app)
        with self._lock:
            self._check_editable()
            suggestions = self._data["suggestions"]
            key = (heard.casefold(), intended.casefold(), app)
            suggestions[:] = [item for item in suggestions if
                              (item["heard"].casefold(), item["intended"].casefold(), item.get("app")) != key]
            suggestions.append({"heard": heard, "intended": intended, "app": app})
            del suggestions[:-20]
            self._save()

    def learn_edit(self, heard: str, intended: str, app: str | None) -> bool:
        """Learn an edit without replacing a conflicting saved rule."""
        with self._lock:
            app = self._app(app)
            conflict = any(rule["heard"].casefold() == heard.casefold()
                           and rule.get("app") == app and rule["intended"] != intended
                           for rule in self._data["corrections"])
            if conflict:
                self.suggest_correction(heard, intended, app)
                return False
            self.add_correction(heard, intended, app, source="edit")
            return True

    def delete_suggestion(self, heard: str, intended: str, app: str | None = None) -> None:
        key = (heard.casefold(), intended.casefold(), self._app(app))
        with self._lock:
            self._check_editable()
            suggestions = self._data["suggestions"]
            suggestions[:] = [item for item in suggestions if
                              (item["heard"].casefold(), item["intended"].casefold(), item.get("app")) != key]
            self._save()

    def accept_suggestion(self, heard: str, intended: str, app: str | None = None) -> None:
        with self._lock:
            self._check_editable()
            key = (heard.casefold(), intended.casefold(), self._app(app))
            if not any((item["heard"].casefold(), item["intended"].casefold(), item.get("app")) == key
                       for item in self._data["suggestions"]):
                raise ValueError("Suggestion is no longer available")
            self.add_correction(heard, intended, app)
            self.delete_suggestion(heard, intended, app)

    def correct(self, text: str, app: str | None = None) -> str:
        app = self._app(app)
        with self._lock:
            rules = [rule for rule in self._data["corrections"] if rule.get("app") in (None, app)]
        if not rules:
            return text
        selected = {}
        for rule in rules:
            key = rule["heard"].casefold()
            if key not in selected or rule.get("app") == app:
                selected[key] = rule["intended"]
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(key) for key in sorted(selected, key=len, reverse=True)) + r")(?!\w)",
            re.IGNORECASE,
        )
        return pattern.sub(lambda match: selected[match.group().casefold()], text)

    def remember_output(self, text: str, app: str | None = None) -> None:
        with self._lock:
            self._check_editable()
            self._data["history"].append({
                "text": text, "app": self._app(app),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            self._data["history"] = self._data["history"][-50:]
            self._save()

    def history(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in reversed(self._data["history"])]

    def clear_history(self) -> None:
        with self._lock:
            self._check_editable()
            self._data["history"] = []
            self._save()

    def list_snippets(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._data["snippets"]]

    def add_snippet(self, cue: str, text: str) -> None:
        cue = self._phrase(cue, "Snippet cue")
        text = text.strip()
        if not text or len(text) > 5000:
            raise ValueError("Snippet text must be 1–5000 characters")
        with self._lock:
            self._check_editable()
            snippets = self._data["snippets"]
            snippets[:] = [item for item in snippets if item["cue"].casefold() != cue.casefold()]
            snippets.append({"cue": cue, "text": text})
            self._save()

    def delete_snippet(self, cue: str) -> None:
        with self._lock:
            self._check_editable()
            snippets = self._data["snippets"]
            snippets[:] = [item for item in snippets if item["cue"].casefold() != cue.casefold()]
            self._save()

    def snippet_for(self, text: str) -> str | None:
        cue = text.strip().rstrip(".!?").casefold()
        with self._lock:
            return next((item["text"] for item in self._data["snippets"] if item["cue"].casefold() == cue), None)

    def styles(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data["styles"])

    def style_for(self, app: str | None) -> str:
        with self._lock:
            return self._data["styles"].get(self._app(app), "standard")

    def set_style(self, app: str, style: str) -> None:
        app = self._phrase(app, "App name").casefold()
        if style not in self.STYLES:
            raise ValueError("Unknown style")
        with self._lock:
            self._check_editable()
            if style == "standard":
                self._data["styles"].pop(app, None)
            else:
                self._data["styles"][app] = style
            self._save()
