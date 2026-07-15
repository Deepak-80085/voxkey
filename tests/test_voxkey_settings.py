import unittest
from unittest.mock import Mock, patch


class SettingsActionsTests(unittest.TestCase):
    def test_sound_toggle_persists_without_restarting_pipeline(self):
        from voxkey_ui import SettingsActions

        runtime = Mock()
        runtime.load_settings.return_value = {"sounds_enabled": True}
        actions = SettingsActions(Mock(), runtime)
        actions.set_sounds_enabled(False)

        self.assertFalse(runtime.save_settings.call_args.args[0]["sounds_enabled"])

    def test_repair_action_runs_controller_repair_on_a_daemon_thread(self):
        from voxkey_ui import SettingsActions

        controller = Mock()
        with patch("voxkey_ui.threading.Thread") as thread:
            worker = thread.return_value
            SettingsActions(controller, Mock()).repair()

        thread.assert_called_once_with(target=controller.repair_models, daemon=True)
        worker.start.assert_called_once_with()
        controller.repair_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
