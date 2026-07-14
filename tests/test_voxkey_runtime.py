import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voxkey_runtime import AppState, VoxKeyRuntime


class VoxKeyRuntimeTests(unittest.TestCase):
    def test_runtime_uses_voxkey_localappdata_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                runtime = VoxKeyRuntime()
                self.assertEqual(runtime.data_dir(), Path(temp_dir) / "VoxKey")
                self.assertEqual(runtime.models_dir(), Path(temp_dir) / "VoxKey" / "models")
                self.assertEqual(
                    runtime.recordings_dir(), Path(temp_dir) / "VoxKey" / "recordings"
                )

    def test_default_settings_require_small_english_and_no_base_fallback(self):
        settings = VoxKeyRuntime().default_settings()

        self.assertEqual(settings["speech_model"], "small.en")
        self.assertNotIn("base.en", str(settings))
        self.assertEqual(settings["ollama_model"], "qwen3.5:0.8b")

    def test_saves_and_loads_settings_from_voxkey_data_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                runtime = VoxKeyRuntime()
                runtime.save_settings({"hotkey": "ctrl+space"})
                settings = runtime.load_settings()

        self.assertEqual(settings["speech_model"], "small.en")
        self.assertEqual(settings["hotkey"], "ctrl+space")

    def test_state_contract_includes_recoverable_repair_state(self):
        self.assertEqual(AppState.NEEDS_REPAIR.value, "Needs repair")
        self.assertEqual(AppState.READY.value, "Ready")

    def test_sound_feedback_defaults_to_enabled_and_persists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                runtime = VoxKeyRuntime()
                self.assertTrue(runtime.default_settings()["sounds_enabled"])
                runtime.save_settings({"sounds_enabled": False})
                self.assertFalse(runtime.load_settings()["sounds_enabled"])


if __name__ == "__main__":
    unittest.main()
