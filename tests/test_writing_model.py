import unittest
from unittest.mock import Mock

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
        self.assertEqual(payload["options"]["num_predict"], 120)

    def test_empty_writer_output_is_unavailable_not_raw_text(self):
        request = Mock(return_value=FakeResponse({"response": "   "}))
        client = WritingModelClient("test-model", request=request)

        with self.assertRaises(WritingModelUnavailable):
            client.polish("hello")


if __name__ == "__main__":
    unittest.main()
