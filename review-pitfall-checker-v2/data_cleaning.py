from __future__ import annotations

import html
import re
from typing import Any


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]")
KV_RE = re.compile(r"(?P<key>[\u4e00-\u9fffA-Za-z0-9 _/\-]{1,20})[:：]\s*(?P<value>[^\n\r;；|]{1,50})")

USELESS_ECOMMERCE_PHRASES = (
    "此用户没有填写评价",
    "系统默认好评",
    "收到了",
    "很好",
    "挺好",
    "不错",
)
USELESS_XHS_PHRASES = (
    "接广告吗",
    "求私信",
    "求链接",
    "蹲链接",
    "求地址",
)
MARKETING_BLACKLIST = (
    "姐妹们冲啊",
    "宝藏单品",
    "大数据推荐",
    "平替",
    "尊嘟假嘟",
    "福利暗号",
    "官方置顶",
    "链接在评论区",
)
XHS_PRAISE_TERMS = ("回购", "闭眼冲", "无脑买", "绝绝子", "天花板", "真香", "好用到哭")
GENERAL_NEGATIVE_TERMS = (
    "翻车",
    "发热",
    "坏了",
    "拉稀",
    "烫",
    "断连",
    "刺痛",
    "长痘",
    "发红",
    "软便",
    "不吃",
)
CRITICAL_TERMS = {
    "power_bank": ("烫", "发热", "断连"),
    "facial_mask": ("刺痛", "长痘", "发红"),
    "dog_food": ("软便", "拉稀", "不吃"),
}

SPEC_KEYS = ("spec", "param", "detail", "attribute", "规格", "参数", "详情")
COMMENT_KEYS = ("review", "reviews", "comment", "comments", "评价", "评论", "追评")
NOTE_KEYS = ("note", "notes", "content", "body", "desc", "note_text")
TEXT_KEYS = ("text", "content", "comment", "review", "body", "desc", "note_text")


def clean_and_filter_data(raw_data: dict, platform: str, category: str) -> dict:
    try:
        normalized_platform = _normalize_platform(platform)
        normalized_category = _normalize_category(category)
        if not isinstance(raw_data, dict):
            return _empty_result(normalized_platform, normalized_category)

        if normalized_platform in {"jd", "taobao"}:
            return _clean_ecommerce(raw_data, normalized_platform, normalized_category)
        if normalized_platform == "xhs":
            return _clean_xhs(raw_data, normalized_platform, normalized_category)
        return _empty_result(normalized_platform, normalized_category)
    except Exception:
        return _empty_result(_normalize_platform(platform), _normalize_category(category))


def _clean_ecommerce(raw_data: dict, platform: str, category: str) -> dict:
    result = _empty_result(platform, category)
    specs_pairs = _extract_spec_pairs(raw_data)
    result["specs_pairs"] = specs_pairs
    result["specs_text"] = "\n".join(f"{key}: {value}" for key, value in specs_pairs)

    raw_comments = _extract_text_entries(raw_data, COMMENT_KEYS)
    result["total_count"] = len(raw_comments)

    cleaned_comments: list[dict[str, Any]] = []
    noise_count = 0
    for entry in raw_comments:
        text = _clean_text(entry["text"])
        if _is_invalid_ecommerce_comment(text):
            noise_count += 1
            continue
        priority = _score_ecommerce_comment(text)
        cleaned_comments.append(
            {
                "text": text,
                "is_critical_issue": _has_critical_issue(text, category),
                "priority_score": priority,
            }
        )

    cleaned_comments.sort(key=lambda item: (-item["priority_score"], -len(item["text"])))
    result["comments"] = [
        {"text": item["text"], "is_critical_issue": item["is_critical_issue"]}
        for item in cleaned_comments[:15]
    ]
    result["noise_count"] = noise_count
    result["noise_rate_estimate"] = _round_rate(noise_count, result["total_count"])
    return result


