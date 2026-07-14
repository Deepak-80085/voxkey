import unittest

from voxkey_events import UiEvent
from voxkey_runtime import AppState


class VoxKeyUiTests(unittest.TestCase):
    def test_capture_started_shows_an_orb_without_copy_and_plays_start_sound(self):
        from voxkey_ui import SoundCue, hud_view_for

        event = UiEvent("capture_started", AppState.LISTENING)
        view = hud_view_for(event)

        self.assertTrue(view.visible)
        self.assertEqual(view.title, "")
        self.assertEqual(view.detail, "")
        self.assertEqual(SoundCue.for_event(event), "start")

    def test_sound_player_uses_bundled_simplespeech_start_and_end_assets(self):
        from voxkey_ui import SoundPlayer

        sounds = SoundPlayer()

        self.assertEqual(sounds._SOUND_FILES, {"start": "starrt.mp3", "complete": "end.mp3"})
        self.assertTrue((sounds.asset_dir / "starrt.mp3").is_file())
        self.assertTrue((sounds.asset_dir / "end.mp3").is_file())

    def test_release_and_all_post_release_events_hide_the_hud_but_keep_sounds(self):
        from voxkey_ui import SoundCue, hud_view_for

        for kind in ("capture_stopped", "transcribing", "polishing", "paste_succeeded", "pipeline_failed"):
            with self.subTest(kind=kind):
                view = hud_view_for(UiEvent(kind, AppState.READY, "Writer unavailable"))
                self.assertFalse(view.visible)

        self.assertEqual(SoundCue.for_event(UiEvent("paste_succeeded")), "complete")
        self.assertEqual(SoundCue.for_event(UiEvent("pipeline_failed")), "error")

    def test_only_capture_lifecycle_events_are_sent_to_the_hud(self):
        from voxkey_ui import should_render_hud

        self.assertTrue(should_render_hud(UiEvent("capture_started", AppState.LISTENING)))
        self.assertTrue(should_render_hud(UiEvent("capture_stopped", AppState.TRANSCRIBING)))
        self.assertFalse(should_render_hud(UiEvent("paste_succeeded", AppState.READY)))
        self.assertFalse(should_render_hud(UiEvent("state_changed", AppState.READY)))

    def test_hud_is_a_compact_orb_without_text_widgets(self):
        from voxkey_ui import VoxKeyHud, create_qt_application

        app = create_qt_application()
        hud = VoxKeyHud()
        self.assertLessEqual(hud.width(), 52)
        self.assertEqual(hud.width(), hud.height())
        self.assertFalse(hasattr(hud, "_title"))
        self.assertFalse(hasattr(hud, "_detail"))
        app.quit()

    def test_shell_constructs_its_settings_before_connecting_sound_controls(self):
        from unittest.mock import Mock
        from voxkey_ui import VoxKeyShell, create_qt_application

        app = create_qt_application()
        runtime = Mock()
        runtime.load_settings.return_value = {"sounds_enabled": True}
        runtime.logger.return_value = Mock()
        shell = VoxKeyShell(Mock(), runtime, lambda: None)
        self.assertIsNotNone(shell.tray)
        shell.close()
        app.quit()


if __name__ == "__main__":
    unittest.main()
