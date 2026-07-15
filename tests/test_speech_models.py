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
        self.runtime.logger = Mock(return_value=Mock())
        self.model_dir = Path(self.temp_dir.name) / "models" / "speech"
        self.model_dir.mkdir(parents=True)
        (self.model_dir / "model.bin").write_bytes(b"valid model")
        self.models_dir = Mock(return_value=self.model_dir.parent)
        self.runtime.models_dir = self.models_dir

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ollama_cuda_runtime_directories_are_added_before_gpu_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "Programs" / "Ollama" / "lib" / "ollama"
            (base / "cuda_v12").mkdir(parents=True)
            (base / "mlx_cuda_v13").mkdir(parents=True)
            runtime = Mock()
            runtime.models_dir.return_value = Path(temp_dir) / "models"
            runtime.logger.return_value = Mock()
            handles = []

            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                manager = SpeechModelManager(runtime, dll_directory_adder=handles.append)
                manager._configure_cuda_runtime_search_path()

        self.assertEqual(handles, [str(base / "cuda_v12"), str(base / "mlx_cuda_v13")])

    def test_transcription_logs_the_active_inference_device(self):
        model, logger = Mock(), Mock()
        model.transcribe.return_value = ([], None)
        self.runtime.logger = Mock(return_value=logger)
        manager = SpeechModelManager(self.runtime, model_loader=Mock(return_value=model))
        manager.model, manager.device = model, "cuda"

        manager.transcribe(Path("sample.wav"))

        logger.info.assert_any_call("Transcribing with device=%s", "cuda")

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

    def test_existing_valid_model_is_not_downloaded_again(self):
        downloader = Mock()
        manager = SpeechModelManager(self.runtime, downloader=downloader)

        self.assertEqual(manager._ensure_model(), self.model_dir)
        downloader.assert_not_called()

    def test_model_download_is_directed_to_voxkey_owned_speech_directory(self):
        (self.model_dir / "model.bin").unlink()
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

    def test_repair_forces_download_to_replace_a_non_empty_corrupt_model(self):
        (self.model_dir / "model.bin").write_bytes(b"corrupt")

        def download(**_kwargs):
            (self.model_dir / "model.bin").write_bytes(b"repaired")

        def load(**_kwargs):
            if (self.model_dir / "model.bin").read_bytes() != b"repaired":
                raise RuntimeError("corrupt model")
            return Mock()

        downloader = Mock(side_effect=download)
        manager = SpeechModelManager(
            self.runtime,
            model_loader=Mock(side_effect=load),
            downloader=downloader,
            cuda_checker=lambda: [],
        )

        status = manager.repair()

        self.assertTrue(status.ready)
        self.assertTrue(downloader.call_args.kwargs["force_download"])

    def test_repair_reuses_a_healthy_speech_model_without_downloading(self):
        downloader = Mock()
        manager = SpeechModelManager(
            self.runtime,
            model_loader=Mock(return_value=Mock()),
            downloader=downloader,
            cuda_checker=lambda: [],
        )

        status = manager.repair()

        self.assertTrue(status.ready)
        downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
