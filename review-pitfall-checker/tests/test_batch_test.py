import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class BatchTestScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.post_calls = []
        requests_module = types.ModuleType("requests")

        def post(url, json=None, timeout=None):
            self.post_calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse(
                {
                    "recommendation": "NOT",
                    "fatal_risks": [{"title": "明显质量风险"}],
                }
            )

        requests_module.post = post
        self.old_requests = sys.modules.get("requests")
        sys.modules["requests"] = requests_module
        sys.modules.pop("scripts.batch_test", None)

    def tearDown(self) -> None:
        if self.old_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = self.old_requests
        sys.modules.pop("scripts.batch_test", None)

    def test_runs_cases_saves_results_and_prints_summary(self) -> None:
        module = importlib.import_module("scripts.batch_test")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            review_file = data_dir / "case1.txt"
            review_file.write_text("质量不好\n售后慢", encoding="utf-8")
            cases_file = data_dir / "test_cases.json"
            cases_file.write_text(
                json.dumps(
                    [
                        {
                            "product_id": "sku-1",
                            "reviews_file": "data/case1.txt",
                            "scenario": "老人使用",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("builtins.print") as mocked_print:
                module.run_batch(root_dir=root)

            result_file = data_dir / "results" / "sku-1.json"
            self.assertTrue(result_file.exists())
            self.assertEqual(json.loads(result_file.read_text(encoding="utf-8"))["recommendation"], "NOT")

        self.assertEqual(self.post_calls[0]["url"], "http://localhost:8000/analyze")
        self.assertEqual(self.post_calls[0]["json"]["reviews"], "质量不好\n售后慢")
        printed = "\n".join(str(call.args[0]) for call in mocked_print.call_args_list)
        self.assertIn("sku-1", printed)
        self.assertIn("NOT", printed)
        self.assertIn("1", printed)


if __name__ == "__main__":
    unittest.main()
