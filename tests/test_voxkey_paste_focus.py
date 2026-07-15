import unittest
from unittest.mock import Mock, patch

from voxkey_app import paste_polished_text, restore_foreground_window_handle


class VoxKeyPasteFocusTests(unittest.TestCase):
    def test_paste_restores_recording_target_before_sending_ctrl_v(self):
        controller = Mock()
        with (
            patch("voxkey_app.pyperclip.paste", return_value="old"),
            patch("voxkey_app.pyperclip.copy"),
            patch("voxkey_app.keyboard.Controller", return_value=controller),
            patch("voxkey_app.restore_foreground_window_handle") as restore,
            patch("voxkey_app.time.sleep"),
        ):
            pasted = paste_polished_text("Hello, Notepad.", target_hwnd=1234)

        self.assertTrue(pasted)
        restore.assert_called_once_with(1234)
        controller.press.assert_any_call("v")
        self.assertNotIn(
            __import__("pynput").keyboard.Key.ctrl_r,
            [call.args[0] for call in controller.release.call_args_list],
        )

    def test_releasing_right_ctrl_queues_audio_with_the_original_paste_target(self):
        controller = Mock()
        runtime = Mock()
        runtime.recordings_dir.return_value = Mock()
        from voxkey_app import HoldToDictateService

        service = HoldToDictateService(controller, runtime)
        service.recording = True
        service.capture_started = True
        service.paste_target_hwnd = 1234
        service.recorder.stop_and_save = Mock(return_value="recording.wav")

        service._release(__import__("pynput").keyboard.Key.ctrl_r)

        self.assertEqual(service.jobs.get_nowait(), ("recording.wav", 1234))

    def test_restore_foreground_window_uses_windows_focus_api(self):
        user32 = Mock()
        with patch("voxkey_app._user32", user32):
            restore_foreground_window_handle(1234)

        user32.SetForegroundWindow.assert_called_once_with(1234)


if __name__ == "__main__":
    unittest.main()
