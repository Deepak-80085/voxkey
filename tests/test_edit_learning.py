import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from edit_learning import EditLearningWatcher, _WindowsEditReader, edited_phrase, safe_to_learn
from personal_memory import PersonalMemory


class EditLearningTests(unittest.TestCase):
    def test_edits_inside_own_paste_become_short_phrase_pairs(self):
        self.assertEqual(edited_phrase("Open git hub.", "Open GitHub.", "Open git hub."),
                         ("git hub", "GitHub"))
        self.assertEqual(edited_phrase("Say git now.", "Say Git now.", "Say git now."),
                         ("git", "Git"))
        self.assertEqual(edited_phrase("Use cash.", "Use cache.", "Use cash."),
                         ("cash", "cache"))

    def test_ignores_unrelated_or_unsafe_changes(self):
        self.assertIsNone(edited_phrase("before Open git.", "BEFORE Open git.", "Open git."))
        self.assertIsNone(edited_phrase("Open git.", "Open git. More text", "Open git."))
        self.assertIsNone(edited_phrase("Open git.", "Open git.", "Open git."))
        self.assertIsNone(edited_phrase("Open git. Open git.", "Open Git. Open git.", "Open git."))
        self.assertTrue(safe_to_learn("cash", "cache"))
        self.assertTrue(safe_to_learn("git hub", "GitHub"))
        self.assertFalse(safe_to_learn("open", "Open"))
        self.assertTrue(safe_to_learn("git", "Git", ["Git"]))
        self.assertFalse(safe_to_learn("use", "used"))
        self.assertFalse(safe_to_learn("good", "bad"))

    def test_reviewed_ambiguous_edit_persists_before_it_applies(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.json"
            memory = PersonalMemory(path)
            memory.suggest_correction("cash", "cache", "notepad.exe")
            self.assertEqual(memory.correct("cash", "notepad.exe"), "cash")
            self.assertEqual(len(PersonalMemory(path).list_suggestions()), 1)
            memory.accept_suggestion("cash", "cache", "notepad.exe")
            self.assertEqual(PersonalMemory(path).correct("cash", "notepad.exe"), "cache")
            self.assertEqual(memory.list_suggestions(), [])

    def test_watcher_only_reads_its_target_and_learns_close_word_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = PersonalMemory(Path(folder) / "memory.json")
            watcher = EditLearningWatcher(memory, lambda: True, lambda: 42)
            reader = Mock()
            reader.capture.return_value = (object(), "Use cash.")
            reader.read.return_value = "Use cache."
            ticks = iter(range(100))
            with patch("edit_learning._WindowsEditReader", return_value=reader), \
                    patch("edit_learning.time.monotonic", side_effect=lambda: next(ticks)), \
                    patch("edit_learning.time.sleep"), \
                    patch("comtypes.CoInitialize"), patch("comtypes.CoUninitialize"):
                watcher._observe(0, 42, "Use cash.", "notepad.exe")
            self.assertEqual(memory.correct("cash", "notepad.exe"), "cache")
            self.assertEqual(memory.correct("cash", "browser.exe"), "cash")
            self.assertEqual(memory.list_corrections()[0]["source"], "edit")

            reader.capture.reset_mock()
            watcher.foreground = lambda: 99
            with patch("edit_learning._WindowsEditReader", return_value=reader), \
                    patch("comtypes.CoInitialize"), patch("comtypes.CoUninitialize"):
                watcher._observe(0, 42, "Use cash.", "notepad.exe")
            reader.capture.assert_not_called()

    def test_long_document_uses_text_near_caret(self):
        reader = object.__new__(_WindowsEditReader)
        reader.u = SimpleNamespace(
            UIA_HasKeyboardFocusPropertyId=1, UIA_ControlTypePropertyId=2,
            UIA_EditControlTypeId=3, UIA_DocumentControlTypeId=4,
            TreeScope_Descendants=5, UIA_ValuePatternId=6, UIA_TextPatternId=7,
            IUIAutomationValuePattern=8, IUIAutomationTextPattern=9,
            TextPatternRangeEndpoint_Start=0, TextPatternRangeEndpoint_End=1,
            TextUnit_Character=0,
        )
        reader._range = None
        element = Mock(CurrentIsPassword=False, CurrentHasKeyboardFocus=True)
        value = Mock(CurrentValue="x" * 6000)
        text = Mock()
        region = Mock()
        region.GetText.side_effect = ["near Use cash. here", "near Use cache. here"]
        text.GetSelection.return_value = Mock(Length=1)
        text.GetSelection.return_value.GetElement.return_value.Clone.return_value = region
        element.GetCurrentPattern.side_effect = lambda key: Mock(QueryInterface=Mock(return_value=value if key == 6 else text))
        root = Mock()
        root.FindFirst.return_value = element
        reader.automation = Mock()
        reader.automation.ElementFromHandle.return_value = root

        captured = reader.capture(42, "Use cash.")

        self.assertEqual(captured, (element, "near Use cash. here"))
        self.assertEqual(reader.read(element), "near Use cache. here")
        region.MoveEndpointByUnit.assert_any_call(0, 0, -(len("Use cash.") + 128))

    def test_conflicting_auto_edit_stays_reviewable(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = PersonalMemory(Path(folder) / "memory.json")
            memory.add_correction("cash", "cache", "notepad.exe")
            self.assertFalse(memory.learn_edit("cash", "case", "notepad.exe"))
            self.assertEqual(memory.correct("cash", "notepad.exe"), "cache")
            self.assertEqual(memory.list_suggestions()[0]["intended"], "case")

    def test_distinctive_name_learns_across_apps(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = PersonalMemory(Path(folder) / "memory.json")
            self.assertTrue(memory.learn_edit("git hub", "GitHub", None))
            self.assertEqual(memory.correct("open git hub", "notepad.exe"), "open GitHub")
            self.assertEqual(memory.correct("open git hub", "terminal.exe"), "open GitHub")


if __name__ == "__main__":
    unittest.main()
