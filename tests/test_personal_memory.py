import tempfile
import unittest
from pathlib import Path

from personal_memory import PersonalMemory


class PersonalMemoryTests(unittest.TestCase):
    def test_corrupt_file_does_not_crash_dictation_or_get_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text("{broken", encoding="utf-8")
            memory = PersonalMemory(path)
            self.assertEqual(memory.correct("hello"), "hello")
            with self.assertRaises(OSError):
                memory.add_correction("hello", "world")
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_correction_survives_restart_and_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = PersonalMemory(path)
            memory.add_correction("vox key", "VoxKey")
            self.assertEqual(PersonalMemory(path).correct("Open vox key, please."), "Open VoxKey, please.")
            memory.delete_correction("vox key")
            self.assertEqual(PersonalMemory(path).correct("Open vox key."), "Open vox key.")

    def test_rules_are_exact_non_cascading_and_app_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = PersonalMemory(Path(directory) / "memory.json")
            memory.add_correction("git", "Git")
            memory.add_correction("GitHub", "GitHub.com", app="browser.exe")
            memory.add_correction("cash", "cache", app="editor.exe")
            self.assertEqual(memory.correct("git and GitHub with cash", "editor.exe"), "Git and GitHub with cache")
            self.assertEqual(memory.correct("cash in git", "browser.exe"), "cash in Git")
            self.assertEqual(memory.correct("github", "browser.exe"), "GitHub.com")
            self.assertEqual(memory.correct("digit"), "digit")

    def test_recent_output_is_local_bounded_and_clearable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = PersonalMemory(path)
            for number in range(55):
                memory.remember_output(f"Dictation {number}")
            self.assertEqual(len(PersonalMemory(path).history()), 50)
            self.assertEqual(memory.history()[0]["text"], "Dictation 54")
            memory.clear_history()
            self.assertEqual(PersonalMemory(path).history(), [])

    def test_snippet_expands_only_its_full_cue_and_style_is_app_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = PersonalMemory(path)
            memory.add_snippet("my meeting link", "https://example.com/meet")
            memory.set_style("Notepad.exe", "minimal")
            reopened = PersonalMemory(path)
            self.assertEqual(reopened.snippet_for("My meeting link."), "https://example.com/meet")
            self.assertIsNone(reopened.snippet_for("send my meeting link"))
            self.assertEqual(reopened.style_for("NOTEPAD.EXE"), "minimal")
            self.assertEqual(reopened.style_for("browser.exe"), "standard")
            reopened.delete_snippet("my meeting link")
            reopened.set_style("notepad.exe", "standard")
            self.assertIsNone(PersonalMemory(path).snippet_for("my meeting link"))
            self.assertEqual(PersonalMemory(path).style_for("notepad.exe"), "standard")


if __name__ == "__main__":
    unittest.main()
