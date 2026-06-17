"""Cross-platform FITorNOT decision agent.

This module keeps the new Bright Data driven workflow separate from the
original manual-review FITorNOT tool. The caller must pass a Bright Data MCP
adapter as ``brightdata_client``; the agent never fabricates product data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


URL_PATTERN = re.compile(r"https?://[^\s,，]+", re.IGNORECASE)

PROMO_PHRASES = (
    "闭眼冲",
    "姐妹们",
    "太绝了",
    "好评返现",
    "默认好评",
    "红包",
    "五星好评",
    "无脑入",
)

RISK_KEYWORDS = (
    "发热",
    "烫",
    "鼓包",
    "虚标",
    "卡顿",
    "做工",
    "粗糙",
    "售后",
    "漏液",
    "刺痛",
    "泛红",
    "过敏",
    "不支持快充",
    "接口松",
    "太重",
    "小包放不下",
    "Wh",
    "认证",
)


class BrightDataClient(Protocol):
    """Runtime boundary for Bright Data MCP tools."""

    def scrape(self, url: str) -> dict[str, Any]:
        """Scrape one public product or social URL."""


@dataclass(frozen=True)
class ScrapedSource:
    url: str
    platform: str
    data: dict[str, Any]


@dataclass(frozen=True)
class BlockedLink:
    url: str
    reason: str


def analyze_product_links(
    request: dict[str, Any], brightdata_client: BrightDataClient | None = None
) -> dict[str, Any]:
    """Scrape all URLs and return a cleaned decision report.

    ``brightdata_client`` must be an adapter around the ``brightdata`` MCP
    namespace, such as ``brightdata__scrape`` or a platform-specific parser.
    """

    links = _extract_links(request)
    output_language = str(request.get("output_language") or "中文").strip() or "中文"
    if not links:
        raise ValueError("at least one URL is required")
    if brightdata_client is None:
        raise ValueError("brightdata_client is required")

    sources: list[ScrapedSource] = []
    blocked_links: list[BlockedLink] = []

    for url in links:
        try:
            scraped = brightdata_client.scrape(url)
        except Exception as exc:  # noqa: BLE001 - preserve runtime scrape reason.
            blocked_links.append(BlockedLink(url=url, reason=str(exc)))
            continue

        sources.append(
            ScrapedSource(
                url=url,
                platform=_detect_platform(url, scraped),
                data=scraped,
            )
        )

    profile = _build_profile(sources)
    report = _render_report(
        profile=profile,
        blocked_links=blocked_links,
        output_language=output_language,
    )

    return {
        "language": output_language,
        "scraped_urls": [source.url for source in sources],
        "blocked_links": [
            {"url": link.url, "reason": link.reason} for link in blocked_links
        ],
        "report": report,
    }


def _extract_links(request: dict[str, Any]) -> list[str]:
    links = request.get("links")
    if isinstance(links, list):
        return [str(link).strip() for link in links if str(link).strip()]

    text = str(request.get("input") or request.get("text") or "")
    return URL_PATTERN.findall(text)


def _detect_platform(url: str, scraped: dict[str, Any]) -> str:
    explicit = str(scraped.get("platform") or "").lower()
    if explicit:
        return explicit
    lowered = url.lower()
    if "xiaohongshu.com" in lowered or "xhslink.com" in lowered:
        return "xiaohongshu"
    if "jd.com" in lowered:
        return "jd"
    if "taobao.com" in lowered or "tmall.com" in lowered:
        return "taobao"
    return "other"


def _build_profile(sources: list[ScrapedSource]) -> dict[str, Any]:
    product_names: list[str] = []
    source_rows: list[dict[str, Any]] = []
    risks: list[str] = []
    highlights: list[str] = []
    ecommerce_params: list[str] = []

    for source in sources:
        product_name = _pick_product_name(source.data)
        if product_name and product_name not in product_names:
            product_names.append(product_name)

        cleaned_texts = _extract_clean_texts(source)
        source_risks = _pick_keyword_texts(cleaned_texts, RISK_KEYWORDS)
        source_highlights = _pick_highlights(cleaned_texts)

        risks.extend(_dedupe(source_risks))
        highlights.extend(_dedupe(source_highlights))

        params = source.data.get("parameters")
        if isinstance(params, dict):
            ecommerce_params.extend(
                f"{key}: {value}" for key, value in params.items() if value
            )

        source_rows.append(
            {
                "platform_label": _platform_label(source.platform),
                "noise_level": _estimate_noise_level(source),
                "signal": _summarize_signal(source_risks, source_highlights),
            }
        )

    return {
        "product_name": product_names[0] if product_names else "Unknown product",
        "selling_points": _dedupe(ecommerce_params + highlights)[:3],
        "source_rows": source_rows,
        "risks": _dedupe(risks)[:5],
        "scenario_risks": _infer_scenario_risks(risks),
        "purchase_score": _purchase_score(risks, source_rows),
    }


def _pick_product_name(data: dict[str, Any]) -> str:
    for key in ("product_title", "title", "name", "goods_name"):
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _extract_clean_texts(source: ScrapedSource) -> list[str]:
    texts: list[str] = []
    data = source.data

    for key in ("note_text", "description", "title"):
        value = data.get(key)
        if isinstance(value, str):
            texts.append(value)

    for key in ("comments", "reviews", "additional_reviews", "negative_reviews"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("comment")
                if text:
                    texts.append(str(text))

    return [text for text in texts if text.strip() and not _is_noise_text(text)]


def _is_noise_text(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 4:
        return True
    return any(phrase in stripped for phrase in PROMO_PHRASES)


def _pick_keyword_texts(texts: list[str], keywords: tuple[str, ...]) -> list[str]:
    return [
        text
        for text in texts
        if any(keyword.lower() in text.lower() for keyword in keywords)
    ]


def _pick_highlights(texts: list[str]) -> list[str]:
    positive_terms = ("方便", "适合", "效果", "小巧", "稳定", "快充")
    return [
        text
        for text in texts
        if any(term in text for term in positive_terms)
        and not any(term in text for term in ("不支持", "不适合", "虚标"))
    ]


def _estimate_noise_level(source: ScrapedSource) -> str:
    raw_texts: list[str] = []
    data = source.data
    for value in data.values():
        if isinstance(value, str):
            raw_texts.append(value)
        elif isinstance(value, list):
            for item in value:
                raw_texts.append(str(item.get("text", item)) if isinstance(item, dict) else str(item))

    if not raw_texts:
        return "低"
    noisy = sum(1 for text in raw_texts if _is_noise_text(text))
    ratio = noisy / len(raw_texts)
    if ratio >= 0.5:
        return "高"
    if ratio >= 0.25:
        return "中"
    return "低"


def _summarize_signal(risks: list[str], highlights: list[str]) -> str:
    signals = _dedupe(risks + highlights)
    if not signals:
        return "未抓到足够具体的真实体验信号"
    return "；".join(signals[:2])


def _infer_scenario_risks(risks: list[str]) -> list[str]:
    joined = " ".join(risks)
    inferred: list[str] = []
    if any(term in joined for term in ("发热", "烫", "鼓包", "Wh", "认证")):
        inferred.append("不适合对电池安全、航旅安检或夜间充电很敏感的用户")
    if any(term in joined for term in ("太重", "小包放不下")):
        inferred.append("不适合轻装通勤、随身小包或长时间携带场景")
    if any(term in joined for term in ("刺痛", "泛红", "过敏")):
        inferred.append("不适合敏感肌或正在屏障受损的人群直接上脸")
    return inferred or ["需要结合你的具体使用场景复核参数与售后条件"]


def _purchase_score(risks: list[str], source_rows: list[dict[str, Any]]) -> str:
    high_risk_terms = ("鼓包", "认证", "过敏", "发热", "烫", "虚标")
    high_risk_count = sum(
        1 for risk in risks if any(term in risk for term in high_risk_terms)
    )
    if high_risk_count >= 3:
        return "⭐⭐"
    if high_risk_count >= 1 or any(row["noise_level"] == "高" for row in source_rows):
        return "⭐⭐⭐"
    return "⭐⭐⭐⭐"


def _platform_label(platform: str) -> str:
    if platform in {"xiaohongshu", "xhs"}:
        return "小红书 (种草/玩法)"
    if platform in {"jd", "taobao", "tmall"}:
        return "电商平台 (价格/质量)"
    return "其他公开来源"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = " ".join(str(item).split())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _render_report(
    profile: dict[str, Any],
    blocked_links: list[BlockedLink],
    output_language: str,
) -> str:
    if _is_english(output_language):
        return _render_english_report(profile, blocked_links)
    return _render_chinese_report(profile, blocked_links)


def _is_english(output_language: str) -> bool:
    return output_language.strip().lower() in {"english", "en", "英文"}


def _render_chinese_report(
    profile: dict[str, Any], blocked_links: list[BlockedLink]
) -> str:
    rows = "\n".join(
        f"| {row['platform_label']} | {row['noise_level']} | {row['signal']} |"
        for row in profile["source_rows"]
    )
    blocked = _render_chinese_blocked_links(blocked_links)
    risks = profile["risks"] or ["已抓取样本中没有出现足够明确的高危硬伤"]
    scenario_risks = profile["scenario_risks"]

    return f"""## 📌 商品全局意图图谱
