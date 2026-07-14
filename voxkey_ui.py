"""Native Qt presentation for VoxKey without coupling the dictation pipeline to Qt."""

from __future__ import annotations

import math
import sys
import winsound
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
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
    def __init__(self, enabled: bool = True, logger=None) -> None:
        self.enabled = enabled
        self.logger = logger

    def play(self, cue: str | None) -> None:
        if not cue or not self.enabled:
            return
        try:
            sound = {
                "start": winsound.MB_OK,
                "complete": winsound.MB_ICONASTERISK,
                "error": winsound.MB_ICONHAND,
            }[cue]
            winsound.MessageBeep(sound)
        except Exception:
            if self.logger:
                self.logger.exception("Sound cue failed: %s", cue)


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
        self._phase = 0.0
        self.setFixedSize(132, 132)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._pulse = QTimer(self)
        self._pulse.setInterval(40)
        self._pulse.timeout.connect(self._advance_animation)
        self._opacity = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity.setDuration(180)
        self._opacity.setEasingCurve(QEasingCurve.OutCubic)

    def _advance_animation(self) -> None:
        self._phase += 0.16
        self.update()

    def _position_bottom_center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - self.height() - 52))

    def show_event(self, event: UiEvent) -> None:
        view = hud_view_for(event)
        if not view.visible:
            self.hide()
            self._pulse.stop()
            return
        self._view = view
        self._position_bottom_center()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._pulse.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        colors = self._COLORS["listening"]
        radius = 45 + math.sin(self._phase) * 4
        gradient = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
        gradient.setColorAt(0, colors[0])
        gradient.setColorAt(0.48, colors[1])
        gradient.setColorAt(1, colors[2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))
        painter.setPen(QPen(QColor(230, 239, 255, 120), 1.2))
        for index in range(7):
            offset = (index - 3) * 8
            height = 4 + abs(math.sin(self._phase + index * 0.65)) * 10
            painter.drawLine(int(cx + offset), int(cy - height / 2), int(cx + offset), int(cy + height / 2))


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
