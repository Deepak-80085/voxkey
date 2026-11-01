"""Offline English transcription benchmark helpers and CLI."""

from __future__ import annotations

import argparse
import json
import re
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


def run_faster_whisper(manager, audio_path: Path, beam_size: int) -> tuple[str, float]:
    started = time.perf_counter()
    transcript = manager.transcribe(audio_path, beam_size=beam_size)
    return transcript, time.perf_counter() - started


def main() -> None:
    from speech_models import SUPPORTED_MODELS, SpeechModelManager
    from voxkey_runtime import VoxKeyRuntime
    from writing_model import TextFormatter

    parser = argparse.ArgumentParser(description="Compare labeled clips using VoxKey's production decoder")
    parser.add_argument("--model", choices=SUPPORTED_MODELS, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--beam-size", type=int, choices=(1, 3, 5), default=1)
    parser.add_argument("--term", action="append", help="Override saved vocabulary; repeat per term")
    parser.add_argument("--with-writer", action="store_true")
    parser.add_argument("--max-wer", type=float)
    args = parser.parse_args()
    manifest_path = args.manifest
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = VoxKeyRuntime()
    manager = SpeechModelManager(
        runtime,
        vocabulary_provider=lambda: args.term if args.term is not None else runtime.load_settings()["vocabulary"],
        model_name=args.model,
    )
    status = manager.health_check()
    if not status.ready:
        raise SystemExit(status.reason)
    writer = None
    if args.with_writer:
        writer = TextFormatter(vocabulary_provider=lambda: runtime.load_settings()["vocabulary"])
    results = []
    errors = words = 0
    flow_errors = flow_words = 0
    for entry in entries:
        audio_path = manifest_path.parent / entry["audio"]
        actual, elapsed_s = run_faster_whisper(manager, audio_path, args.beam_size)
        reference_words = len(normalized_words(entry["expected"]))
        clip_wer = word_error_rate(entry["expected"], actual)
        errors += round(clip_wer * reference_words)
        words += reference_words
        result = {
            "audio": str(audio_path),
            "expected": entry["expected"],
            "actual": actual,
            "word_error_rate": clip_wer,
            "elapsed_s": elapsed_s,
        }
        if "flow" in entry:
            flow_wer = word_error_rate(entry["expected"], entry["flow"])
            flow_errors += round(flow_wer * reference_words)
            flow_words += reference_words
            result["flow_word_error_rate"] = flow_wer
        if writer:
            started = time.perf_counter()
            result["formatted"] = writer.polish(actual)
            result["writer_elapsed_s"] = time.perf_counter() - started
        results.append(result)

    aggregate_wer = errors / words if words else 0.0
    summary = {"model": args.model, "device": status.device, "beam_size": args.beam_size, "vocabulary": args.term if args.term is not None else runtime.load_settings()["vocabulary"], "word_error_rate": aggregate_wer, "results": results}
    if flow_words:
        summary["flow_word_error_rate"] = flow_errors / flow_words
    print(json.dumps(summary, indent=2))
    if args.max_wer is not None and aggregate_wer > args.max_wer:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
