"""Native Qt presentation for VoxKey without coupling the dictation pipeline to Qt."""

from __future__ import annotations

import ctypes
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, Property, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QLabel, QLineEdit, QListWidget,
    QMessageBox, QMenu, QPlainTextEdit, QPushButton, QSystemTrayIcon,
    QTabWidget, QVBoxLayout, QWidget,
)

from voxkey_events import UiEvent
from voxkey_runtime import AppState
from vocabulary import normalize_vocabulary


@dataclass(frozen=True)
class HudView:
    visible: bool
    title: str
    detail: str
    mood: str


def should_render_hud(event: UiEvent) -> bool:
    """Only a held, active dictation capture controls the transient orb."""
    return event.kind in {"capture_started", "capture_stopped", "capture_failed"}


def hud_view_for(event: UiEvent) -> HudView:
    """Show a silent, text-free orb only while Right Ctrl is actively held."""
    if event.kind == "capture_started":
        return HudView(True, "", "", "listening")
    return HudView(False, "", "", "idle")


class SoundCue:
    """Short system sounds. Playback failure must never affect dictation."""

    @staticmethod
    def for_event(event: UiEvent) -> str | None:
        return {
            "capture_started": "start",
            "paste_succeeded": "complete",
            "pipeline_failed": "error",
            "capture_failed": "error",
        }.get(event.kind)


class SoundPlayer:
    """Play VoxKey's bundled SimpleSpeech MP3 cues without blocking dictation."""

    _SOUND_FILES = {"start": "starrt.mp3", "complete": "end.mp3"}

    def __init__(self, enabled: bool = True, logger=None, asset_dir: Path | None = None) -> None:
        self.enabled = enabled
        self.logger = logger
        self.asset_dir = asset_dir or Path(__file__).resolve().parent / "asset"

    def play(self, cue: str | None) -> None:
        if not cue or not self.enabled:
            return
        filename = self._SOUND_FILES.get(cue)
        if not filename or sys.platform != "win32":
            return
        path = self.asset_dir / filename
        if not path.is_file():
            if self.logger:
                self.logger.warning("VoxKey sound asset is missing: %s", path)
            return
        threading.Thread(target=self._play_mp3, args=(path, cue), daemon=True).start()

    def _play_mp3(self, path: Path, cue: str) -> None:
        try:
            winmm = ctypes.windll.winmm
            alias = f"voxkey_{cue}_{threading.get_ident()}"
            winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
            winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
            winmm.mciSendStringW(f"close {alias}", None, 0, None)
        except Exception:
            if self.logger:
                self.logger.exception("VoxKey sound cue failed: %s", cue)


class VoxKeyHud(QWidget):
    """A non-activating, mouse-transparent bottom-center status overlay."""

    _COLORS = {
        "listening": (QColor("#53e1ff"), QColor("#8d6dff"), QColor("#ff78b9")),
        "processing": (QColor("#8c9cff"), QColor("#8d6dff"), QColor("#ba8cff")),
        "success": (QColor("#67f0c0"), QColor("#61cfff"), QColor("#8d6dff")),
        "error": (QColor("#ff826e"), QColor("#f55b8c"), QColor("#d66dff")),
    }

    def __init__(self) -> None:
        super().__init__(None)
        self._view = HudView(False, "", "", "idle")
        self._orb_radius = 18.0
        self.setFixedSize(52, 52)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._breath = QPropertyAnimation(self, b"orbRadius", self)
        self._breath.setDuration(900)
        self._breath.setStartValue(15.0)
        self._breath.setKeyValueAt(0.5, 21.0)
        self._breath.setEndValue(15.0)
        self._breath.setLoopCount(-1)
        self._breath.setEasingCurve(QEasingCurve.InOutSine)

    def _position_bottom_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - self.height() - 36))

    def show_event(self, event: UiEvent) -> None:
        view = hud_view_for(event)
        if not view.visible:
            self._breath.stop()
            self.hide()
            return
        self._view = view
        self._position_bottom_center()
        self._orb_radius = 15.0
        self.show()
        self.raise_()
        self._breath.start()

    def _get_orb_radius(self) -> float:
        return self._orb_radius

    def _set_orb_radius(self, radius: float) -> None:
        self._orb_radius = float(radius)
        self.update()

    orbRadius = Property(float, _get_orb_radius, _set_orb_radius)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        colors = self._COLORS["listening"]
        radius = self._orb_radius
        gradient = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
        gradient.setColorAt(0, colors[0])
        gradient.setColorAt(0.48, colors[1])
        gradient.setColorAt(1, colors[2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))


