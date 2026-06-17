"""模型评估脚本。

读取人工标注样本，跑清洗 + Dify 分析 pipeline，输出：
- L1/L2/L3 各等级准确率
- 混淆矩阵
- 不一致 case，便于复盘 prompt 或人工标注口径
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.call_dify_workflow import run_dify_workflow
from scripts.clean_reviews import clean_reviews_from_csv


RISK_LEVELS = ("L1", "L2", "L3")


def load_labels(path: str | Path) -> dict[str, str]:
    """读取人工标注 risk_level。"""

    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        return {
            row["review_id"]: row["human_risk_level"]
            for row in csv.DictReader(file)
            if row.get("review_id") and row.get("human_risk_level")
        }


def build_confusion_matrix(
    labels: dict[str, str], predictions: list[dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """生成 human_risk_level x model_risk_level 的混淆矩阵。"""

    prediction_map = {
        item.get("review_id"): item.get("risk_level", "") for item in predictions
    }
    matrix: dict[str, dict[str, int]] = {
        level: {predicted: 0 for predicted in RISK_LEVELS} for level in RISK_LEVELS
    }

    for review_id, human_level in labels.items():
        predicted_level = prediction_map.get(review_id, "")
        if human_level in matrix and predicted_level in matrix[human_level]:
            matrix[human_level][predicted_level] += 1

    return matrix


def format_reviews_for_workflow(reviews: list[dict[str, Any]]) -> str:
    """把结构化评论转成传给 Dify 的文本。"""

    return "\n".join(
        f"{item['review_id']}: {item['text']} "
        f"(rating={item['rating']}, useful_count={item['useful_count']})"
        for item in reviews
    )


def extract_predictions(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    """从 Dify outputs 中提取预测列表。"""

    raw_results = (
        outputs.get("results")
        or outputs.get("analysis_results")
        or outputs.get("items")
        or []
    )
    if isinstance(raw_results, dict):
        raw_results = [raw_results]
    if not isinstance(raw_results, list):
        return []
    return [item for item in raw_results if isinstance(item, dict)]


def calculate_accuracy_by_level(
    labels: dict[str, str], predictions: list[dict[str, Any]]
) -> dict[str, float]:
    """计算每个风险等级的准确率。"""

    prediction_map = {
        item.get("review_id"): item.get("risk_level", "") for item in predictions
    }
    totals: dict[str, int] = defaultdict(int)
    correct: dict[str, int] = defaultdict(int)

    for review_id, human_level in labels.items():
        totals[human_level] += 1
        if prediction_map.get(review_id) == human_level:
            correct[human_level] += 1

    return {
        level: (correct[level] / totals[level] if totals[level] else 0.0)
        for level in RISK_LEVELS
    }


def print_mismatches(labels: dict[str, str], predictions: list[dict[str, Any]]) -> None:
    """打印模型输出和人工标注不一致的样本。"""

    prediction_map = {item.get("review_id"): item for item in predictions}
    for review_id, human_level in labels.items():
        predicted = prediction_map.get(review_id, {})
        predicted_level = predicted.get("risk_level", "")
        if predicted_level != human_level:
            print(
                f"[不一致] review_id={review_id} "
                f"human={human_level} model={predicted_level} "
                f"reason={predicted.get('reason', '')}"
            )


def evaluate(
    reviews_csv: str | Path,
    labels_csv: str | Path,
    user_scenario: str,
    product_id: str = "",
) -> None:
    """运行完整评估流程并打印结果。"""

    reviews = clean_reviews_from_csv(reviews_csv)
    labels = load_labels(labels_csv)
    outputs = run_dify_workflow(
        format_reviews_for_workflow(reviews),
        user_scenario=user_scenario,
        user_id=product_id or "evaluate",
    )
    predictions = extract_predictions(outputs)

    accuracy = calculate_accuracy_by_level(labels, predictions)
    matrix = build_confusion_matrix(labels, predictions)

    print("各风险等级准确率:")
    for level in RISK_LEVELS:
        print(f"- {level}: {accuracy[level]:.2%}")

    print("\n混淆矩阵 human -> model:")
    print(matrix)

    print("\n不一致 case:")
    print_mismatches(labels, predictions)


def main() -> None:
    parser = argparse.ArgumentParser(description="评估避坑评价分析模型效果")
    parser.add_argument("--reviews", default="data/sample_reviews.csv")
    parser.add_argument("--labels", default="data/labeled_sample.csv")
    parser.add_argument("--scenario", required=True, help="用户使用场景")
    parser.add_argument("--product-id", default="", help="商品 ID")
    args = parser.parse_args()

    evaluate(args.reviews, args.labels, args.scenario, args.product_id)


if __name__ == "__main__":
    main()
