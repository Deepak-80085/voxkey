import unittest
from unittest.mock import Mock, patch

import window_focus
from window_focus import WINDOWS, focus_app, is_foreground


class FocusAppTests(unittest.TestCase):
    def _run(self, find, bring, timeout=1.0):
        now = [0.0]
        sleep = lambda s: now.__setitem__(0, now[0] + s)
        return focus_app("T3 Code", find=find, bring=bring, timeout=timeout, sleep=sleep, clock=lambda: now[0])

    def test_waits_for_the_window_then_focuses_it(self):
        find = Mock(side_effect=[None, None, 42])
        bring = Mock(return_value=True)
        self.assertEqual(self._run(find, bring), 42)  # the exact window, for later front checks
        bring.assert_called_once_with(42)
        find.assert_called_with("t3 code (nightly).exe", None)

    def test_false_when_no_window_appears(self):
        bring = Mock()
        self.assertFalse(self._run(Mock(return_value=None), bring))
        bring.assert_not_called()

    def test_false_when_the_window_will_not_take_focus(self):
        self.assertFalse(self._run(Mock(return_value=7), Mock(return_value=False)))

    def test_is_foreground_compares_the_exact_window_handle(self):
        user32 = Mock()
        with patch.object(window_focus, "_user32", user32):
            user32.GetForegroundWindow.return_value = 42
            self.assertTrue(is_foreground(42))
            user32.GetForegroundWindow.return_value = 43  # another window of the same app
            self.assertFalse(is_foreground(42))
            user32.GetForegroundWindow.return_value = None
            self.assertFalse(is_foreground(42))

    def test_spec_names(self):
        self.assertEqual(WINDOWS["whatsapp"], (None, "WhatsApp"))
        self.assertEqual(WINDOWS["slack"][0], "slack.exe")
        self.assertEqual(WINDOWS["chatgpt"][0], "chatgpt.exe")


if __name__ == "__main__":
    unittest.main()
