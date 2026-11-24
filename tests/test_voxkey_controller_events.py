import unittest
from pathlib import Path
from unittest.mock import Mock

from voxkey_controller import VoxKeyController
from voxkey_events import EventBus
from voxkey_runtime import AppState


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


class CommandControllerTests(unittest.TestCase):
    def _make(self, parsed, result=(True, "Opened Slack"), ticks=(1.0, 1.2, 1.6)):
        speech, writer, paste, logger, events = Mock(), Mock(), Mock(return_value=True), Mock(), EventBus()
        speech.health_check.return_value = Mock(ready=True, reason=None)
        speech.transcribe.return_value = "open slack"
        writer.polish.return_value = "Open Slack."
        commands = Mock()
        commands.parse.return_value = parsed
        commands.run.return_value = result
        controller = VoxKeyController(
            speech, writer, paste, logger=logger, events=events, commands=commands,
            clock=lambda it=iter(ticks): next(it),
        )
        controller.start()
        events.drain()
        return controller, paste, writer, commands, logger, events

    def test_command_runs_instead_of_pasting_and_logs_command_ms(self):
        controller, paste, writer, commands, logger, events = self._make("CMD")
        self.assertTrue(controller.process_audio(Path("s.wav")))
        paste.assert_not_called()
        writer.polish.assert_not_called()
        commands.run.assert_called_once_with("CMD")
        emitted = events.drain()
        done = [e for e in emitted if e.kind == "command_succeeded"]
        self.assertEqual(done[0].detail, "Opened Slack")
        self.assertEqual(emitted[-1].state, AppState.READY)
        logger.info.assert_any_call("Command completed; success=%s; command_ms=%d", True, 400)

    def test_failed_command_emits_failure_and_pastes_nothing(self):
        controller, paste, _, _, _, events = self._make("CMD", result=(False, "Couldn't open Slack"))
        self.assertFalse(controller.process_audio(Path("s.wav")))
        paste.assert_not_called()
        failed = [e for e in events.drain() if e.kind == "command_failed"]
        self.assertEqual(failed[0].detail, "Couldn't open Slack")
        self.assertEqual(controller.state, AppState.READY)

    def test_not_a_command_pastes_as_before(self):
        controller, paste, _, commands, _, events = self._make(None, ticks=(1.0, 1.2, 1.4, 1.5))
        self.assertTrue(controller.process_audio(Path("s.wav")))
        commands.parse.assert_called_once_with("open slack")
        paste.assert_called_once()
        self.assertNotIn("command_failed", [e.kind for e in events.drain()])

    def test_parser_crash_falls_back_to_pasting(self):
        controller, paste, _, commands, _, _ = self._make(None, ticks=(1.0, 1.2, 1.4, 1.5))
        commands.parse.side_effect = RuntimeError("boom")
        self.assertTrue(controller.process_audio(Path("s.wav")))
        paste.assert_called_once()


if __name__ == "__main__":
    unittest.main()
