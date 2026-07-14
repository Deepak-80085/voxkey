"""Native Qt presentation for VoxKey without coupling the dictation pipeline to Qt."""

from __future__ import annotations

import ctypes
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QLabel, QMenu, QPushButton, QStyle, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from voxkey_events import UiEvent
from voxkey_runtime import AppState


@dataclass(frozen=True)
class HudView:
    visible: bool
    title: str
    detail: str
    mood: str


def should_render_hud(event: UiEvent) -> bool:
    """Only a held, active dictation capture controls the transient orb."""
    return event.kind in {"capture_started", "capture_stopped"}


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
        self._breath = QPropertyAnimation(self, b"windowOpacity", self)
        self._breath.setDuration(1200)
        self._breath.setStartValue(0.76)
        self._breath.setKeyValueAt(0.5, 1.0)
        self._breath.setEndValue(0.76)
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
        self.setWindowOpacity(0.76)
        self.show()
        self.raise_()
        self._breath.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        colors = self._COLORS["listening"]
        radius = 18
        gradient = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
        gradient.setColorAt(0, colors[0])
        gradient.setColorAt(0.48, colors[1])
        gradient.setColorAt(1, colors[2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))


class SettingsActions:
    """Small testable adapter between settings controls and local runtime."""

    def __init__(self, controller, runtime, sound_player=None) -> None:
        self.controller = controller
        self.runtime = runtime
        self.sound_player = sound_player

    def set_sounds_enabled(self, enabled: bool) -> None:
        settings = dict(self.runtime.load_settings())
        settings["sounds_enabled"] = bool(enabled)
        self.runtime.save_settings(settings)
        if self.sound_player:
            self.sound_player.enabled = bool(enabled)

    def repair(self) -> None:
        self.controller.repair_models()

    def open_diagnostics(self) -> None:
        import os
        os.startfile(self.runtime.data_dir())


class VoxKeyShell:
    """Tray-first Qt shell; the HUD never owns focus."""

    def __init__(self, controller, runtime, shutdown) -> None:
        self.controller, self.runtime, self.shutdown = controller, runtime, shutdown
        self.hud = VoxKeyHud()
        self.sounds = SoundPlayer(runtime.load_settings()["sounds_enabled"], runtime.logger())
        self.actions = SettingsActions(controller, runtime, self.sounds)
        self.tray = QSystemTrayIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        menu = QMenu()
        menu.addAction("Open settings", self.show_settings)
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
        layout = QVBoxLayout(dialog)
        title = QLabel("VoxKey")
        title.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        layout.addWidget(title)
        layout.addWidget(QLabel("Private local dictation. Hold Right Ctrl to speak."))
        self.health = QLabel()
        layout.addWidget(self.health)
        checkbox = QCheckBox("Play voice feedback sounds")
        checkbox.setChecked(self.sounds.enabled)
        checkbox.toggled.connect(self.actions.set_sounds_enabled)
        checkbox.toggled.connect(self.sound_action.setChecked)
        layout.addWidget(checkbox)
        repair = QPushButton("Repair models")
        repair.clicked.connect(self.actions.repair)
        layout.addWidget(repair)
        diagnostics = QPushButton("Open diagnostics folder")
        diagnostics.clicked.connect(self.actions.open_diagnostics)
        layout.addWidget(diagnostics)
        dialog.resize(400, 220)
        return dialog

    def show_settings(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def handle_event(self, event: UiEvent) -> None:
        if should_render_hud(event):
            self.hud.show_event(event)
        cue = SoundCue.for_event(event)
        self.sounds.play(cue)
        if event.kind == "state_changed" and event.state:
            detail = event.detail or "Ready for local dictation."
            self.health.setText(f"Status: {event.state.value} — {detail}")

    def close(self) -> None:
        self.hud.hide()
        self.settings.hide()
        self.tray.hide()


def create_qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    return app
