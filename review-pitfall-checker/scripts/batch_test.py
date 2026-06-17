"""批量调用本地 /analyze 接口，方便快速扫 FITorNOT 分析结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


def load_test_cases(path: Path) -> list[dict[str, Any]]:
    """读取 data/test_cases.json。"""

    return json.loads(path.read_text(encoding="utf-8"))


def call_analyze(
    base_url: str,
    product_id: str,
    reviews_text: str,
    scenario: str,
) -> dict[str, Any]:
    """调用本地 FastAPI /analyze 接口。"""

    response = requests.post(
        f"{base_url.rstrip('/')}/analyze",
        json={
            "product_id": product_id,
            "reviews": reviews_text,
            "user_scenario": scenario,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def summarize_result(product_id: str, result: dict[str, Any]) -> str:
    """生成一行便于肉眼扫读的汇总。"""

    recommendation = result.get("recommendation", "")
    fatal_risks = result.get("fatal_risks") or []
    fatal_count = len(fatal_risks) if isinstance(fatal_risks, list) else 0
    return f"{product_id}\t{recommendation}\t{fatal_count}"


def run_batch(
    root_dir: str | Path = ".",
    base_url: str = "http://localhost:8000",
) -> list[dict[str, Any]]:
    """读取测试用例，逐个调用 /analyze，并把结果写入 data/results。"""

    root = Path(root_dir)
    data_dir = root / "data"
    cases = load_test_cases(data_dir / "test_cases.json")
    results_dir = data_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    saved_results: list[dict[str, Any]] = []
    print("product_id\trecommendation\tfatal_risks")

    for case in cases:
        product_id = str(case["product_id"])
        reviews_file = root / str(case["reviews_file"])
        reviews_text = reviews_file.read_text(encoding="utf-8")
        scenario = str(case.get("scenario", ""))
        result = call_analyze(base_url, product_id, reviews_text, scenario)

        output_path = results_dir / f"{product_id}.json"
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        saved_results.append(result)
        print(summarize_result(product_id, result))

    return saved_results


def main() -> None:
    parser = argparse.ArgumentParser(description="批量测试 FITorNOT 本地分析接口")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    run_batch(root_dir=args.root_dir, base_url=args.base_url)


if __name__ == "__main__":
    main()
