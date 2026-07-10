import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from refiner import Refiner
from runtime import app_data_dir, recordings_dir


class RuntimePathTests(unittest.TestCase):
    def test_application_paths_are_created_outside_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                app_dir = app_data_dir()
                recording_dir = recordings_dir()

        self.assertEqual(app_dir, Path(temp_dir) / "SimpleSpeech")
        self.assertEqual(recording_dir, app_dir / "recordings")
        self.assertNotIn("simplespeech/temp_recording", str(recording_dir).lower())


class RefinerTests(unittest.TestCase):
    def test_request_failure_preserves_raw_text_and_marks_unavailable(self):
        import requests

        refiner = Refiner()
        with patch.object(
            refiner,
            "_call_ollama",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            text, available = refiner.refine("hello world")

        self.assertEqual(text, "hello world")
        self.assertFalse(available)


if __name__ == "__main__":
    unittest.main()