def _clean_xhs(raw_data: dict, platform: str, category: str) -> dict:
    result = _empty_result(platform, category)
    note_records = _extract_xhs_notes(raw_data)
    total_count = 0
    noise_count = 0
    kept_notes: list[dict[str, str]] = []
    kept_comments: list[dict[str, Any]] = []

    for note in note_records:
        body = _clean_text(note.get("body", ""))
        if body:
            total_count += 1
            if _is_marketing_note(body):
                noise_count += 1
            else:
                kept_notes.append({"text": body[:500]})

        for comment_text in note.get("top_comments", []):
            total_count += 1
            cleaned_comment = _clean_text(comment_text)
            if _is_invalid_xhs_comment(cleaned_comment):
                noise_count += 1
                continue
            kept_comments.append(
                {
                    "text": cleaned_comment,
                    "is_critical_issue": _has_critical_issue(cleaned_comment, category),
                }
            )

    result["notes"] = kept_notes
    result["comments"] = kept_comments[:10]
    result["total_count"] = total_count
    result["noise_count"] = noise_count
    result["noise_rate_estimate"] = _round_rate(noise_count, total_count)
    return result


def _empty_result(platform: str, category: str) -> dict:
    return {
        "platform": platform,
        "category": category,
        "specs_text": "",
        "specs_pairs": [],
        "notes": [],
        "comments": [],
        "total_count": 0,
        "noise_count": 0,
        "noise_rate_estimate": 0.0,
    }


def _normalize_platform(platform: str) -> str:
    value = str(platform or "").lower()
    if "taobao" in value:
        return "taobao"
    if "xhs" in value or "xiaohongshu" in value:
        return "xhs"
    if "jd" in value:
        return "jd"
    return value or "unknown"


