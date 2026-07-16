"""VoxKey-owned portable Ollama runtime for Windows."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

import requests


OLLAMA_VERSION = "v0.32.0"
OLLAMA_URL = (
    f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/"
    "ollama-windows-amd64.zip"
)
OLLAMA_SHA256 = "56561a8f0a904483303c610e61af61c5a7b6f5496ce3707e207d25d4ff67b89e"
OLLAMA_HOST = "127.0.0.1:11435"


class ManagedOllamaRuntime:
    def __init__(
        self,
        runtime,
        download=urllib.request.urlopen,
        request=requests.get,
        popen=subprocess.Popen,
        sleep=time.sleep,
        expected_sha256=OLLAMA_SHA256,
    ):
        self.runtime = runtime
        self.download = download
        self.request = request
        self.popen = popen
        self.sleep = sleep
        self.expected_sha256 = expected_sha256
        self.process = None

    @property
    def base_url(self) -> str:
        return f"http://{OLLAMA_HOST}"

    def executable_path(self) -> Path:
        return self.runtime.runtime_dir() / "ollama" / "ollama.exe"

    def is_installed(self) -> bool:
        marker = self.executable_path().parent / ".voxkey-version"
        try:
            return self.executable_path().is_file() and marker.read_text(encoding="ascii") == OLLAMA_VERSION
        except OSError:
            return False

    def models_dir(self) -> Path:
        path = self.runtime.models_dir() / "writer"
        path.mkdir(parents=True, exist_ok=True)
        return path

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
                                report(f"Downloading local writer runtime: {percent}%")
                                last_percent = percent
            download_complete = True
            report("Verifying local writer runtime...")
            if digest.hexdigest().lower() != self.expected_sha256.lower():
                raise RuntimeError("Downloaded Ollama runtime failed SHA-256 verification")

            report("Installing local writer runtime...")
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

    def _healthy(self) -> bool:
        try:
            response = self.request(f"{self.base_url}/api/tags", timeout=1)
            response.raise_for_status()
            return True
        except Exception:
            return False

    def ensure_ready(self, progress=None) -> None:
        if not self.is_installed():
            self.install(progress)
        if progress:
            progress("Starting local writer runtime...")
        self.start()

    def start(self) -> None:
        if self._healthy():
            return
        executable = self.executable_path()
        if not executable.is_file():
            raise RuntimeError("VoxKey Ollama runtime is not installed")
        environment = os.environ.copy()
        environment["OLLAMA_HOST"] = OLLAMA_HOST
        environment["OLLAMA_MODELS"] = str(self.models_dir())
        self.process = self.popen(
            [str(executable), "serve"],
            cwd=str(executable.parent),
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _attempt in range(60):
            if self._healthy():
                return
            self.sleep(0.25)
        self.stop()
        raise RuntimeError("VoxKey Ollama runtime did not start")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
