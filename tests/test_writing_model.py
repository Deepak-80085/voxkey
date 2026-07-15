import tempfile
import unittest
from unittest.mock import Mock, patch

from writing_model import WritingModelClient, WritingModelUnavailable


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class WritingModelTests(unittest.TestCase):
    def test_unavailable_ollama_never_becomes_a_raw_text_fallback(self):
        request = Mock(side_effect=ConnectionError("offline"))
        client = WritingModelClient("test-model", request=request)

        self.assertFalse(client.health_check().ready)
        with self.assertRaises(WritingModelUnavailable):
            client.polish("hello world")

    def test_health_check_requires_selected_local_model(self):
        request = Mock(return_value=FakeResponse({"models": [{"name": "other"}]}))
        client = WritingModelClient("test-model", request=request)

        status = client.health_check()

        self.assertFalse(status.ready)
        self.assertIn("test-model", status.reason)

    def test_polish_uses_preservation_prompt_and_returns_only_polished_text(self):
        request = Mock(return_value=FakeResponse({"response": "Hello, Zudio."}))
        client = WritingModelClient("test-model", request=request)

        self.assertEqual(client.polish("hello zudio"), "Hello, Zudio.")
        payload = request.call_args.kwargs["json"]
        self.assertIn("Preserve names, numbers, facts, and meaning", payload["prompt"])
        self.assertTrue(payload["stream"] is False)
        self.assertFalse(payload["think"])
        self.assertEqual(payload["keep_alive"], "24h")
        self.assertEqual(payload["options"]["num_predict"], 120)

    def test_empty_writer_output_is_unavailable_not_raw_text(self):
        request = Mock(return_value=FakeResponse({"response": "   "}))
        client = WritingModelClient("test-model", request=request)

        with self.assertRaises(WritingModelUnavailable):
            client.polish("hello")

    def test_repair_pulls_missing_model_with_local_ollama_cli(self):
        request = Mock(
            side_effect=[
                FakeResponse({"models": []}),
                FakeResponse({"models": [{"name": "test-model"}]}),
            ]
        )
        run = Mock()
        client = WritingModelClient(
            "test-model",
            request=request,
            run=run,
            which=Mock(return_value="ollama.exe"),
        )

        status = client.repair()

        self.assertTrue(status.ready)
        self.assertEqual(run.call_args.args[0], ["ollama.exe", "pull", "test-model"])

    def test_repair_does_not_pull_when_model_is_already_available(self):
        run = Mock()
        client = WritingModelClient(
            "test-model",
            request=Mock(return_value=FakeResponse({"models": [{"name": "test-model"}]})),
            run=run,
            which=Mock(return_value="ollama.exe"),
        )

        self.assertTrue(client.repair().ready)
        run.assert_not_called()

    def test_repair_explains_when_ollama_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"LOCALAPPDATA": temp_dir}, clear=False):
                client = WritingModelClient(
                    "test-model",
                    request=Mock(return_value=FakeResponse({"models": []})),
                    which=Mock(return_value=None),
                )

                status = client.repair()

        self.assertFalse(status.ready)
        self.assertIn("Install Ollama", status.reason)


if __name__ == "__main__":
    unittest.main()
