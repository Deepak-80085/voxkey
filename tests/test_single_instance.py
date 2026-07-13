import unittest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
