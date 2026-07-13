import unittest
from unittest.mock import Mock, call, patch

from app import paste_text_at_cursor


class PasteTextTests(unittest.TestCase):
    def test_blank_text_does_not_access_clipboard_or_press_keys(self):
        controller = Mock()
        with patch("app.pyperclip.copy") as copy, patch("app.pyperclip.paste") as paste:
            result = paste_text_at_cursor("  ", controller)

        self.assertFalse(result)
        copy.assert_not_called()
        paste.assert_not_called()
        controller.press.assert_not_called()

    def test_paste_restores_clipboard_and_sends_one_paste_chord(self):
        controller = Mock()
        with (
            patch("app.pyperclip.paste", return_value="old clipboard"),
            patch("app.pyperclip.copy") as copy,
            patch("app.time.sleep"),
        ):
            result = paste_text_at_cursor("new text", controller)

        self.assertTrue(result)
        self.assertEqual(copy.call_args_list, [call("new text"), call("old clipboard")])
        self.assertEqual(controller.press.call_count, 2)
        self.assertEqual(controller.release.call_count, 8)

    def test_clipboard_read_failure_still_pastes_without_restoration(self):
        controller = Mock()
        with (
            patch(
                "app.pyperclip.paste",
                side_effect=__import__("pyperclip").PyperclipException("clipboard unavailable"),
            ),
            patch("app.pyperclip.copy") as copy,
            patch("app.time.sleep"),
        ):
            result = paste_text_at_cursor("new text", controller)

        self.assertTrue(result)
        copy.assert_called_once_with("new text")
        self.assertEqual(controller.press.call_count, 2)


if __name__ == "__main__":
    unittest.main()
