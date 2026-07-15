import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
REQUIRED_FROZEN_FILES = (
    Path("_internal") / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
)


def validate_frozen_app(app_dir: Path) -> list[str]:
    return [
        path.as_posix()
        for path in REQUIRED_FROZEN_FILES
        if not (app_dir / path).is_file()
    ]


class VoxKeyPackagingTests(unittest.TestCase):
    def test_voxkey_spec_bundles_required_native_runtime_dependencies(self):
        contents = (ROOT / "VoxKey.spec").read_text(encoding="utf-8")
        self.assertIn("voxkey_app.py", contents)
        self.assertIn("PySide6.QtWidgets", contents)
        self.assertIn("faster_whisper", contents)
        self.assertIn("assets/*.onnx", contents)
        self.assertIn("name='VoxKey'", contents)
        self.assertNotIn("PIL.ImageTk", contents)
        self.assertNotIn("pystray", contents)

    def test_voxkey_installer_is_per_user(self):
        contents = (ROOT / "installer" / "VoxKey.iss").read_text(encoding="utf-8")
        self.assertIn('#define MyAppName "VoxKey"', contents)
        self.assertIn('#define MyAppVersion "2.2.0"', contents)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\{#MyAppName}', contents)
        self.assertIn('Source: "..\\dist\\VoxKey\\*"', contents)

    def test_voxkey_package_has_brand_and_windows_version_metadata(self):
        spec = (ROOT / "VoxKey.spec").read_text(encoding="utf-8")

        self.assertTrue((ROOT / "asset" / "logo.png").is_file())
        self.assertTrue((ROOT / "asset" / "icon.ico").is_file())
        self.assertTrue((ROOT / "file_version_info.txt").is_file())
        self.assertIn("version='file_version_info.txt'", spec)

    def test_release_workflow_is_signing_ready_for_version_2_2_0(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        signing_script = (ROOT / "scripts" / "sign_windows.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("VoxKey-Setup-2.2.0.exe", workflow)
        self.assertIn("WINDOWS_CERTIFICATE", workflow)
        self.assertIn("signtool.exe", signing_script.lower())
        self.assertNotIn("VoxKey-Setup-2.1.0.exe", workflow)

    def test_frozen_validation_reports_missing_vad_model(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = validate_frozen_app(Path(temporary_directory))
        self.assertEqual(
            missing,
            ["_internal/faster_whisper/assets/silero_vad_v6.onnx"],
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} <frozen-app-directory>")
    missing = validate_frozen_app(Path(sys.argv[1]))
    if missing:
        print("Frozen application is missing required runtime dependencies:")
        print(*(f"- {path}" for path in missing), sep="\n")
        raise SystemExit(1)
    print("Frozen application contains all required runtime dependencies.")