class SettingsActions:
    """Small testable adapter between settings controls and local runtime."""

    def __init__(
        self,
        controller,
        runtime,
        sound_player=None,
        set_microphone=None,
        set_hotkey=None,
        set_autostart=None,
    ) -> None:
        self.controller = controller
        self.runtime = runtime
        self.sound_player = sound_player
        self._set_microphone = set_microphone
        self._set_hotkey = set_hotkey
        self._set_autostart = set_autostart

    def set_sounds_enabled(self, enabled: bool) -> None:
        settings = dict(self.runtime.load_settings())
        settings["sounds_enabled"] = bool(enabled)
        self.runtime.save_settings(settings)
        if self.sound_player:
            self.sound_player.enabled = bool(enabled)

    def repair(self) -> None:
        threading.Thread(target=self.controller.repair_models, daemon=True).start()

    def set_microphone(self, device) -> None:
        settings = dict(self.runtime.load_settings())
        settings["microphone"] = device
        self.runtime.save_settings(settings)
        if self._set_microphone:
            self._set_microphone(device)

    def set_hotkey(self, name: str) -> None:
        settings = dict(self.runtime.load_settings())
        settings["hotkey"] = name
        self.runtime.save_settings(settings)
        if self._set_hotkey:
            self._set_hotkey(name)

    def set_autostart(self, enabled: bool) -> None:
        settings = dict(self.runtime.load_settings())
        settings["start_with_windows"] = bool(enabled)
        self.runtime.save_settings(settings)
        if self._set_autostart:
            self._set_autostart(bool(enabled))

    def set_learn_from_edits(self, enabled: bool) -> None:
        settings = dict(self.runtime.load_settings())
        settings["learn_from_edits"] = bool(enabled)
        self.runtime.save_settings(settings)

    def set_vocabulary(self, text: str) -> None:
        settings = dict(self.runtime.load_settings())
        settings["vocabulary"] = normalize_vocabulary(text.splitlines())
        self.runtime.save_settings(settings)

    def open_diagnostics(self) -> None:
        import os
        os.startfile(self.runtime.data_dir())


