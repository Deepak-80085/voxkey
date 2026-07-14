import unittest
from pathlib import Path
from unittest.mock import Mock

from voxkey_controller import VoxKeyController
from voxkey_events import EventBus


class VoxKeyControllerEventTests(unittest.TestCase):
    def test_success_emits_stages_and_total_paste_timing(self):
        speech, writer = Mock(), Mock()
        paste = Mock(return_value=True)
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "hello"
        writer.polish.return_value = "Hello."
        ticks = iter((1.0, 1.2, 1.4, 1.5))
        events = EventBus()
        controller = VoxKeyController(
            speech, writer, paste, events=events, clock=lambda: next(ticks)
        )
        controller.start()
        events.drain()

        self.assertTrue(controller.process_audio(Path("sample.wav")))
        emitted = events.drain()

        self.assertEqual(
            [event.kind for event in emitted],
            ["transcribing", "state_changed", "polishing", "state_changed", "paste_succeeded", "state_changed"],
        )
        self.assertEqual(emitted[-2].elapsed_ms, 500)

    def test_success_logs_individual_transcription_polishing_and_paste_timings(self):
        speech, writer, paste, logger = Mock(), Mock(), Mock(return_value=True), Mock()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "hello"
        writer.polish.return_value = "Hello."
        ticks = iter((1.0, 1.2, 1.7, 1.8))
        controller = VoxKeyController(speech, writer, paste, logger=logger, clock=lambda: next(ticks))
        controller.start()

        controller.process_audio(Path("sample.wav"))

        logger.info.assert_any_call("Transcription completed; chars=%d; elapsed_ms=%d", 5, 200)
        logger.info.assert_any_call("Polishing completed; chars=%d; elapsed_ms=%d", 6, 500)
        logger.info.assert_any_call("Paste attempted; success=%s; target=%s; total_ms=%d", True, None, 800)

    def test_writer_failure_emits_failure_and_never_pastes_raw_text(self):
        speech, writer, paste, events = Mock(), Mock(), Mock(), EventBus()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        writer.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "raw words"
        writer.polish.side_effect = RuntimeError("writer offline")
        controller = VoxKeyController(speech, writer, paste, events=events)
        controller.start()
        events.drain()

        self.assertFalse(controller.process_audio(Path("sample.wav")))

        self.assertIn("pipeline_failed", [event.kind for event in events.drain()])
        paste.assert_not_called()


if __name__ == "__main__":
    unittest.main()
