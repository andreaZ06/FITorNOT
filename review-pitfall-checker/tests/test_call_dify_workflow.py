import importlib
import os
import sys
import types
import unittest


PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class CallDifyWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = os.environ.copy()
        self.post_calls = []

        requests_module = types.ModuleType("requests")

        class RequestException(Exception):
            pass

        requests_module.RequestException = RequestException

        def post(url, headers=None, json=None, timeout=None):
            self.post_calls.append(
                {"url": url, "headers": headers, "json": json, "timeout": timeout}
            )
            return FakeResponse(
                200,
                {
                    "data": {
                        "outputs": {
                            "recommendation": "NOT",
                            "fatal_risks": [{"title": "售后风险"}],
                        }
                    }
                },
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

    def test_posts_to_workflows_run_and_returns_outputs(self) -> None:
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
        self.assertEqual(call["timeout"], 90)
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(
            call["json"],
            {
                "inputs": {
                    "reviews": "差评文本",
                    "user_scenario": "老人使用",
                },
                "response_mode": "blocking",
                "user": "user-123",
            },
        )

    def test_raises_error_with_status_and_body_after_retries(self) -> None:
        os.environ["DIFY_API_KEY"] = "test-key"

        def failing_post(url, headers=None, json=None, timeout=None):
            self.post_calls.append({"url": url})
            return FakeResponse(500, {"error": "bad"}, text="server exploded")

        sys.modules["requests"].post = failing_post
        module = importlib.import_module("scripts.call_dify_workflow")

        with patch_time_sleep(module), self.assertRaises(module.DifyWorkflowError) as context:
            module.run_dify_workflow("差评文本")

        self.assertEqual(len(self.post_calls), 3)
        message = str(context.exception)
        self.assertIn("status_code=500", message)
        self.assertIn("server exploded", message)


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
