import unittest
from pathlib import Path


class PackagingSpecTests(unittest.TestCase):
    def test_spec_collects_faster_whisper_vad_assets(self):
        spec = Path(__file__).parents[1] / "SimpleSpeech.spec"
        contents = spec.read_text(encoding="utf-8")

        self.assertIn("collect_data_files", contents)
        self.assertIn("faster_whisper", contents)
        self.assertIn("assets/*.onnx", contents)

    def test_spec_collects_pillow_tk_runtime(self):
        spec = Path(__file__).parents[1] / "SimpleSpeech.spec"
        contents = spec.read_text(encoding="utf-8")

        self.assertIn("PIL.ImageTk", contents)
        self.assertIn("PIL._imagingtk", contents)


if __name__ == "__main__":
    unittest.main()
