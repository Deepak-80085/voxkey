import unittest
from unittest.mock import Mock, patch

import voxkey_app
from voxkey_app import claim_single_instance


class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_returns_false_when_named_mutex_exists(self):
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 123
        kernel32.GetLastError.return_value = 183

        with patch("voxkey_app._kernel32", kernel32):
            self.assertFalse(claim_single_instance())

    def test_first_instance_returns_true_and_keeps_mutex_handle(self):
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 123
        kernel32.GetLastError.return_value = 0

        with patch("voxkey_app._kernel32", kernel32):
            self.assertTrue(claim_single_instance())

    def test_second_launch_tells_the_user_voxkey_is_already_running(self):
        notify = getattr(voxkey_app, "notify_already_running", None)
        self.assertIsNotNone(notify)
        user32 = Mock()

        with patch("voxkey_app._user32", user32):
            notify()

        message = user32.MessageBoxW.call_args.args[1]
        self.assertIn("already running", message.lower())
        self.assertIn("system tray", message.lower())


if __name__ == "__main__":
    unittest.main()
