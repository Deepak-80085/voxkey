import unittest

from benchmark.run_benchmark import normalized_words, word_error_rate


class BenchmarkTests(unittest.TestCase):
    def test_normalized_words_ignore_case_punctuation_and_extra_whitespace(self):
        self.assertEqual(
            normalized_words("  The, Zudio! shopping  "),
            ["the", "zudio", "shopping"],
        )

    def test_word_error_rate_counts_substitution_insertion_and_deletion(self):
        self.assertEqual(word_error_rate("one two three", "one four"), 2 / 3)


if __name__ == "__main__":
    unittest.main()
