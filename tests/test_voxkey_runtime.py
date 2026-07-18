import tempfile
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
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
        self.assertTrue(settings["start_with_windows"])

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

    def test_each_runtime_logger_writes_to_its_own_data_directory(self):
        first_logger = second_logger = None
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as first, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as second:
                with patch.dict("os.environ", {"LOCALAPPDATA": first}, clear=False):
                    first_logger = VoxKeyRuntime().logger()
                with patch.dict("os.environ", {"LOCALAPPDATA": second}, clear=False):
                    second_logger = VoxKeyRuntime().logger()

                first_path = Path(first_logger.handlers[0].baseFilename)
                second_path = Path(second_logger.handlers[0].baseFilename)

                self.assertEqual(first_path, Path(first) / "VoxKey" / "voxkey.log")
                self.assertEqual(second_path, Path(second) / "VoxKey" / "voxkey.log")
        finally:
            for logger in (first_logger, second_logger):
                if logger:
                    for handler in logger.handlers:
                        handler.close()

    def test_unhandled_exception_hooks_write_tracebacks_to_local_log(self):
        original_sys_hook = sys.excepthook
        original_thread_hook = threading.excepthook
        runtime = None
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                    runtime = VoxKeyRuntime()
                    runtime.install_exception_logging()
                    try:
                        raise RuntimeError("worker exploded")
                    except RuntimeError as error:
                        threading.excepthook(
                            SimpleNamespace(
                                exc_type=type(error),
                                exc_value=error,
                                exc_traceback=error.__traceback__,
                                thread=SimpleNamespace(name="test-worker"),
                            )
                        )
                        sys.excepthook(type(error), error, error.__traceback__)
                    for handler in runtime.logger().handlers:
                        handler.flush()
                    contents = (runtime.data_dir() / "voxkey.log").read_text(encoding="utf-8")
        finally:
            sys.excepthook = original_sys_hook
            threading.excepthook = original_thread_hook
            if runtime:
                for handler in runtime.logger().handlers:
                    handler.close()

        self.assertIn("Unhandled exception in thread test-worker", contents)
        self.assertIn("Unhandled exception in main thread", contents)
        self.assertIn("RuntimeError: worker exploded", contents)

    def test_windows_autostart_writes_current_executable_to_run_key(self):
        from unittest.mock import Mock, patch
        from voxkey_app import set_start_with_windows

        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=None)
        with patch('voxkey_app.winreg.CreateKey', return_value=key), patch(
            'voxkey_app.winreg.SetValueEx'
        ) as set_value:
            set_start_with_windows(True, executable=Path('C:/VoxKey/VoxKey.exe'))

        self.assertEqual(set_value.call_args.args[1], 'VoxKey')
        self.assertIn('VoxKey.exe', set_value.call_args.args[4])


if __name__ == "__main__":
    unittest.main()
