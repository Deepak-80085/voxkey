"""Thread-safe, UI-framework-independent lifecycle events for VoxKey."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, SimpleQueue

from voxkey_runtime import AppState


@dataclass(frozen=True)
class UiEvent:
    kind: str
    state: AppState | None = None
    detail: str | None = None
    elapsed_ms: int | None = None


class EventBus:
    """Accept events from worker threads and drain them on the UI thread."""

    def __init__(self) -> None:
        self._events = SimpleQueue()

    def publish(self, event: UiEvent) -> None:
        self._events.put(event)

    def drain(self) -> list[UiEvent]:
        events: list[UiEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events
