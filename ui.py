"""Small Tkinter control center for VoxKey's local model health."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from voxkey_runtime import AppState


@dataclass(frozen=True)
class StatusView:
    title: str
    detail: str
    can_repair: bool


def status_view(state: AppState, reason: str | None) -> StatusView:
    if state is AppState.NEEDS_REPAIR:
        return StatusView("Needs repair", reason or "VoxKey needs repair", True)
    if state is AppState.READY:
        return StatusView("Ready", "English dictation is ready and processed locally.", False)
    details = {
        AppState.STARTING: "Starting VoxKey locally.",
        AppState.SETUP: "Complete local setup to enable dictation.",
        AppState.VALIDATING: "Checking local speech and writing models.",
        AppState.LISTENING: "Listening.",
        AppState.TRANSCRIBING: "Transcribing locally.",
        AppState.POLISHING: "Polishing locally.",
    }
    return StatusView(state.value, reason or details[state], False)


class VoxKeyControlCenter:
    def __init__(self, controller, runtime):
        self.controller = controller
        self.runtime = runtime
        self.root = tk.Tk()
        self.root.title("VoxKey")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)

        frame = ttk.Frame(self.root, padding=20)
        frame.grid()
        ttk.Label(frame, text="VoxKey", font=("Segoe UI", 18, "bold")).grid(sticky="w")
        ttk.Label(
            frame,
            text="Private voice typing. On your device.",
        ).grid(sticky="w", pady=(0, 16))
        self.state_label = ttk.Label(frame, font=("Segoe UI", 12, "bold"))
        self.state_label.grid(sticky="w")
        self.detail_label = ttk.Label(frame, wraplength=360, justify="left")
        self.detail_label.grid(sticky="w", pady=(4, 12))
        self.repair_button = ttk.Button(frame, text="Repair models", command=self.repair_models)
        self.repair_button.grid(sticky="w")
        ttk.Label(
            frame,
            text=f"Local logs: {runtime.data_dir() / 'voxkey.log'}",
            wraplength=360,
        ).grid(sticky="w", pady=(16, 0))
        self.render_state(controller.state, controller.reason)

    def render_state(self, state: AppState, reason: str | None = None) -> None:
        view = status_view(state, reason)
        self.state_label.configure(text=view.title)
        self.detail_label.configure(text=view.detail)
        self.repair_button.configure(state="normal" if view.can_repair else "disabled")

    def repair_models(self) -> None:
        self.controller.repair_models()
        self.render_state(self.controller.state, self.controller.reason)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def process_events(self) -> None:
        self.render_state(self.controller.state, self.controller.reason)
        self.root.update_idletasks()
        self.root.update()
