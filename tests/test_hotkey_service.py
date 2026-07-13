import unittest
from unittest.mock import Mock, patch

from app import HotkeyDictationService, keyboard


class FakeRecorder:
    def __init__(self):
        self.started = False
        self.aborted = False

    def start(self):
        self.started = True
        return True

    def abort(self):
        self.aborted = True


class HotkeyServiceTests(unittest.TestCase):
    def make_service(self):
        service = HotkeyDictationService(Mock(), Mock(), indicator=Mock())
        service._recorder = FakeRecorder()
        return service

    def test_short_alt_hold_does_not_start_recording(self):
        service = self.make_service()
        with patch("app.time.monotonic", side_effect=[100.0, 100.1]):
            service._on_press(keyboard.Key.alt)
            service.tick()

        self.assertFalse(service._recorder.started)
        self.assertFalse(service._recording)

    def test_alt_used_with_non_modifier_is_ignored(self):
        service = self.make_service()
        with patch("app.time.monotonic", side_effect=[100.0, 101.0]):
            service._on_press(keyboard.Key.alt)
            service._on_press("f")
            service.tick()

        self.assertFalse(service._recorder.started)
        self.assertFalse(service._recording)

    def test_stop_before_start_is_safe(self):
        service = self.make_service()

        service.stop()

        self.assertTrue(service._recorder.aborted)


if __name__ == "__main__":
    unittest.main()
