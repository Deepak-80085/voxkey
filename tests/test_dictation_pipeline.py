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
        self.assertEqual(controller.state, AppState.READY)
        self.assertIsNone(controller.reason)

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

    def test_local_correction_runs_before_writer_and_history_only_after_paste(self):
        speech, writer, memory = Mock(), Mock(), Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "open vox key"
        memory.correct.return_value = "open VoxKey"
        memory.snippet_for.return_value = None
        memory.style_for.return_value = "standard"
        writer.polish.return_value = "Open VoxKey."
        controller = VoxKeyController(speech, writer, paste=Mock(return_value=True), memory=memory)
        controller.start()

        self.assertTrue(controller.process_audio(Path("sample.wav"), app="editor.exe"))
        memory.correct.assert_called_once_with("open vox key", "editor.exe")
        writer.polish.assert_called_once_with("open VoxKey")
        memory.remember_output.assert_called_once_with("Open VoxKey.", "editor.exe")

    def test_saved_snippet_bypasses_writer(self):
        speech, writer, memory = Mock(), Mock(), Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "my meeting link"
        memory.correct.return_value = "my meeting link"
        memory.snippet_for.return_value = "https://example.com/meet"
        memory.style_for.return_value = "standard"
        paste = Mock(return_value=True)
        controller = VoxKeyController(speech, writer, paste=paste, memory=memory)
        controller.start()

        self.assertTrue(controller.process_audio(Path("sample.wav")))
        writer.polish.assert_not_called()
        paste.assert_called_once_with("https://example.com/meet", target_hwnd=None)

    def test_app_style_reaches_writer_and_failed_paste_is_not_saved(self):
        speech, writer, memory = Mock(), Mock(), Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "send the update"
        memory.correct.return_value = "send the update"
        memory.snippet_for.return_value = None
        memory.style_for.return_value = "minimal"
        writer.polish.return_value = "Send the update"
        controller = VoxKeyController(speech, writer, paste=Mock(return_value=False), memory=memory)
        controller.start()

        self.assertFalse(controller.process_audio(Path("sample.wav"), app="notepad.exe"))
        writer.polish.assert_called_once_with("send the update", style="minimal")
        memory.remember_output.assert_not_called()

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

    def test_repair_prepares_gpu_runtime_before_speech(self):
        speech = Mock()
        order = []
        speech.repair.side_effect = lambda: order.append('speech') or Mock(ready=True, reason=None)
        controller = VoxKeyController(
            speech, Mock(), paste=Mock(), prepare_runtime=lambda _progress: order.append('runtime')
        )

        controller.repair_models()

        self.assertEqual(order, ['runtime', 'speech'])
        self.assertEqual(controller.state, AppState.READY)

    def test_gpu_runtime_failure_still_lets_speech_load(self):
        speech = Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        controller = VoxKeyController(
            speech, Mock(), paste=Mock(), prepare_runtime=Mock(side_effect=RuntimeError('offline'))
        )

        controller.start()

        speech.health_check.assert_called_once()
        self.assertEqual(controller.state, AppState.READY)


if __name__ == "__main__":
    unittest.main()
