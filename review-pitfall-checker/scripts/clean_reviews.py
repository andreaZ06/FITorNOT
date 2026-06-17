"""评论清洗脚本。

职责：
- 读取手动导出的评论 CSV。
- 过滤过短评论和疑似水军/广告话术。
- 按 review_id 去重，并输出结构化评论列表。
"""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from pathlib import Path
from typing import Any


AD_KEYWORDS = (
    "商家发的红包",
    "好评返现",
    "返现",
    "红包",
    "五星好评",
    "刷单",
    "加微信",
)


def normalize_text(text: str) -> str:
    """压缩首尾空白，避免同一条评论因为复制空格造成误判。"""

    return (text or "").strip()


def has_meaningful_text(line: str) -> bool:
    """判断一行是否包含字母、数字或中文等可分析文本。"""

    return any(
        unicodedata.category(char).startswith(("L", "N")) for char in line.strip()
    )


def lightweight_clean_reviews_text(reviews_text: str) -> str:
    """轻量程序化预处理评论文本。

    这里只做格式级清理：去掉空白行和纯表情/符号行。
    不做语义判断，不过滤“好评返现”等内容，这些交给 Dify 内部节点处理。
    """

    lines: list[str] = []
    for raw_line in (reviews_text or "").splitlines():
        line = raw_line.strip()
        if not line or not has_meaningful_text(line):
            continue
        lines.append(line)

    return "\n".join(lines)


def is_noise_review(text: str) -> bool:
    """判断是否为过短评论或疑似广告/水军评论。"""

    normalized = normalize_text(text)
    if len(normalized) < 5:
        return True
    return any(keyword in normalized for keyword in AD_KEYWORDS)


def parse_int(value: Any, default: int = 0) -> int:
    """把 CSV 里的数字字段转成 int，空值或异常值按默认值处理。"""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗评论行，保留每个 review_id 第一次出现的有效评论。"""

    cleaned: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row in rows:
        review_id = normalize_text(str(row.get("review_id", "")))
        text = normalize_text(str(row.get("text", "")))

        if not review_id or review_id in seen_ids or is_noise_review(text):
            continue

        seen_ids.add(review_id)
        cleaned.append(
            {
                "review_id": review_id,
                "text": text,
                "rating": parse_int(row.get("rating")),
                "useful_count": parse_int(row.get("useful_count")),
            }
        )

    return cleaned


def clean_reviews_from_csv(
    input_path: str | Path, output_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """从 CSV 文件读取并清洗评论；可选输出 JSON 文件。"""

    source = Path(input_path)
    with source.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    cleaned = clean_review_rows(rows)

    if output_path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="清洗电商评论 CSV")
    parser.add_argument("input", help="输入 CSV 路径")
    parser.add_argument("-o", "--output", help="输出 JSON 路径")
    args = parser.parse_args()

    cleaned = clean_reviews_from_csv(args.input, args.output)
    print(json.dumps(cleaned, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
