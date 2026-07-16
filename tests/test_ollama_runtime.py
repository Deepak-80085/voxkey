import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from ollama_runtime import ManagedOllamaRuntime, OLLAMA_SHA256
from voxkey_runtime import VoxKeyRuntime


class FakeDownload:
    def __init__(self, payload, status=200):
        self.payload = io.BytesIO(payload)
        self.headers = {'Content-Length': str(len(payload))}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self.payload.read(size)


class OllamaRuntimeTests(unittest.TestCase):
    def test_install_verifies_and_extracts_portable_runtime(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('ollama.exe', b'portable ollama')
        payload = archive.getvalue()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Mock(spec=VoxKeyRuntime)
            runtime.runtime_dir.return_value = Path(temp_dir) / 'runtime'
            runtime.models_dir.return_value = Path(temp_dir) / 'models'
            manager = ManagedOllamaRuntime(
                runtime,
                download=Mock(return_value=FakeDownload(payload)),
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )
            progress = []

            manager.install(progress.append)

            self.assertEqual(manager.executable_path().read_bytes(), b'portable ollama')
            self.assertTrue(manager.is_installed())
            self.assertEqual(
                (manager.executable_path().parent / '.voxkey-version').read_text(),
                'v0.32.0',
            )
            self.assertTrue(any('100%' in detail for detail in progress))

    def test_start_uses_private_host_and_voxkey_model_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Mock(spec=VoxKeyRuntime)
            runtime.runtime_dir.return_value = Path(temp_dir) / 'runtime'
            runtime.models_dir.return_value = Path(temp_dir) / 'models'
            executable = runtime.runtime_dir.return_value / 'ollama' / 'ollama.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'ollama')
            response = Mock()
            response.raise_for_status.return_value = None
            request = Mock(side_effect=[ConnectionError('offline'), response])
            popen = Mock()
            manager = ManagedOllamaRuntime(
                runtime,
                request=request,
                popen=popen,
                sleep=Mock(),
            )

            manager.start()

            environment = popen.call_args.kwargs['env']
            self.assertEqual(environment['OLLAMA_HOST'], '127.0.0.1:11435')
            self.assertEqual(environment['OLLAMA_MODELS'], str(Path(temp_dir) / 'models' / 'writer'))
            self.assertEqual(popen.call_args.args[0], [str(executable), 'serve'])

    def test_install_resumes_partial_runtime_download(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('ollama.exe', b'portable ollama')
        payload = archive.getvalue()
        split = len(payload) // 2

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Mock(spec=VoxKeyRuntime)
            runtime.runtime_dir.return_value = Path(temp_dir) / 'runtime'
            runtime.models_dir.return_value = Path(temp_dir) / 'models'
            runtime.runtime_dir.return_value.mkdir(parents=True)
            partial = runtime.runtime_dir.return_value / 'ollama-v0.32.0.zip.part'
            partial.write_bytes(payload[:split])
            download = Mock(return_value=FakeDownload(payload[split:], status=206))
            manager = ManagedOllamaRuntime(
                runtime,
                download=download,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
            )

            manager.install()

            request = download.call_args.args[0]
            self.assertEqual(request.headers['Range'], f'bytes={split}-')
            self.assertTrue(manager.executable_path().is_file())

    def test_official_runtime_checksum_is_pinned(self):
        self.assertEqual(
            OLLAMA_SHA256,
            '56561a8f0a904483303c610e61af61c5a7b6f5496ce3707e207d25d4ff67b89e',
        )

    def test_ensure_ready_installs_missing_runtime_before_start(self):
        runtime = Mock(spec=VoxKeyRuntime)
        runtime.runtime_dir.return_value = Path('runtime')
        runtime.models_dir.return_value = Path('models')
        manager = ManagedOllamaRuntime(runtime)
        manager.install = Mock()
        manager.start = Mock()
        manager.is_installed = Mock(return_value=False)

        manager.ensure_ready()

        manager.install.assert_called_once_with(None)
        manager.start.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
