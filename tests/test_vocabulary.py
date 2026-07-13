import unittest

from vocabulary import build_initial_prompt, normalize_vocabulary


class VocabularyTests(unittest.TestCase):
    def test_normalizes_deduplicates_and_discards_blank_entries(self):
        self.assertEqual(
            normalize_vocabulary([" Zudio ", "zudio", "Inno   Setup", "", "   "]),
            ["Zudio", "Inno Setup"],
        )

    def test_limits_entries_to_prevent_an_unbounded_prompt(self):
        words = [f"Term {index}" for index in range(101)]

        self.assertEqual(len(normalize_vocabulary(words)), 100)

    def test_prompt_mentions_only_local_user_terms(self):
        self.assertEqual(
            build_initial_prompt(["Zudio", "VoxKey"]),
            "English dictation. Terms: Zudio, VoxKey.",
        )
        self.assertEqual(build_initial_prompt([]), "")


if __name__ == "__main__":
    unittest.main()