- **目标品类/型号**：{profile['product_name']}
- **全网核心卖点**：{_join_or_none(profile['selling_points'])}

## 🔍 跨平台数据交叉验证 (Bright Data Scraped Data)
| 平台数据源 | 样本噪点率 (软文/刷单预估) | 核心风向标 (用户都在夸什么/骂什么) |
| :--- | :--- | :--- |
{rows or '| 暂无成功抓取来源 | 高 | 无法形成可靠判断 |'}

{blocked}
## 🚫 避坑指南与风险分级
- **⚡ 高危风险（买前必看）**：{risks[0]}
- **⚠️ 场景不匹配风险**：{scenario_risks[0]}

## 💡 最终决策建议
- **购买指数**：{profile['purchase_score']}
- **一句话结论**：如果上述高危风险正好命中你的使用场景，建议先观望或换更透明的同类商品；否则只建议在可退换、参数清楚的渠道低风险尝试。"""


def _render_chinese_blocked_links(blocked_links: list[BlockedLink]) -> str:
    if not blocked_links:
        return ""
    lines = "\n".join(f"- {link.url}：{link.reason}" for link in blocked_links)
    return f"""抓取受阻链接（残缺版分析，未补造数据）：
{lines}

"""


def _render_english_report(
    profile: dict[str, Any], blocked_links: list[BlockedLink]
) -> str:
    rows = "\n".join(
        f"| {row['platform_label']} | {_noise_en(row['noise_level'])} | {row['signal']} |"
        for row in profile["source_rows"]
    )
    blocked = _render_english_blocked_links(blocked_links)
    risks = profile["risks"] or ["No concrete high-risk defect appeared in the scraped samples"]
    scenario_risks = profile["scenario_risks"]

    return f"""## 📌 Global Product Intent Map
