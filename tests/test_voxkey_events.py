import unittest

from voxkey_runtime import AppState


class VoxKeyEventTests(unittest.TestCase):
    def test_event_bus_preserves_event_order(self):
        from voxkey_events import EventBus, UiEvent

        bus = EventBus()
        expected = [
            UiEvent("capture_started", AppState.LISTENING),
            UiEvent("paste_succeeded", AppState.READY, elapsed_ms=42),
        ]

        for event in expected:
            bus.publish(event)

        self.assertEqual(bus.drain(), expected)


if __name__ == "__main__":
    unittest.main()
