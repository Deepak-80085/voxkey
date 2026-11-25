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

    def test_polls_every_50_ms(self):
        sleep = Mock()
        now = [0.0]
        focus_app("T3 Code", find=Mock(side_effect=[None, 42]), bring=Mock(return_value=True),
                  sleep=sleep, clock=lambda: now[0])
        sleep.assert_called_once_with(0.05)

    def test_polling_slows_to_250_ms_after_one_second(self):
        sleeps, now = [], [0.0]
        def sleep(s):
            sleeps.append(s)
            now[0] += s
        focus_app("T3 Code", find=Mock(return_value=None), bring=Mock(), timeout=10.0,
                  sleep=sleep, clock=lambda: now[0])
        self.assertEqual(sleeps[0], 0.05)
        self.assertEqual(sleeps[-1], 0.25)
        self.assertLess(len(sleeps), 60)

    def test_find_window_prefers_the_largest_window_of_the_app(self):
        area = {1: 100, 2: 5000, 3: 300}
        with patch.object(window_focus, "list_windows", return_value=[1, 2, 3]):
            self.assertEqual(window_focus.find_window("slack.exe", area=area.get), 2)
        with patch.object(window_focus, "list_windows", return_value=[]):
            self.assertIsNone(window_focus.find_window("slack.exe", area=area.get))

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

    def test_whatsapp_title_must_be_the_app_window_not_a_browser_tab(self):
        match = window_focus.title_matches
        self.assertTrue(match("WhatsApp", "WhatsApp"))
        self.assertTrue(match("WhatsApp", "(3) WhatsApp"))
        for tab in ("WhatsApp Web - Google Chrome", "WhatsApp - Google Chrome", "WhatsApp — Mozilla Firefox",
                    "Notes about WhatsApp"):
            self.assertFalse(match("WhatsApp", tab), tab)


class FocusNewTests(unittest.TestCase):
    def _run(self, found, bring, timeout=1.0):
        now = [0.0]
        sleep = lambda s: now.__setitem__(0, now[0] + s)
        started = Mock()
        hwnd = window_focus.focus_new("Terminal", started, find=Mock(side_effect=found), bring=bring,
                                      timeout=timeout, sleep=sleep, clock=lambda: now[0])
        return hwnd, started

    def test_focuses_only_the_window_that_was_not_there_before_launch(self):
        bring = Mock(return_value=True)
        hwnd, started = self._run([[5, 6], [5, 6], [5, 6, 9]], bring)
        self.assertEqual(hwnd, 9)
        bring.assert_called_once_with(9)
        started.assert_called_once_with()

    def test_none_when_no_new_window_appears(self):
        bring = Mock()
        self.assertIsNone(self._run([[5]] * 300, bring)[0])
        bring.assert_not_called()

    def test_none_when_the_new_window_will_not_take_focus(self):
        self.assertIsNone(self._run([[5], [5, 9]], Mock(return_value=False))[0])


if __name__ == "__main__":
    unittest.main()