class VoxKeyShell:
    """Tray-first Qt shell; the HUD never owns focus."""

    def __init__(
        self,
        controller,
        runtime,
        shutdown,
        microphones=(),
        set_microphone=None,
        hotkeys=(),
        set_hotkey=None,
        set_autostart=None,
        memory=None,
    ) -> None:
        self.controller, self.runtime, self.shutdown = controller, runtime, shutdown
        self.microphones = microphones
        self.hotkeys = hotkeys
        self.memory = memory
        self.memory_dialog = None
        self.hud = VoxKeyHud()
        self.sounds = SoundPlayer(runtime.load_settings()["sounds_enabled"], runtime.logger())
        self.actions = SettingsActions(
            controller,
            runtime,
            self.sounds,
            set_microphone,
            set_hotkey,
            set_autostart,
        )
        self.icon = QIcon(str(Path(__file__).resolve().parent / "asset" / "icon.ico"))
        self.tray = QSystemTrayIcon(self.icon)
        menu = QMenu()
        menu.addAction("Open settings", self.show_settings)
        memory_action = menu.addAction("Personal memory", self.show_memory)
        memory_action.setEnabled(memory is not None)
        self.sound_action = menu.addAction("Sounds on")
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(self.sounds.enabled)
        self.sound_action.toggled.connect(self.actions.set_sounds_enabled)
        menu.addAction("Repair models", self.actions.repair)
        menu.addAction("Open diagnostics", self.actions.open_diagnostics)
        menu.addSeparator()
        menu.addAction("Quit VoxKey", self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("VoxKey — local dictation")
        self.settings = self._make_settings()
        self.tray.show()

    def _make_settings(self) -> QDialog:
        dialog = QDialog()
        dialog.setWindowTitle("VoxKey settings")
        dialog.setWindowIcon(self.icon)
        layout = QVBoxLayout(dialog)
        title = QLabel("VoxKey")
        title.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        layout.addWidget(title)
        layout.addWidget(QLabel("Private local dictation. Hold your selected hotkey to speak."))
        self.health = QLabel()
        layout.addWidget(self.health)
        microphone = QComboBox()
        microphone.addItem("System default microphone", None)
        for device, name in self.microphones:
            microphone.addItem(name, device)
        selected = self.runtime.load_settings().get("microphone")
        selected_index = microphone.findData(selected)
        microphone.setCurrentIndex(max(0, selected_index))
        microphone.currentIndexChanged.connect(
            lambda _index: self.actions.set_microphone(microphone.currentData())
        )
        layout.addWidget(microphone)
        hotkey = QComboBox()
        for name, label in self.hotkeys:
            hotkey.addItem(label, name)
        selected_hotkey = self.runtime.load_settings().get("hotkey", "right_ctrl")
        hotkey.setCurrentIndex(max(0, hotkey.findData(selected_hotkey)))
        hotkey.currentIndexChanged.connect(
            lambda _index: self.actions.set_hotkey(hotkey.currentData())
        )
        layout.addWidget(hotkey)
        vocabulary = QPlainTextEdit()
        vocabulary.setPlaceholderText("Names and terms, one per line")
        vocabulary.setPlainText("\n".join(self.runtime.load_settings().get("vocabulary", [])))
        vocabulary.setFixedHeight(72)
        layout.addWidget(vocabulary)
        save_vocabulary = QPushButton("Save vocabulary")
        save_vocabulary.clicked.connect(
            lambda: self.actions.set_vocabulary(vocabulary.toPlainText())
        )
        layout.addWidget(save_vocabulary)
        if self.memory is not None:
            personal = QPushButton("Corrections and history")
            personal.clicked.connect(self.show_memory)
            layout.addWidget(personal)
            learn = QCheckBox("Learn from edits to recent dictation (2 minutes)")
            learn.setChecked(bool(self.runtime.load_settings().get("learn_from_edits")))
            learn.toggled.connect(self.actions.set_learn_from_edits)
            layout.addWidget(learn)
        checkbox = QCheckBox("Play voice feedback sounds")
        checkbox.setChecked(self.sounds.enabled)
        checkbox.toggled.connect(self.actions.set_sounds_enabled)
        checkbox.toggled.connect(self.sound_action.setChecked)
        layout.addWidget(checkbox)
        autostart = QCheckBox("Start VoxKey with Windows")
        autostart.setChecked(bool(self.runtime.load_settings().get("start_with_windows")))
        autostart.toggled.connect(self.actions.set_autostart)
        layout.addWidget(autostart)
        repair = QPushButton("Repair models")
        repair.clicked.connect(self.actions.repair)
        layout.addWidget(repair)
        diagnostics = QPushButton("Open diagnostics folder")
        diagnostics.clicked.connect(self.actions.open_diagnostics)
        layout.addWidget(diagnostics)
        dialog.resize(400, 340)
        return dialog

    def show_settings(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def show_memory(self) -> None:
        if self.memory is None:
            return
        if self.memory_dialog:
            self.memory_dialog.close()
            self.memory_dialog.deleteLater()
        dialog = QDialog(self.settings)
        dialog.setWindowTitle("VoxKey personal memory")
        dialog.setWindowIcon(self.icon)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        corrections_page = QWidget()
        tabs.addTab(corrections_page, "Corrections")
        layout = QVBoxLayout(corrections_page)
        if self.memory.load_error:
            layout.addWidget(QLabel("Memory file could not be read. Open diagnostics to inspect it."))
        layout.addWidget(QLabel("Recent dictations stay on this PC. Select one to correct a phrase."))
        history = self.memory.history()
        recent = QListWidget()
        recent.setFixedHeight(100)
        for item in history:
            recent.addItem(item["text"].replace("\n", " ")[:120])
        layout.addWidget(recent)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setFixedHeight(80)
        layout.addWidget(preview)
        scope = QComboBox()
        heard = QLineEdit()
        intended = QLineEdit()
        heard.setPlaceholderText("Phrase VoxKey heard")
        intended.setPlaceholderText("What you intended")
        layout.addWidget(heard)
        layout.addWidget(intended)
        layout.addWidget(scope)

        def select_output(index: int) -> None:
            item = history[index] if 0 <= index < len(history) else None
            preview.setPlainText(item["text"] if item else "")
            scope.clear()
            if item and item.get("app"):
                scope.addItem(f"Only {item['app']}", item["app"])
            scope.addItem("All apps", None)

        recent.currentRowChanged.connect(select_output)
        select_output(0 if history else -1)
        if history:
            recent.setCurrentRow(0)
        corrections = QListWidget()
        corrections.setFixedHeight(100)

        def refresh_rules() -> None:
            corrections.clear()
            for rule in self.memory.list_corrections():
                scope_label = rule.get("app") or "all apps"
                origin = ", learned from edit" if rule.get("source") == "edit" else ""
                corrections.addItem(f"{rule['heard']} → {rule['intended']} ({scope_label}{origin})")

        def save_rule() -> None:
            try:
                self.memory.add_correction(heard.text(), intended.text(), scope.currentData())
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "Correction not saved", str(exc))
                return
            heard.clear()
            intended.clear()
            refresh_rules()

        save = QPushButton("Remember correction")
        save.clicked.connect(save_rule)
        layout.addWidget(save)
        layout.addWidget(QLabel("Saved corrections"))
        refresh_rules()
        layout.addWidget(corrections)

        suggestions = QListWidget()
        suggestions.setFixedHeight(85)

        def refresh_suggestions() -> None:
            suggestions.clear()
            for item in self.memory.list_suggestions():
                suggestions.addItem(f"{item['heard']} → {item['intended']} ({item.get('app') or 'all apps'})")

        layout.addWidget(QLabel("Edits to review"))
        refresh_suggestions()
        layout.addWidget(suggestions)
        refresh = QPushButton("Refresh suggested edits")
        refresh.clicked.connect(refresh_suggestions)
        layout.addWidget(refresh)

        def selected_suggestion():
            items = self.memory.list_suggestions()
            index = suggestions.currentRow()
            return items[index] if 0 <= index < len(items) else None

        def accept_suggestion() -> None:
            item = selected_suggestion()
            if item is None:
                return
            try:
                self.memory.accept_suggestion(item["heard"], item["intended"], item.get("app"))
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "Suggestion not accepted", str(exc))
                return
            refresh_suggestions()
            refresh_rules()

        def discard_suggestion() -> None:
            item = selected_suggestion()
            if item is None:
                return
            try:
                self.memory.delete_suggestion(item["heard"], item["intended"], item.get("app"))
            except OSError as exc:
                QMessageBox.warning(dialog, "Suggestion not deleted", str(exc))
                return
            refresh_suggestions()

        accept = QPushButton("Remember selected edit")
        accept.clicked.connect(accept_suggestion)
        layout.addWidget(accept)
        discard = QPushButton("Dismiss selected edit")
        discard.clicked.connect(discard_suggestion)
        layout.addWidget(discard)

        def delete_rule() -> None:
            index = corrections.currentRow()
            rules = self.memory.list_corrections()
            if 0 <= index < len(rules):
                rule = rules[index]
                try:
                    self.memory.delete_correction(rule["heard"], rule.get("app"))
                except OSError as exc:
                    QMessageBox.warning(dialog, "Correction not deleted", str(exc))
                    return
                refresh_rules()

        remove = QPushButton("Delete selected correction")
        remove.clicked.connect(delete_rule)
        layout.addWidget(remove)

        def clear_history() -> None:
            try:
                self.memory.clear_history()
            except OSError as exc:
                QMessageBox.warning(dialog, "History not cleared", str(exc))
                return
            history.clear()
            recent.clear()
            select_output(-1)

        clear = QPushButton("Clear dictation history")
        clear.clicked.connect(clear_history)
        layout.addWidget(clear)

        snippets_page = QWidget()
        tabs.addTab(snippets_page, "Snippets")
        snippet_layout = QVBoxLayout(snippets_page)
        snippet_layout.addWidget(QLabel("Say a cue by itself to paste its saved text."))
        cue = QLineEdit()
        cue.setPlaceholderText("Spoken cue, for example my meeting link")
        expansion = QPlainTextEdit()
        expansion.setPlaceholderText("Text to paste")
        snippet_layout.addWidget(cue)
        snippet_layout.addWidget(expansion)
        snippets = QListWidget()

        def refresh_snippets() -> None:
            snippets.clear()
            for item in self.memory.list_snippets():
                snippets.addItem(item["cue"])

        def save_snippet() -> None:
            try:
                self.memory.add_snippet(cue.text(), expansion.toPlainText())
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "Snippet not saved", str(exc))
                return
            cue.clear()
            expansion.clear()
            refresh_snippets()

        save_snippet_button = QPushButton("Save snippet")
        save_snippet_button.clicked.connect(save_snippet)
        snippet_layout.addWidget(save_snippet_button)
        refresh_snippets()
        snippet_layout.addWidget(snippets)

        def select_snippet(index: int) -> None:
            items = self.memory.list_snippets()
            if 0 <= index < len(items):
                cue.setText(items[index]["cue"])
                expansion.setPlainText(items[index]["text"])

        snippets.currentRowChanged.connect(select_snippet)

        def delete_snippet() -> None:
            index = snippets.currentRow()
            items = self.memory.list_snippets()
            if 0 <= index < len(items):
                try:
                    self.memory.delete_snippet(items[index]["cue"])
                except OSError as exc:
                    QMessageBox.warning(dialog, "Snippet not deleted", str(exc))
                    return
                refresh_snippets()

        remove_snippet = QPushButton("Delete selected snippet")
        remove_snippet.clicked.connect(delete_snippet)
        snippet_layout.addWidget(remove_snippet)

        styles_page = QWidget()
        tabs.addTab(styles_page, "App styles")
        style_layout = QVBoxLayout(styles_page)
        style_layout.addWidget(QLabel("Choose how VoxKey formats dictation in one app."))
        style_app = QLineEdit()
        style_app.setPlaceholderText("App name, for example notepad.exe")
        if history and history[0].get("app"):
            style_app.setText(history[0]["app"])
        style_choice = QComboBox()
        for style in self.memory.STYLES:
            style_choice.addItem(style.title(), style)
        style_layout.addWidget(style_app)
        style_layout.addWidget(style_choice)
        styles = QListWidget()

        def refresh_styles() -> None:
            styles.clear()
            for app, style in sorted(self.memory.styles().items()):
                styles.addItem(f"{app}: {style}")

        def save_style() -> None:
            try:
                self.memory.set_style(style_app.text(), style_choice.currentData())
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "Style not saved", str(exc))
                return
            refresh_styles()

        save_style_button = QPushButton("Save app style")
        save_style_button.clicked.connect(save_style)
        style_layout.addWidget(save_style_button)
        refresh_styles()
        style_layout.addWidget(styles)

        def select_style(index: int) -> None:
            items = sorted(self.memory.styles().items())
            if 0 <= index < len(items):
                app, style = items[index]
                style_app.setText(app)
                style_choice.setCurrentIndex(style_choice.findData(style))

        styles.currentRowChanged.connect(select_style)

        def delete_style() -> None:
            index = styles.currentRow()
            apps = sorted(self.memory.styles())
            if 0 <= index < len(apps):
                try:
                    self.memory.set_style(apps[index], "standard")
                except OSError as exc:
                    QMessageBox.warning(dialog, "Style not reset", str(exc))
                    return
                refresh_styles()

        remove_style = QPushButton("Reset selected app")
        remove_style.clicked.connect(delete_style)
        style_layout.addWidget(remove_style)
        dialog.resize(480, 730)
        dialog.show()
        self.memory_dialog = dialog

    def handle_event(self, event: UiEvent) -> None:
        if should_render_hud(event):
            self.hud.show_event(event)
        cue = SoundCue.for_event(event)
        self.sounds.play(cue)
        if event.kind == "state_changed" and event.state:
            detail = event.detail or {
                AppState.VALIDATING: "Preparing local models. First launch may take a few minutes.",
                AppState.READY: "Ready for local dictation.",
            }.get(event.state, "Working locally.")
            self.health.setText(f"Status: {event.state.value} — {detail}")

    def close(self) -> None:
        self.hud.hide()
        if self.memory_dialog:
            self.memory_dialog.hide()
        self.settings.hide()
        self.tray.hide()


def create_qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    return app
