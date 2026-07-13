import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class VoxKeyPackagingTests(unittest.TestCase):
    def test_voxkey_spec_bundles_required_native_runtime_dependencies(self):
        contents = (ROOT / "VoxKey.spec").read_text(encoding="utf-8")

        self.assertIn("voxkey_app.py", contents)
        self.assertIn("PIL.ImageTk", contents)
        self.assertIn("PIL._imagingtk", contents)
        self.assertIn("faster_whisper", contents)
        self.assertIn("assets/*.onnx", contents)
        self.assertIn("name='VoxKey'", contents)

    def test_voxkey_installer_is_per_user_and_keeps_user_data_outside_program_files(self):
        contents = (ROOT / "installer" / "VoxKey.iss").read_text(encoding="utf-8")

        self.assertIn('#define MyAppName "VoxKey"', contents)
        self.assertIn('#define MyAppVersion "2.0.1-test"', contents)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\{#MyAppName}', contents)
        self.assertIn('Source: "..\\dist\\VoxKey\\*"', contents)
        self.assertNotIn("VoxKey\\recordings", contents)


if __name__ == "__main__":
    unittest.main()
