import unittest
from unittest.mock import Mock

from writing_model import WritingModelClient, WritingModelUnavailable


class FakeResponse:
    def __init__(self, payload, lines=()):
        self.payload = payload
        self.lines = lines

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_lines(self):
        return iter(self.lines)


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
        self.assertEqual(request.call_args.kwargs["timeout"], 300)

    def test_empty_writer_output_is_unavailable_not_raw_text(self):
        request = Mock(return_value=FakeResponse({"response": "   "}))
        client = WritingModelClient("test-model", request=request)

        with self.assertRaises(WritingModelUnavailable):
            client.polish("hello")

    def test_repair_warms_an_available_model_before_reporting_ready(self):
        request = Mock(return_value=FakeResponse({"models": [{"name": "test-model"}]}))
        post = Mock(return_value=FakeResponse({"response": "ready"}))
        progress = []
        client = WritingModelClient(
            "test-model",
            request=request,
            post=post,
            runtime_manager=Mock(),
        )

        status = client.repair(progress.append)

        self.assertTrue(status.ready)
        self.assertTrue(post.call_args.args[0].endswith("/api/generate"))
        self.assertEqual(post.call_args.kwargs["timeout"], 300)
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 1)
        self.assertTrue(any("Loading local writing model" in detail for detail in progress))

    def test_repair_starts_managed_runtime_and_pulls_missing_model(self):
        request = Mock(
            side_effect=[
                FakeResponse({"models": []}),
                FakeResponse({"models": []}),
                FakeResponse({"models": [{"name": "test-model"}]}),
            ]
        )
        post = Mock(
            return_value=FakeResponse(
                {"status": "success"},
                [b'{"status":"downloading","completed":5,"total":10}', b'{"status":"success"}'],
            )
        )
        runtime_manager = Mock()
        client = WritingModelClient(
            "test-model",
            request=request,
            post=post,
            runtime_manager=runtime_manager,
        )

        progress = []
        status = client.repair(progress.append)

        self.assertTrue(status.ready)
        runtime_manager.ensure_ready.assert_called_once()
        pull = post.call_args_list[0]
        self.assertTrue(pull.args[0].endswith('/api/pull'))
        self.assertEqual(pull.kwargs['json'], {'model': 'test-model', 'stream': True})
        self.assertTrue(post.call_args_list[-1].args[0].endswith('/api/generate'))
        self.assertTrue(any('50%' in detail for detail in progress))

    def test_repair_does_not_pull_when_model_is_already_available(self):
        runtime_manager = Mock()
        client = WritingModelClient(
            "test-model",
            request=Mock(return_value=FakeResponse({"models": [{"name": "test-model"}]})),
            runtime_manager=runtime_manager,
        )

        self.assertTrue(client.repair().ready)
        runtime_manager.ensure_ready.assert_not_called()

    def test_repair_rechecks_model_after_starting_managed_runtime(self):
        request = Mock(
            side_effect=[
                ConnectionError('runtime stopped'),
                FakeResponse({'models': [{'name': 'test-model'}]}),
            ]
        )
        post = Mock()
        runtime_manager = Mock()
        client = WritingModelClient(
            'test-model',
            request=request,
            post=post,
            runtime_manager=runtime_manager,
        )

        self.assertTrue(client.repair().ready)

        runtime_manager.ensure_ready.assert_called_once()
        self.assertTrue(post.call_args.args[0].endswith('/api/generate'))

    def test_repair_explains_when_managed_runtime_install_fails(self):
        runtime_manager = Mock()
        runtime_manager.ensure_ready.side_effect = RuntimeError('download failed')
        client = WritingModelClient(
            "test-model",
            request=Mock(return_value=FakeResponse({"models": []})),
            runtime_manager=runtime_manager,
        )

        status = client.repair()

        self.assertFalse(status.ready)
        self.assertIn("runtime", status.reason.lower())


if __name__ == "__main__":
    unittest.main()
