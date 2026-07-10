import ctypes
import inspect
import os
import sysconfig
import time

from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self):
        self._gpu_model_size = os.getenv("WHISPER_MODEL_GPU", "distil-large-v3")
        self._cpu_model_size = os.getenv("WHISPER_MODEL_CPU", "base.en")
        self._prefer_speed = os.getenv("WHISPER_PREFER_SPEED", "1") == "1"
        self._vad_filter = os.getenv("WHISPER_VAD_FILTER", "1") == "1"
        print(
            "Loading Whisper models "
            f"(GPU={self._gpu_model_size}, CPU fallback={self._cpu_model_size})..."
        )
        self._model_size = None
        self._device = None
        self._compute_type = None
        self.model = None
        self._supports_chunk_length_s = False
        self._supports_chunk_length = False
        self._supports_without_timestamps = False
        self._supports_best_of = False
        self._dll_dir_handles = []

        self._configure_windows_cuda_dll_paths()
        self._load_model_with_fallback()

    def _configure_windows_cuda_dll_paths(self):
        if os.name != "nt":
            return

        purelib = sysconfig.get_paths().get("purelib")
        if not purelib:
            return

        candidate_dirs = [
            os.path.join(purelib, "nvidia", "cublas", "bin"),
            os.path.join(purelib, "nvidia", "cudnn", "bin"),
            os.path.join(purelib, "nvidia", "cuda_runtime", "bin"),
        ]

        existing_dirs = [d for d in candidate_dirs if os.path.isdir(d)]
        if not existing_dirs:
            return

        # Ensure dependent CUDA DLLs can be resolved by ctranslate2 on Windows.
        for dll_dir in existing_dirs:
            if hasattr(os, "add_dll_directory"):
                self._dll_dir_handles.append(os.add_dll_directory(dll_dir))

        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(";") if current_path else []
        for dll_dir in existing_dirs:
            if dll_dir not in path_parts:
                path_parts.insert(0, dll_dir)
        os.environ["PATH"] = ";".join(path_parts)

    def _is_cuda_runtime_error(self, exc):
        message = str(exc).lower()
        cuda_error_signals = (
            "cublas64_12.dll",
            "cudnn",
            "cuda",
            "ctranslate2",
            "cannot be loaded",
            "not found",
        )
        return any(signal in message for signal in cuda_error_signals)

    def _set_transcribe_signature_flags(self):
        signature = inspect.signature(self.model.transcribe)
        self._supports_chunk_length_s = "chunk_length_s" in signature.parameters
        self._supports_chunk_length = "chunk_length" in signature.parameters
        self._supports_without_timestamps = (
            "without_timestamps" in signature.parameters
        )
        self._supports_best_of = "best_of" in signature.parameters

    def _check_cuda_runtime(self):
        required = ("cublas64_12.dll", "cudnn64_9.dll")
        missing = []
        loader = ctypes.WinDLL if hasattr(ctypes, "WinDLL") else ctypes.CDLL
        for dll_name in required:
            try:
                loader(dll_name)
            except OSError:
                missing.append(dll_name)
        return missing

    def _load_model(self, device, compute_type, model_size):
        self.model = WhisperModel(
            model_size_or_path=model_size,
            device=device,
            compute_type=compute_type,
        )
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._set_transcribe_signature_flags()

    def _load_model_with_fallback(self):
        missing_runtime = self._check_cuda_runtime()
        if missing_runtime:
            print(
                "[SimpleSpeech] CUDA runtime missing "
                f"({', '.join(missing_runtime)}). Falling back to CPU."
            )
            self._load_model(
                device="cpu",
                compute_type="int8",
                model_size=self._cpu_model_size,
            )
            print(f"Model loaded into CPU ({self._model_size}).")
            return

        try:
            self._load_model(
                device="cuda",
                compute_type="int8_float16",
                model_size=self._gpu_model_size,
            )
            print(f"Model loaded into GPU ({self._model_size}).")
        except Exception as exc:
            print(f"[SimpleSpeech] GPU init failed ({exc}). Falling back to CPU.")
            self._load_model(
                device="cpu",
                compute_type="int8",
                model_size=self._cpu_model_size,
            )
            print(f"Model loaded into CPU ({self._model_size}).")

    def _fallback_to_cpu(self):
        if self._device == "cpu":
            return
        self._load_model(
            device="cpu",
            compute_type="int8",
            model_size=self._cpu_model_size,
        )
        print("[SimpleSpeech] Switched transcription backend to CPU.")

    def _build_transcribe_kwargs(self):
        kwargs = {
            "beam_size": 1,
            "language": "en",
            "condition_on_previous_text": False,
            "vad_filter": self._vad_filter,
        }

        if self._supports_chunk_length_s:
            kwargs["chunk_length_s"] = 30
        elif self._supports_chunk_length:
            kwargs["chunk_length"] = 30

        if self._prefer_speed:
            if self._supports_best_of:
                kwargs["best_of"] = 1
            if self._supports_without_timestamps:
                kwargs["without_timestamps"] = True

        return kwargs

    def _transcribe_once(self, audio_path, kwargs):
        segments, _ = self.model.transcribe(audio_path, **kwargs)
        # Consume the iterator here so runtime/provider errors are caught at this layer.
        return " ".join(segment.text for segment in segments).strip()

    def transcribe(self, audio_path):
        start = time.time()
        kwargs = self._build_transcribe_kwargs()

        try:
            output_string = self._transcribe_once(audio_path, kwargs)
        except Exception as exc:
            if self._device == "cuda" and self._is_cuda_runtime_error(exc):
                print(f"[SimpleSpeech] GPU transcription failed ({exc}). Retrying on CPU.")
                self._fallback_to_cpu()
                kwargs = self._build_transcribe_kwargs()
                output_string = self._transcribe_once(audio_path, kwargs)
            else:
                raise

        duration = time.time() - start
        return output_string, round(duration, 2)
