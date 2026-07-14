"""Native Qt presentation for VoxKey without coupling the dictation pipeline to Qt."""

from __future__ import annotations

import math
import sys
import winsound
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from voxkey_events import UiEvent
from voxkey_runtime import AppState


@dataclass(frozen=True)
class HudView:
    visible: bool
    title: str
    detail: str
    mood: str


def hud_view_for(event: UiEvent) -> HudView:
    """Translate framework-neutral lifecycle events into concise HUD copy."""
    views = {
        "capture_started": HudView(True, "Listening", "Release Right Ctrl when you’re done", "listening"),
        "capture_stopped": HudView(True, "Transcribing…", "Processing locally", "processing"),
        "transcribing": HudView(True, "Transcribing…", "Processing locally", "processing"),
        "polishing": HudView(True, "Polishing…", "Making your words clear", "processing"),
        "paste_succeeded": HudView(True, "Done", "", "success"),
        "pipeline_failed": HudView(True, "Needs attention", event.detail or "Dictation could not finish", "error"),
        "capture_failed": HudView(True, "Needs attention", event.detail or "Microphone could not start", "error"),
    }
    if event.kind == "state_changed" and event.state is AppState.READY:
        return HudView(False, "", "", "idle")
    return views.get(event.kind, HudView(False, "", "", "idle"))


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
        self.setFixedSize(360, 220)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._title = QLabel(self)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        self._title.setStyleSheet("color: white; background: transparent;")
        self._detail = QLabel(self)
        self._detail.setAlignment(Qt.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setFont(QFont("Segoe UI", 9))
        self._detail.setStyleSheet("color: #c8c8d5; background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 132, 28, 15)
        layout.setSpacing(3)
        layout.addWidget(self._title)
        layout.addWidget(self._detail)
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
        self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - self.height() - 38))

    def show_event(self, event: UiEvent) -> None:
        view = hud_view_for(event)
        if not view.visible:
            self.hide()
            self._pulse.stop()
            return
        self._view = view
        self._title.setText(view.title)
        self._detail.setText(view.detail)
        self._position_bottom_center()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._pulse.start()
        delay = 500 if view.mood == "success" else 3500 if view.mood == "error" else 0
        if delay:
            QTimer.singleShot(delay, self.hide)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, 76
        colors = self._COLORS.get(self._view.mood, self._COLORS["processing"])
        radius = 51 + math.sin(self._phase) * (5 if self._view.mood == "listening" else 2)
        gradient = QLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
        gradient.setColorAt(0, colors[0])
        gradient.setColorAt(0.48, colors[1])
        gradient.setColorAt(1, colors[2])
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))
        painter.setPen(QPen(QColor(210, 203, 255, 115), 1.2))
        for index in range(9):
            offset = (index - 4) * 9
            height = 4 + abs(math.sin(self._phase + index * 0.65)) * 12
            painter.drawLine(int(cx + offset), 139 - int(height / 2), int(cx + offset), 139 + int(height / 2))


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
        self.settings = self._make_settings()
        self.tray = QSystemTrayIcon(QApplication.style().standardIcon(QApplication.style().SP_ComputerIcon))
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
