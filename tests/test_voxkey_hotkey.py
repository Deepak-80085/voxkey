import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pynput import keyboard
from voxkey_app import HoldToDictateService
from voxkey_runtime import AppState, VoxKeyRuntime


class Recorder:
    def start(self):
        return True

    def stop_and_save(self):
        return Path("recording.wav")

    def abort(self):
        pass


class Controller:
    state = AppState.READY

    def can_dictate(self):
        return True

    def _set_state(self, state, _reason=None):
        self.state = state


class VoxKeyHotkeyTests(unittest.TestCase):
    def make_service(self):
        runtime = Mock(spec=VoxKeyRuntime)
        runtime.recordings_dir.return_value = Path(".")
        runtime.logger.return_value = Mock()
        service = HoldToDictateService(Controller(), runtime)
        service.recorder = Recorder()
        return service

    def test_right_ctrl_hold_starts_recording(self):
        service = self.make_service()
        with patch("voxkey_app.time.monotonic", side_effect=[100, 101]):
            service._press(keyboard.Key.ctrl_r)
            service.tick()

        self.assertTrue(service.recording)

    def test_alt_does_not_activate_dictation(self):
        service = self.make_service()
        service._press(keyboard.Key.alt)
        with patch("voxkey_app.time.monotonic", return_value=999):
            service.tick()

        self.assertFalse(service.recording)


if __name__ == "__main__":
    unittest.main()