def _normalize_category(category: str) -> str:
    value = str(category or "").lower()
    if value in CRITICAL_TERMS:
        return value
    if "power" in value or "bank" in value or "充电宝" in value:
        return "power_bank"
    if "mask" in value or "facial" in value or "面膜" in value:
        return "facial_mask"
    if "dog" in value or "food" in value or "狗粮" in value:
        return "dog_food"
    return value or "unknown"


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_RE.sub(" ", text)
    text = CONTROL_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = text.replace("\u3000", " ").replace("&nbsp;", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip(" \n\r\t|;；，,")


def _extract_spec_pairs(raw_data: dict) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def walk(node: Any, in_spec_context: bool = False) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_text = _clean_text(key)
                next_spec_context = in_spec_context or any(marker in key_text.lower() for marker in SPEC_KEYS)
                if next_spec_context and isinstance(value, (str, int, float)):
                    cleaned_value = _clean_text(value)
                    if cleaned_value:
                        candidate = (key_text, cleaned_value)
                        if candidate not in seen:
                            seen.add(candidate)
                            pairs.append(candidate)
                if isinstance(value, str) and next_spec_context:
                    for match in KV_RE.finditer(_clean_text(value)):
                        candidate = (_clean_text(match.group("key")), _clean_text(match.group("value")))
                        if candidate not in seen:
                            seen.add(candidate)
                            pairs.append(candidate)
                elif isinstance(value, (dict, list)):
                    walk(value, next_spec_context)
        elif isinstance(node, list):
            for item in node:
                walk(item, in_spec_context)
        elif isinstance(node, str) and in_spec_context:
            for match in KV_RE.finditer(_clean_text(node)):
                candidate = (_clean_text(match.group("key")), _clean_text(match.group("value")))
                if candidate not in seen:
                    seen.add(candidate)
                    pairs.append(candidate)

    walk(raw_data)
    return pairs[:30]


def _extract_text_entries(raw_data: Any, root_keys: tuple[str, ...]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    def walk(node: Any, in_context: bool = False) -> None:
        if isinstance(node, dict):
            direct_text = _pick_first_text(node)
            if in_context and direct_text:
                results.append({"text": direct_text})
            for key, value in node.items():
                key_text = str(key).lower()
                next_context = in_context or any(marker in key_text for marker in root_keys)
                if isinstance(value, (dict, list)):
                    walk(value, next_context)
                elif next_context and isinstance(value, (str, int, float)) and key_text in TEXT_KEYS:
                    results.append({"text": str(value)})
                elif next_context and isinstance(value, str) and key_text not in TEXT_KEYS:
                    results.append({"text": value})
        elif isinstance(node, list):
            for item in node:
                walk(item, in_context)
        elif in_context and isinstance(node, (str, int, float)):
            results.append({"text": str(node)})

    walk(raw_data)
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in results:
        cleaned = _clean_text(item["text"])
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append({"text": cleaned})
    return deduped


def _extract_xhs_notes(raw_data: dict) -> list[dict[str, Any]]:
    notes_raw = raw_data.get("notes")
    shared_comments = _extract_top_comments(raw_data)
    if isinstance(notes_raw, list):
        source_notes = notes_raw
    else:
        source_notes = [raw_data]

    notes: list[dict[str, Any]] = []
    for note in source_notes:
        if isinstance(note, (str, int, float)):
            notes.append({"body": str(note), "top_comments": list(shared_comments)})
            continue
        if not isinstance(note, dict):
            continue
        body = _pick_first_text(note, preferred_keys=("note_text", "content", "body", "desc", "text"))
        top_comments = _extract_top_comments(note)
        if body or top_comments:
            notes.append({"body": body, "top_comments": top_comments})
    return notes


def _extract_top_comments(note: dict) -> list[str]:
    raw_comments = []
    for key, value in note.items():
        key_text = str(key).lower()
        if "top_comment" in key_text or "comment" in key_text:
            if isinstance(value, list):
                raw_comments.extend(_coerce_comment_texts(value))
            elif isinstance(value, (dict, str)):
                raw_comments.extend(_coerce_comment_texts([value]))
    return raw_comments


def _coerce_comment_texts(values: list[Any]) -> list[str]:
    results: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = _pick_first_text(value)
            if text:
                results.append(text)
        elif isinstance(value, (str, int, float)):
            results.append(str(value))
    return results


def _pick_first_text(node: dict, preferred_keys: tuple[str, ...] = TEXT_KEYS) -> str:
    for key in preferred_keys:
        value = node.get(key)
        if isinstance(value, (str, int, float)):
            cleaned = _clean_text(value)
            if cleaned:
                return cleaned
    for value in node.values():
        if isinstance(value, (str, int, float)):
            cleaned = _clean_text(value)
            if cleaned:
                return cleaned
    return ""


def _is_invalid_ecommerce_comment(text: str) -> bool:
    if len(text) < 6:
        return True
    return any(phrase in text for phrase in USELESS_ECOMMERCE_PHRASES)


def _is_invalid_xhs_comment(text: str) -> bool:
    if len(text) < 6:
        return True
    return any(phrase in text for phrase in USELESS_XHS_PHRASES)


def _is_marketing_note(text: str) -> bool:
    marketing_hits = sum(1 for phrase in MARKETING_BLACKLIST if phrase in text)
    has_praise = any(term in text for term in XHS_PRAISE_TERMS)
    has_flaw = any(term in text for term in GENERAL_NEGATIVE_TERMS)
    return marketing_hits >= 2 or (has_praise and not has_flaw)


def _score_ecommerce_comment(text: str) -> int:
    score = 0
    if "追加评论" in text or "追评" in text:
        score += 4
    score += sum(2 for term in GENERAL_NEGATIVE_TERMS if term in text)
    score += min(len(text) // 20, 3)
    return score


def _has_critical_issue(text: str, category: str) -> bool:
    critical_terms = CRITICAL_TERMS.get(category, ())
    return any(term in text for term in critical_terms)


def _round_rate(noise_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round(noise_count / total_count, 2)
