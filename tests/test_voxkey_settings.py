import unittest
from unittest.mock import Mock


class SettingsActionsTests(unittest.TestCase):
    def test_sound_toggle_persists_without_restarting_pipeline(self):
        from voxkey_ui import SettingsActions

        runtime = Mock()
        runtime.load_settings.return_value = {"sounds_enabled": True}
        actions = SettingsActions(Mock(), runtime)
        actions.set_sounds_enabled(False)

        self.assertFalse(runtime.save_settings.call_args.args[0]["sounds_enabled"])

    def test_repair_action_delegates_to_controller(self):
        from voxkey_ui import SettingsActions

        controller = Mock()
        SettingsActions(controller, Mock()).repair()
        controller.repair_models.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
