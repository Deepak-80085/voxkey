import unittest

from writing_model import TextFormatter, WritingModelUnavailable, apply_spoken_corrections


class TextFormatterTests(unittest.TestCase):
    def test_explicit_single_word_backtrack_without_general_rewriting(self):
        self.assertEqual(
            apply_spoken_corrections("Let's meet at 2, actually 3 tomorrow"),
            "Let's meet at 3 tomorrow",
        )
        self.assertEqual(
            apply_spoken_corrections("Tuesday actually no Wednesday works"),
            "Wednesday works",
        )
        self.assertEqual(apply_spoken_corrections("I actually think so"), "I actually think so")
        self.assertEqual(
            apply_spoken_corrections("Send it, actually I think tomorrow"),
            "Send it, actually I think tomorrow",
        )

    def test_empty_speech_is_unavailable_not_pasted(self):
        with self.assertRaises(WritingModelUnavailable):
            TextFormatter().polish("  um  ")

    def test_keeps_every_word_and_adds_sentence_formatting(self):
        formatter = TextFormatter()
        self.assertEqual(formatter.polish("I can haz this on Tuesday"), "I can haz this on Tuesday.")
        self.assertEqual(formatter.polish("hey john can you review this"), "Hey john can you review this.")
        self.assertEqual(formatter.polish("The build passed. Send it now."), "The build passed. Send it now.")

    def test_app_styles_format_without_changing_words(self):
        formatter = TextFormatter()
        self.assertEqual(formatter.polish("send the update", style="minimal"), "Send the update")
        self.assertEqual(
            formatter.polish("send the update new line review the draft", style="bullet notes"),
            "• Send the update.\n• Review the draft.",
        )

    def test_vocabulary_restores_preferred_casing_without_changing_words(self):
        formatter = TextFormatter(vocabulary_provider=lambda: ["Git", "GitHub"])
        self.assertEqual(formatter.polish("i pushed git to github"), "I pushed Git to GitHub.")

    def test_keeps_mixed_case_name_at_start(self):
        self.assertEqual(TextFormatter().polish("iPhone is ready"), "iPhone is ready.")

    def test_spoken_commands_format_directly(self):
        formatter = TextFormatter()
        self.assertEqual(
            formatter.polish("buy milk new line call Zudio new paragraph tell the team"),
            "Buy milk\nCall Zudio\n\nTell the team.",
        )
        self.assertEqual(formatter.polish("how are you question mark"), "How are you?")
        self.assertEqual(formatter.polish("hello full stop how are you"), "Hello. How are you.")
        self.assertEqual(
            formatter.polish("bullet point update docs bullet point run tests"), "• Update docs\n• Run tests."
        )

    def test_long_dictation_removes_fillers_without_rewriting(self):
        polished = TextFormatter().polish("Um, preserve this wording and order, uh exactly. " * 30)

        self.assertNotIn("Um", polished)
        self.assertNotIn("uh", polished)
        self.assertIn("preserve this wording and order", polished.casefold())

    def test_long_dictation_keeps_explicit_paragraph_command(self):
        polished = TextFormatter().polish("say these exact words " * 60 + "new paragraph final thought")

        self.assertIn("\n\nFinal thought.", polished)


if __name__ == "__main__":
    unittest.main()
