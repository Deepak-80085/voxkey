# Offline English transcription benchmark

Use this tool to compare local speech engines/models with actual English dictation before changing the app default.

## Fixtures

Create consented 16 kHz mono WAV recordings under `benchmark/fixtures/`. Add each file and its exact intended sentence to `benchmark/fixtures/manifest.json`:

```json
[
  {
    "audio": "zudio.wav",
    "expected": "The Zudio shopping is cheap and good."
  }
]
```

Include quiet and noisy recordings, fast speech, proper names, brands, technical terms, and normal conversational sentences. Never add recordings without the speaker's consent.

## Run faster-whisper

```powershell
.\.venv\Scripts\python.exe benchmark\run_benchmark.py `
  --engine faster-whisper `
  --model small.en `
  --manifest benchmark\fixtures\manifest.json
```

The output reports per-recording latency and normalized word error rate. Lower word error rate and lower latency are better. The benchmark runs locally and does not upload audio.
