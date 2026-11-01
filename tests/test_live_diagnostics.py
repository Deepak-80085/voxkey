import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from voxkey_app import HoldToDictateService
from voxkey_runtime import AppState


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

    def _set_state(self, state, reason=None):
        self.state = state

    def process_audio(self, *_args, **_kwargs):
        return True


class LiveDiagnosticsTests(unittest.TestCase):
    def test_hotkey_lifecycle_is_logged(self):
        runtime = Mock()
        runtime.recordings_dir.return_value = Path(".")
        logger = Mock()
        service = HoldToDictateService(Controller(), runtime, logger=logger)
        service.recorder = Recorder()

        with patch("voxkey_app.get_foreground_window_handle", return_value=123):
            service._press(__import__("pynput").keyboard.Key.ctrl_r)
        with patch("voxkey_app.time.monotonic", return_value=999999):
            service.alt_started_at = 0
            service.tick()
        service._release(__import__("pynput").keyboard.Key.ctrl_r)

        messages = [str(call.args[0]) for call in logger.info.call_args_list]
        self.assertTrue(any("Dictation hotkey pressed" in message for message in messages))
        self.assertTrue(any("Recording started" in message for message in messages))
        self.assertTrue(any("Recording saved" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
