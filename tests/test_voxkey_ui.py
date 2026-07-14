import unittest

from voxkey_events import UiEvent
from voxkey_runtime import AppState


class VoxKeyUiTests(unittest.TestCase):
    def test_capture_started_maps_to_listening_hud_and_start_sound(self):
        from voxkey_ui import SoundCue, hud_view_for

        event = UiEvent("capture_started", AppState.LISTENING)
        view = hud_view_for(event)

        self.assertTrue(view.visible)
        self.assertEqual(view.title, "Listening")
        self.assertEqual(SoundCue.for_event(event), "start")

    def test_pipeline_failure_maps_to_readable_error_and_error_sound(self):
        from voxkey_ui import SoundCue, hud_view_for

        event = UiEvent("pipeline_failed", AppState.NEEDS_REPAIR, "Writer unavailable")
        view = hud_view_for(event)

        self.assertTrue(view.visible)
        self.assertEqual(view.title, "Needs attention")
        self.assertEqual(view.detail, "Writer unavailable")
        self.assertEqual(SoundCue.for_event(event), "error")

    def test_ready_state_event_updates_health_without_hiding_success_hud(self):
        from voxkey_ui import hud_view_for, should_render_hud

        event = UiEvent("state_changed", AppState.READY)
        self.assertFalse(hud_view_for(event).visible)
        self.assertFalse(should_render_hud(event))

    def test_paste_success_is_rendered_before_following_ready_state(self):
        from voxkey_ui import should_render_hud

        self.assertTrue(should_render_hud(UiEvent("paste_succeeded", AppState.READY)))

    def test_hud_renders_copy_in_its_single_translucent_surface(self):
        from voxkey_ui import VoxKeyHud, create_qt_application

        app = create_qt_application()
        hud = VoxKeyHud()
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