- **Target category/model**: {profile['product_name']}
- **Core market selling points**: {_join_or_none(profile['selling_points'], none_text='Not enough reliable signal')}

## 🔍 Cross-Platform Validation (Bright Data Scraped Data)
| Source | Estimated noise level | Core signal |
| :--- | :--- | :--- |
{rows or '| No successfully scraped source | High | No reliable signal |'}

{blocked}
## 🚫 Pitfall Guide and Risk Levels
- **⚡ High-risk issue**: {risks[0]}
- **⚠️ Scenario mismatch risk**: {scenario_risks[0]}

## 💡 Final Decision
- **Purchase index**: {profile['purchase_score']}
- **One-line conclusion**: Partial analysis is acceptable only for screening. If the high-risk issue matches your use case, skip it or wait for stronger cross-platform evidence."""


def _render_english_blocked_links(blocked_links: list[BlockedLink]) -> str:
    if not blocked_links:
        return ""
    lines = "\n".join(f"- {link.url}: {link.reason}" for link in blocked_links)
    return f"""Partial analysis: these links were blocked, and no data was invented for them:
{lines}

"""


def _noise_en(value: str) -> str:
    return {"高": "High", "中": "Medium", "低": "Low"}.get(value, value)


def _join_or_none(items: list[str], none_text: str = "暂无足够可靠信号") -> str:
    return "；".join(items) if items else none_text
