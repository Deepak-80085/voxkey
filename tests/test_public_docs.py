import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PublicRepositoryDocumentationTests(unittest.TestCase):
    def test_public_repository_has_local_only_setup_and_license_docs(self):
        self.assertTrue((ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        privacy = (ROOT / "docs" / "privacy.md").read_text(encoding="utf-8")
        self.assertIn("small.en", readme)
        self.assertIn("qwen3.5:0.8b", readme)
        self.assertNotIn("ollama pull", readme)
        self.assertIn("No audio or text leaves your computer", privacy)
        launch = (ROOT / "docs" / "launch.md").read_text(encoding="utf-8")
        self.assertIn("30-second demo", launch)
        self.assertIn("beta testers", launch)


if __name__ == "__main__":
    unittest.main()
