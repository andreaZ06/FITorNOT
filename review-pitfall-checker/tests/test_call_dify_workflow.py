import importlib
import os
import sys
import types
import unittest


PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, lines=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self.text = text

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            if decode_unicode and isinstance(line, bytes):
                yield line.decode("utf-8")
            else:
                yield line


class CallDifyWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = os.environ.copy()
        self.post_calls = []

        requests_module = types.ModuleType("requests")

        class RequestException(Exception):
            pass

        requests_module.RequestException = RequestException

        def post(url, headers=None, json=None, timeout=None, stream=False):
            self.post_calls.append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "timeout": timeout,
                    "stream": stream,
                }
            )
            return FakeResponse(
                200,
                [
                    "",
                    'data: {"event": "node_started", "data": {"node_id": "1"}}',
                    'data: {"event": "workflow_finished", "data": {"outputs": {"recommendation": "NOT", "fatal_risks": [{"title": "售后风险"}]}}}',
                ],
            )

        requests_module.post = post
        dotenv_module = types.ModuleType("dotenv")
        dotenv_module.load_dotenv = lambda: None

        self.old_requests = sys.modules.get("requests")
        self.old_dotenv = sys.modules.get("dotenv")
        sys.modules["requests"] = requests_module
        sys.modules["dotenv"] = dotenv_module
        sys.modules.pop("scripts.call_dify_workflow", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.original_env)
        if self.old_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = self.old_requests
        if self.old_dotenv is None:
            sys.modules.pop("dotenv", None)
        else:
            sys.modules["dotenv"] = self.old_dotenv
        sys.modules.pop("scripts.call_dify_workflow", None)

    def test_streams_workflow_and_returns_workflow_finished_outputs(self) -> None:
        os.environ["DIFY_API_KEY"] = "test-key"
        os.environ["DIFY_BASE_URL"] = "https://dify.example/v1/"
        module = importlib.import_module("scripts.call_dify_workflow")

        result = module.run_dify_workflow(
            "差评文本", user_scenario="老人使用", user_id="user-123"
        )

        self.assertEqual(
            result,
            {
                "recommendation": "NOT",
                "fatal_risks": [{"title": "售后风险"}],
            },
        )
        self.assertEqual(len(self.post_calls), 1)
        call = self.post_calls[0]
        self.assertEqual(call["url"], "https://dify.example/v1/workflows/run")
        self.assertEqual(call["timeout"], 180)
        self.assertTrue(call["stream"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(
            call["json"],
            {
                "inputs": {
                    "reviews": "差评文本",
                    "user_scenario": "老人使用",
                },
                "response_mode": "streaming",
                "user": "user-123",
            },
        )

    def test_raises_error_event_with_recent_events(self) -> None:
        os.environ["DIFY_API_KEY"] = "test-key"

        def post(url, headers=None, json=None, timeout=None, stream=False):
            self.post_calls.append({"url": url})
            return FakeResponse(
                200,
                [
                    'data: {"event": "node_started", "data": {"node_id": "1"}}',
                    'data: {"event": "error", "message": "workflow failed", "code": "provider_error"}',
                ],
            )

        sys.modules["requests"].post = post
        module = importlib.import_module("scripts.call_dify_workflow")

        with self.assertRaises(module.DifyWorkflowError) as context:
            module.run_dify_workflow("差评文本")

        message = str(context.exception)
        self.assertIn("workflow failed", message)
        self.assertIn("node_started", message)

    def test_retries_connection_failures_only(self) -> None:
        os.environ["DIFY_API_KEY"] = "test-key"
        attempts = {"count": 0}

        def post(url, headers=None, json=None, timeout=None, stream=False):
            attempts["count"] += 1
            self.post_calls.append({"url": url})
            if attempts["count"] < 3:
                raise sys.modules["requests"].RequestException("connect failed")
            return FakeResponse(
                200,
                [
                    'data: {"event": "workflow_finished", "data": {"outputs": {"recommendation": "FIT"}}}',
                ],
            )

        sys.modules["requests"].post = post
        module = importlib.import_module("scripts.call_dify_workflow")

        with patch_time_sleep(module):
            result = module.run_dify_workflow("差评文本")

        self.assertEqual(result, {"recommendation": "FIT"})
        self.assertEqual(len(self.post_calls), 3)


class patch_time_sleep:
    def __init__(self, module):
        self.module = module
        self.original_sleep = module.time.sleep

    def __enter__(self):
        self.module.time.sleep = lambda seconds: None

    def __exit__(self, exc_type, exc, tb):
        self.module.time.sleep = self.original_sleep


if __name__ == "__main__":
    unittest.main()
