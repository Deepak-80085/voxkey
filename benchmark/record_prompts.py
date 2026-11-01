"""Record known-text clips locally for a personal speech comparison."""

import json
from pathlib import Path

from voxkey_app import Recorder


PROMPTS = [
    "Git should sync with GitHub before I ship version three.",
    "Please open VoxKey and add Wispr Flow to the project notes.",
    "I said cache, not cash, when I described the build failure.",
]


def main() -> None:
    output = Path(__file__).parent / "local_samples" / "personal"
    output.mkdir(parents=True, exist_ok=True)
    recorder = Recorder(output)
    entries = []
    print("Read each sentence exactly. Audio stays in", output.resolve())
    try:
        for number, prompt in enumerate(PROMPTS, start=1):
            while True:
                print(f"\n{number}. {prompt}")
                input("Press Enter to start recording.")
                recorder.start()
                input("Speak, then press Enter to stop.")
                path = recorder.stop_and_save()
                if input("Press Enter to keep, or type r to retry: ").strip().lower() != "r":
                    target = output / f"personal-{number}.wav"
                    path.replace(target)
                    entries.append({"audio": target.name, "expected": prompt})
                    break
                path.unlink()
    finally:
        recorder.abort()
    (output / "manifest.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print("Saved", output / "manifest.json")


if __name__ == "__main__":
    main()
