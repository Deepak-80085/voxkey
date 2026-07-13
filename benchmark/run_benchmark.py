"""Offline English transcription benchmark helpers and CLI."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path


def normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def word_error_rate(expected: str, actual: str) -> float:
    reference = normalized_words(expected)
    hypothesis = normalized_words(actual)
    if not reference:
        return 0.0 if not hypothesis else 1.0

    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_word in enumerate(reference, start=1):
        current = [reference_index]
        for hypothesis_index, hypothesis_word in enumerate(hypothesis, start=1):
            current.append(min(
                previous[hypothesis_index] + 1,
                current[hypothesis_index - 1] + 1,
                previous[hypothesis_index - 1]
                + (reference_word != hypothesis_word),
            ))
        previous = current
    return previous[-1] / len(reference)


def run_faster_whisper(model_name: str, audio_path: Path) -> tuple[str, float]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    started = time.perf_counter()
    segments, _ = model.transcribe(str(audio_path), language="en")
    transcript = " ".join(segment.text for segment in segments).strip()
    return transcript, time.perf_counter() - started


def main() -> None:
    if len(sys.argv) != 7 or sys.argv[1:3] != ["--engine", "faster-whisper"] or sys.argv[5] != "--manifest":
        raise SystemExit(
            "Usage: run_benchmark.py --engine faster-whisper --model <model> --manifest <manifest.json>"
        )

    model_name = sys.argv[4]
    manifest_path = Path(sys.argv[6])
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    for entry in entries:
        audio_path = manifest_path.parent / entry["audio"]
        actual, elapsed_s = run_faster_whisper(model_name, audio_path)
        results.append({
            "audio": str(audio_path),
            "expected": entry["expected"],
            "actual": actual,
            "word_error_rate": word_error_rate(entry["expected"], actual),
            "elapsed_s": elapsed_s,
        })

    print(json.dumps({"engine": "faster-whisper", "model": model_name, "results": results}, indent=2))


if __name__ == "__main__":
    main()
