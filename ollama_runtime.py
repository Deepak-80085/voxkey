"""Download Ollama's Windows release once, only for the CUDA libraries Whisper loads from it.

VoxKey no longer runs Ollama. faster-whisper needs cuBLAS on the GPU and this verified
archive is where it comes from (see speech_models._configure_cuda_runtime_search_path).
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path


OLLAMA_VERSION = "v0.32.0"
OLLAMA_URL = (
    f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/"
    "ollama-windows-amd64.zip"
)
OLLAMA_SHA256 = "56561a8f0a904483303c610e61af61c5a7b6f5496ce3707e207d25d4ff67b89e"


class ManagedOllamaRuntime:
    def __init__(
        self,
        runtime,
        download=urllib.request.urlopen,
        expected_sha256=OLLAMA_SHA256,
    ):
        self.runtime = runtime
        self.download = download
        self.expected_sha256 = expected_sha256

    def executable_path(self) -> Path:
        return self.runtime.runtime_dir() / "ollama" / "ollama.exe"

    def is_installed(self) -> bool:
        marker = self.executable_path().parent / ".voxkey-version"
        try:
            return self.executable_path().is_file() and marker.read_text(encoding="ascii") == OLLAMA_VERSION
        except OSError:
            return False

    def install(self, progress=None) -> None:
        report = progress or (lambda _detail: None)
        root = self.runtime.runtime_dir()
        root.mkdir(parents=True, exist_ok=True)
        archive = root / f"ollama-{OLLAMA_VERSION}.zip.part"
        staging = root / "ollama.installing"
        target = root / "ollama"
        digest = hashlib.sha256()
        existing = archive.stat().st_size if archive.exists() else 0
        request = (
            urllib.request.Request(OLLAMA_URL, headers={"Range": f"bytes={existing}-"})
            if existing
            else OLLAMA_URL
        )
        download_complete = False

        try:
            with self.download(request) as response:
                resumed = bool(existing and getattr(response, "status", 200) == 206)
                if resumed:
                    with archive.open("rb") as partial:
                        while chunk := partial.read(1024 * 1024):
                            digest.update(chunk)
                else:
                    existing = 0
                total = existing + int(response.headers.get("Content-Length", 0))
                downloaded = existing
                last_percent = -1
                with archive.open("ab" if resumed else "wb") as destination:
                    while chunk := response.read(1024 * 1024):
                        destination.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if total:
                            percent = min(100, downloaded * 100 // total)
                            if percent != last_percent:
                                report(f"Downloading GPU speech runtime: {percent}%")
                                last_percent = percent
            download_complete = True
            report("Verifying GPU speech runtime...")
            if digest.hexdigest().lower() != self.expected_sha256.lower():
                raise RuntimeError("Downloaded Ollama runtime failed SHA-256 verification")

            report("Installing GPU speech runtime...")
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            staging_root = staging.resolve()
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    destination = (staging / member.filename).resolve()
                    if destination != staging_root and staging_root not in destination.parents:
                        raise RuntimeError("Ollama archive contains an unsafe path")
                bundle.extractall(staging)
            if not (staging / "ollama.exe").is_file():
                raise RuntimeError("Ollama archive does not contain ollama.exe")
            (staging / ".voxkey-version").write_text(OLLAMA_VERSION, encoding="ascii")
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
        finally:
            if download_complete:
                archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging)

    def ensure_ready(self, progress=None) -> None:
        if not self.is_installed():
            self.install(progress)
