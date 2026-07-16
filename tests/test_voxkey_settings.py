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

    def test_microphone_selection_persists_and_updates_live_recorder(self):
        from voxkey_ui import SettingsActions

        runtime = Mock()
        runtime.load_settings.return_value = {"microphone": None}
        update_recorder = Mock()
        actions = SettingsActions(Mock(), runtime, set_microphone=update_recorder)

        actions.set_microphone(3)

        self.assertEqual(runtime.save_settings.call_args.args[0]["microphone"], 3)
        update_recorder.assert_called_once_with(3)

    def test_hotkey_selection_persists_and_updates_live_listener(self):
        from voxkey_ui import SettingsActions

        runtime = Mock()
        runtime.load_settings.return_value = {'hotkey': 'right_ctrl'}
        update_hotkey = Mock()
        actions = SettingsActions(Mock(), runtime, set_hotkey=update_hotkey)

        actions.set_hotkey('f8')

        self.assertEqual(runtime.save_settings.call_args.args[0]['hotkey'], 'f8')
        update_hotkey.assert_called_once_with('f8')

    def test_autostart_selection_persists_and_updates_windows(self):
        from voxkey_ui import SettingsActions

        runtime = Mock()
        runtime.load_settings.return_value = {'start_with_windows': False}
        update_autostart = Mock()
        actions = SettingsActions(Mock(), runtime, set_autostart=update_autostart)

        actions.set_autostart(True)

        self.assertTrue(runtime.save_settings.call_args.args[0]['start_with_windows'])
        update_autostart.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
