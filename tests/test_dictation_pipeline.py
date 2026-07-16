import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from voxkey_controller import VoxKeyController
from voxkey_runtime import AppState
from writing_model import WritingModelUnavailable


class DictationPipelineTests(unittest.TestCase):
    def test_dictation_is_disabled_until_speech_and_writer_are_healthy(self):
        speech = Mock()
        speech.health_check.return_value = Mock(ready=False, reason="Speech model needs repair")
        writer = Mock()
        writer.health_check.return_value = Mock(ready=True, reason=None)
        controller = VoxKeyController(speech, writer, paste=Mock())

        controller.start()

        self.assertEqual(controller.state, AppState.NEEDS_REPAIR)
        self.assertEqual(controller.reason, "Speech model needs repair")
        self.assertFalse(controller.can_dictate())

    def test_writer_failure_does_not_paste_raw_transcript(self):
        speech = Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "hello zudio"
        writer = Mock()
        writer.health_check.return_value = Mock(ready=True, reason=None)
        writer.polish.side_effect = WritingModelUnavailable("writer offline")
        paste = Mock()
        controller = VoxKeyController(speech, writer, paste=paste)
        controller.start()

        result = controller.process_audio(Path("sample.wav"))

        self.assertFalse(result)
        paste.assert_not_called()
        self.assertEqual(controller.state, AppState.NEEDS_REPAIR)
        self.assertIn("writer", controller.reason)

    def test_successful_processing_transcribes_polishes_and_pastes_once(self):
        speech = Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "hello zudio"
        writer = Mock()
        writer.health_check.return_value = Mock(ready=True, reason=None)
        writer.polish.return_value = "Hello, Zudio."
        paste = Mock(return_value=True)
        controller = VoxKeyController(speech, writer, paste=paste)
        controller.start()

        result = controller.process_audio(Path("sample.wav"), target_hwnd=123)

        self.assertTrue(result)
        self.assertEqual(paste.call_args.args[0], "Hello, Zudio.")
        self.assertEqual(paste.call_args.kwargs["target_hwnd"], 123)
        self.assertEqual(controller.state, AppState.READY)

    def test_validation_ignores_repair_while_startup_check_is_running(self):
        entered = threading.Event()
        release = threading.Event()
        speech, writer = Mock(), Mock()

        def health_check():
            entered.set()
            release.wait(timeout=2)
            return Mock(ready=True, reason=None)

        speech.health_check.side_effect = health_check
        writer.health_check.return_value = Mock(ready=True, reason=None)
        controller = VoxKeyController(speech, writer, paste=Mock())
        startup = threading.Thread(target=controller.start)
        startup.start()
        self.assertTrue(entered.wait(timeout=1))

        controller.repair_models()
        release.set()
        startup.join(timeout=2)

        speech.repair.assert_not_called()
        self.assertEqual(speech.health_check.call_count, 1)

    def test_repair_prepares_writer_before_speech(self):
        speech, writer = Mock(), Mock()
        speech.repair.return_value = Mock(ready=True, reason=None)
        writer.repair.return_value = Mock(ready=True, reason=None)
        controller = VoxKeyController(speech, writer, paste=Mock())
        order = []
        writer.repair.side_effect = lambda _progress: order.append('writer') or Mock(ready=True, reason=None)
        speech.repair.side_effect = lambda: order.append('speech') or Mock(ready=True, reason=None)

        controller.repair_models()

        self.assertEqual(order, ['writer', 'speech'])
        self.assertEqual(controller.state, AppState.READY)

    def test_start_automatically_prepares_writer_runtime(self):
        speech, writer = Mock(), Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.repair.return_value = Mock(ready=True, reason=None)
        controller = VoxKeyController(speech, writer, paste=Mock())

        controller.start()

        writer.repair.assert_called_once()
        self.assertEqual(controller.state, AppState.READY)


if __name__ == "__main__":
    unittest.main()
