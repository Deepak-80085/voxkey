import sys
import tempfile
import unittest
from pathlib import Path


REQUIRED_FROZEN_FILES = (
    Path("_internal") / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
)
IMAGINGTK_GLOB = Path("_internal") / "PIL" / "_imagingtk*.pyd"


def validate_frozen_app(app_dir: Path) -> list[str]:
    """Return runtime dependencies absent from a PyInstaller app folder."""
    missing = [
        path.as_posix()
        for path in REQUIRED_FROZEN_FILES
        if not (app_dir / path).is_file()
    ]
    if not list((app_dir / IMAGINGTK_GLOB.parent).glob(IMAGINGTK_GLOB.name)):
        missing.append(IMAGINGTK_GLOB.as_posix())
    return missing


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

    def test_frozen_validation_reports_missing_pillow_tk_bridge(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_dir = Path(temporary_directory)
            vad_model = app_dir / REQUIRED_FROZEN_FILES[0]
            vad_model.parent.mkdir(parents=True)
            vad_model.touch()

            missing = validate_frozen_app(app_dir)

        self.assertEqual(missing, ["_internal/PIL/_imagingtk*.pyd"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} <frozen-app-directory>")

    missing = validate_frozen_app(Path(sys.argv[1]))
    if missing:
        print("Frozen application is missing required runtime dependencies:")
        print(*(f"- {path}" for path in missing), sep="\n")
        raise SystemExit(1)

    print("Frozen application contains all required runtime dependencies.")
