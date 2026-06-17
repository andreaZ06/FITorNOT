import importlib
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def post(self, path):
        def decorator(func):
            return func

        return decorator


class FakeBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MainAnalyzeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_fastapi = sys.modules.get("fastapi")
        self.old_pydantic = sys.modules.get("pydantic")
        self.old_dify = sys.modules.get("scripts.call_dify_workflow")
        self.calls = []

        fastapi_module = types.ModuleType("fastapi")
        fastapi_module.FastAPI = FakeFastAPI
        fastapi_module.HTTPException = FakeHTTPException
        pydantic_module = types.ModuleType("pydantic")
        pydantic_module.BaseModel = FakeBaseModel

        dify_module = types.ModuleType("scripts.call_dify_workflow")

        class DifyWorkflowError(RuntimeError):
            def __init__(self, message, status_code=None, response_body=None):
                self.status_code = status_code
                self.response_body = response_body
                super().__init__(message)

        def run_dify_workflow(**kwargs):
            self.calls.append(kwargs)
            return {"recommendation": "FIT", "fatal_risks": []}

        dify_module.DifyWorkflowError = DifyWorkflowError
        dify_module.run_dify_workflow = run_dify_workflow

        sys.modules["fastapi"] = fastapi_module
        sys.modules["pydantic"] = pydantic_module
        sys.modules["scripts.call_dify_workflow"] = dify_module
        sys.modules.pop("app.main", None)

    def tearDown(self) -> None:
        for name, old_module in (
            ("fastapi", self.old_fastapi),
            ("pydantic", self.old_pydantic),
            ("scripts.call_dify_workflow", self.old_dify),
        ):
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module
        sys.modules.pop("app.main", None)

    def test_analyze_returns_outputs_unchanged_after_lightweight_cleaning(self) -> None:
        module = importlib.import_module("app.main")
        request = module.AnalyzeRequest(
            product_id="sku-1",
            reviews="质量不好\n😀😀\n售后慢",
            user_scenario="老人使用",
        )

        result = module.analyze(request)

        self.assertEqual(result, {"recommendation": "FIT", "fatal_risks": []})
        self.assertEqual(
            self.calls[0],
            {
                "reviews_text": "质量不好\n售后慢",
                "user_scenario": "老人使用",
                "user_id": "sku-1",
            },
        )

    def test_analyze_maps_dify_errors_to_502(self) -> None:
        module = importlib.import_module("app.main")

        def fail(**kwargs):
            raise module.DifyWorkflowError("上游失败", 500, "bad gateway")

        module.run_dify_workflow = fail
        request = module.AnalyzeRequest(
            product_id="sku-1",
            reviews="质量不好",
            user_scenario=None,
        )

        with self.assertRaises(FakeHTTPException) as context:
            module.analyze(request)

        self.assertEqual(context.exception.status_code, 502)
        self.assertEqual(context.exception.detail["dify_status_code"], 500)
        self.assertEqual(context.exception.detail["dify_response_body"], "bad gateway")


if __name__ == "__main__":
    unittest.main()
