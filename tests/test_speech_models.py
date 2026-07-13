import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from speech_models import SpeechModelManager
from voxkey_runtime import VoxKeyRuntime


class SpeechModelTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = VoxKeyRuntime()
        self.model_dir = Path(self.temp_dir.name) / "models" / "speech"
        self.model_dir.mkdir(parents=True)
        (self.model_dir / "model.bin").write_bytes(b"valid model")
        self.models_dir = Mock(return_value=self.model_dir.parent)
        self.runtime.models_dir = self.models_dir

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_gpu_load_failure_retries_same_small_en_model_on_cpu(self):
        cpu_model = Mock()
        loader = Mock(side_effect=[RuntimeError("GPU unavailable"), cpu_model])
        manager = SpeechModelManager(
            self.runtime,
            model_loader=loader,
            cuda_checker=lambda: [],
        )

        with patch.object(manager, "_ensure_model", return_value=self.model_dir):
            status = manager.health_check()

        self.assertTrue(status.ready)
        self.assertEqual(status.device, "cpu")
        self.assertEqual(loader.call_args_list[0].kwargs["model_size_or_path"], str(self.model_dir))
        self.assertEqual(loader.call_args_list[1].kwargs["model_size_or_path"], str(self.model_dir))
        self.assertEqual(loader.call_args_list[1].kwargs["device"], "cpu")
        self.assertNotIn("base.en", str(loader.call_args_list))

    def test_model_download_is_directed_to_voxkey_owned_speech_directory(self):
        downloader = Mock()
        manager = SpeechModelManager(self.runtime, downloader=downloader)

        model_dir = manager._ensure_model()

        self.assertEqual(model_dir, self.model_dir)
        self.assertEqual(downloader.call_args.kwargs["repo_id"], "Systran/faster-whisper-small.en")
        self.assertEqual(downloader.call_args.kwargs["local_dir"], str(self.model_dir))

    def test_missing_or_empty_model_file_returns_repair_state_not_exception(self):
        loader = Mock()
        manager = SpeechModelManager(self.runtime, model_loader=loader)
        empty_model_dir = Path(self.temp_dir.name) / "empty"
        empty_model_dir.mkdir()

        with patch.object(manager, "_ensure_model", return_value=empty_model_dir):
            status = manager.health_check()

        self.assertFalse(status.ready)
        self.assertIsNone(status.device)
        self.assertIn("repair", status.reason.lower())
        loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
