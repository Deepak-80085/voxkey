import unittest

from vocabulary import build_initial_prompt, normalize_vocabulary, with_command_terms, COMMAND_TERMS


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

    def test_command_words_follow_user_words_and_respect_the_limit(self):
        words = with_command_terms(["Zudio"])
        self.assertEqual(words[0], "Zudio")
        self.assertIn("Slack", words)
        full = normalize_vocabulary(with_command_terms([f"T{i}" for i in range(100)]))
        self.assertEqual(len(full), 100)
        self.assertEqual(full[-len(COMMAND_TERMS):], list(COMMAND_TERMS))  # user words are trimmed, not command terms
        self.assertEqual(normalize_vocabulary(with_command_terms(["slack"])).count("slack"), 1)


if __name__ == "__main__":
    unittest.main()
