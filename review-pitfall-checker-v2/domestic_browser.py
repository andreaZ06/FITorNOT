from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

DEFAULT_BROWSER_CHANNEL = "chrome"
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8"
TAOBAO_RESPONSE_MARKER = "wirelessrecommend.recommend"
BROWSER_PROFILE_SYNC_ARTIFACTS = (
    "Local State",
    "Default/Network/Cookies",
    "Default/Network/Cookies-journal",
    "Default/Preferences",
    "Default/Secure Preferences",
    "Default/Local Storage",
    "Default/Session Storage",
    "Default/IndexedDB",
    "Default/WebStorage",
    "Default/Storage",
)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cdp_url_marker_path(profile_dir: Path | str | None) -> Path | None:
    if not profile_dir:
        return None
    return Path(profile_dir) / "cdp-url.txt"


def _read_cdp_url_marker(profile_dir: Path | str | None) -> str | None:
    marker_path = _cdp_url_marker_path(profile_dir)
    if marker_path is None or not marker_path.exists():
        return None
    value = marker_path.read_text(encoding="utf-8").replace("\ufeff", "").strip()
    return value or None


def _default_profile_source_root() -> Path | None:
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None

    candidate = Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if (candidate / "Default").exists():
        return candidate
    return None


def build_browser_session_config(profile_dir: Path | str | None = None) -> dict[str, Any]:
    cdp_url = os.getenv("FITORNOT_BROWSER_CDP_URL", "").strip() or (_read_cdp_url_marker(profile_dir) or "")
    channel = os.getenv("FITORNOT_BROWSER_CHANNEL", DEFAULT_BROWSER_CHANNEL).strip() or DEFAULT_BROWSER_CHANNEL
    user_agent = os.getenv("FITORNOT_BROWSER_USER_AGENT", DEFAULT_BROWSER_USER_AGENT).strip() or DEFAULT_BROWSER_USER_AGENT
    source_root = os.getenv("FITORNOT_BROWSER_PROFILE_SOURCE_DIR", "").strip()
    if source_root:
        profile_source_root = Path(source_root)
    else:
        profile_source_root = _default_profile_source_root()
    return {
        "mode": "cdp" if cdp_url else "persistent",
        "cdp_url": cdp_url or None,
        "channel": channel,
        "user_agent": user_agent,
        "extra_http_headers": {"Accept-Language": DEFAULT_ACCEPT_LANGUAGE},
        "profile_source_root": str(profile_source_root) if profile_source_root else None,
        "sync_system_profile": _env_flag(
            "FITORNOT_BROWSER_SYNC_SYSTEM_PROFILE",
            bool(profile_source_root),
        ),
    }


def sync_browser_profile(source_root: Path | str | None, target_root: Path | str) -> dict[str, Any]:
    if not source_root:
        return {"copied": False, "copied_entries": 0, "errors": []}

    source_path = Path(source_root)
    target_path = Path(target_root)
    if not source_path.exists():
        return {"copied": False, "copied_entries": 0, "errors": [f"missing source root: {source_path}"]}

    if source_path.resolve() == target_path.resolve():
        return {"copied": False, "copied_entries": 0, "errors": []}

    copied_entries = 0
    errors: list[str] = []
    target_path.mkdir(parents=True, exist_ok=True)

    for relative_path in BROWSER_PROFILE_SYNC_ARTIFACTS:
        source_item = source_path / relative_path
        if not source_item.exists():
            continue

        destination_item = target_path / relative_path
        destination_item.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source_item.is_dir():
                shutil.copytree(source_item, destination_item, dirs_exist_ok=True)
            else:
                shutil.copy2(source_item, destination_item)
            copied_entries += 1
        except OSError as exc:
            if source_item.name == "Cookies" and _copy_sqlite_database(source_item, destination_item):
                copied_entries += 1
                continue
            if source_item.name == "Cookies" and _copy_file_with_esentutl(source_item, destination_item):
                copied_entries += 1
                continue
            if source_item.name == "Cookies-journal":
                continue
            errors.append(f"{relative_path}: {exc}")

    return {
        "copied": copied_entries > 0,
        "copied_entries": copied_entries,
        "errors": errors,
    }


def _copy_sqlite_database(source_item: Path, destination_item: Path) -> bool:
    destination_item.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source_item.resolve().as_posix()}?mode=ro"
    try:
        with contextlib.closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
            with contextlib.closing(sqlite3.connect(destination_item)) as destination_connection:
                source_connection.backup(destination_connection)
        return True
    except sqlite3.Error:
        return False


def _copy_file_with_esentutl(source_item: Path, destination_item: Path) -> bool:
    esentutl_path = shutil.which("esentutl.exe")
    if not esentutl_path:
        return False

    destination_item.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [esentutl_path, "/y", str(source_item), "/d", str(destination_item), "/o"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return destination_item.exists() and destination_item.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):
        return False


def _strip_jsonp_wrapper(text: str) -> str:
    stripped = text.strip().rstrip(";")
    match = re.match(r"^[A-Za-z0-9_$]+\((.*)\)$", stripped, re.DOTALL)
    return match.group(1).strip() if match else stripped


def _extract_scalar(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"null", "none"}:
            return text
    return ""


def _normalize_candidate_url(url: str, item_id: str) -> str:
    normalized = str(url or "").strip()
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    if normalized and normalized.startswith("/"):
        normalized = f"https://s.taobao.com{normalized}"
    if normalized:
        return normalized

    cleaned_id = re.sub(r"\D+", "", item_id or "")
    if cleaned_id:
        return f"https://item.taobao.com/item.htm?id={cleaned_id}"
    return ""


def _iter_nested_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            records.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(reversed(current))
    return records


def parse_taobao_search_response(response_text: str, limit: int = 20) -> list[dict[str, Any]]:
    try:
        payload = json.loads(_strip_jsonp_wrapper(response_text))
    except json.JSONDecodeError:
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in _iter_nested_records(payload):
        title = _extract_scalar(record, "title", "raw_title", "itemTitle", "auctionTitle", "name")
        price = _extract_scalar(
            record,
            "price",
            "salePrice",
            "priceText",
            "finalPrice",
            "discountPrice",
            "promotionPrice",
        )
        shop_name = _extract_scalar(record, "shopName", "nick", "sellerNick", "sellerName", "shop")
        item_id = _extract_scalar(record, "itemId", "item_id", "auctionId", "auction_id", "nid", "num_iid")
        url = _normalize_candidate_url(
            _extract_scalar(record, "url", "itemUrl", "clickUrl", "auctionURL", "detailUrl", "targetUrl"),
            item_id,
        )
        normalized_title = re.sub(r"\s+", " ", title).strip()
        if len(normalized_title) < 4:
            continue
        if not any([price, shop_name, url]):
            continue

        dedupe_key = f"{normalized_title.lower()}|{url}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "title": normalized_title,
                "price": price,
                "shop_name": shop_name,
                "url": url,
                "platform": "taobao",
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def cap_xhs_hits(hits: list[dict[str, Any]], total_comment_limit: int = 20) -> list[dict[str, Any]]:
    remaining = max(total_comment_limit, 0)
    normalized: list[dict[str, Any]] = []
    for hit in hits:
        notes: list[dict[str, str]] = []
        for note in hit.get("notes", []):
            text = str(note.get("text") or note.get("content") or "").strip()
            if text:
                notes.append({"text": text[:500], "title": str(note.get("title", "")).strip()})

        comments: list[dict[str, str]] = []
        seen_comments: set[str] = set()
        if remaining > 0:
            for comment in hit.get("comments", []):
                text = str(comment.get("text") if isinstance(comment, dict) else comment).strip()
                normalized_comment = re.sub(r"\s+", " ", text)
                if not normalized_comment:
                    continue
                dedupe_key = normalized_comment.lower()
                if dedupe_key in seen_comments:
                    continue
                seen_comments.add(dedupe_key)
                comments.append({"text": normalized_comment[:240]})
                remaining -= 1
                if remaining <= 0:
                    break

        if notes or comments:
            normalized.append(
                {
                    "query": str(hit.get("query", "")).strip(),
                    "url": str(hit.get("url", "")).strip(),
                    "notes": notes,
                    "comments": comments,
                    "platform": str(hit.get("platform", "xiaohongshu")).strip() or "xiaohongshu",
                }
            )
    return normalized


def _extract_xhs_note_id(url: str) -> str:
    match = re.search(r"/(?:explore|search_result|discovery/item)/([^/?#]+)", url)
    return match.group(1) if match else ""


def normalize_xhs_search_candidates(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    for item in items:
        url = str(item.get("url", "")).strip()
        note_id = _extract_xhs_note_id(url)
        if not note_id:
            continue

        normalized_url = url
        if normalized_url.startswith("/"):
            normalized_url = f"https://www.xiaohongshu.com{normalized_url}"

        text = re.sub(r"\s+", " ", str(item.get("text", "")).strip())
        title = re.sub(r"\s+", " ", str(item.get("title", "")).strip()) or text[:60]
        if not note_id in grouped:
            grouped[note_id] = {
                "url": normalized_url,
                "title": title,
                "text": text,
            }
            ordered_ids.append(note_id)
            continue

        existing = grouped[note_id]
        if "/search_result/" in normalized_url and "/search_result/" not in str(existing.get("url", "")):
            existing["url"] = normalized_url
        if len(title) > len(str(existing.get("title", ""))):
            existing["title"] = title
        if len(text) > len(str(existing.get("text", ""))):
            existing["text"] = text

    normalized: list[dict[str, Any]] = []
    for note_id in ordered_ids:
        item = grouped[note_id]
        title = str(item.get("title", "")).strip()
        text = str(item.get("text", "")).strip()
        url = str(item.get("url", "")).strip()
        if not url or not (title or text):
            continue
        normalized.append(
            {
                "url": url,
                "title": title or text[:60],
                "text": text or title,
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def detect_platform_block_reason(
    platform: str,
    title: str,
    body_text: str,
    response_texts: list[str] | None = None,
) -> str | None:
    combined = "\n".join(part for part in [title, body_text, *(response_texts or [])] if part)
    lowered = combined.lower()

    if platform == "jd":
        if (
            ("京东登录" in combined)
            or ("欢迎登录" in combined and "京东" in combined)
            or ("个人用户登录" in combined and "手机扫码安全登录" in combined)
            or ("获取验证码" in combined and "账号密码登录" in combined)
        ):
            return "JD search login required: use a trusted browser session."
        return None

    if platform in {"xiaohongshu", "xhs"}:
        if "IP存在风险" in combined:
            return "Xiaohongshu search is blocking the current network as risky."
        if "登录后推荐更懂你的笔记" in combined or ("手机号登录" in combined and "小红书" in combined):
            return "Xiaohongshu search login required: use a trusted browser session."
        return None

    if platform == "taobao":
        if any(marker in lowered for marker in ("fail_sys_user_validate", "rgv587_error", "action=captcha", "purecaptcha")):
            return "Taobao search captcha verification triggered; use a trusted browser session."
        if "login.taobao.com" in lowered or ("亲，请登录" in combined and "加载中" in combined):
            return "Taobao search login required: use a trusted browser session."
        return None

    return None


class PlaywrightDomesticBrowserAdapter:
    def __init__(
        self,
        profile_dir: str | None = None,
        headless: bool | None = None,
        ecommerce_platforms: tuple[str, ...] = ("jd", "taobao"),
    ) -> None:
        default_profile_dir = Path(__file__).resolve().parent / ".browser-profile"
        self.profile_dir = Path(profile_dir or os.getenv("FITORNOT_BROWSER_PROFILE_DIR", default_profile_dir))
        self.headless = _env_flag("FITORNOT_BROWSER_HEADLESS", True) if headless is None else headless
        self.ecommerce_platforms = ecommerce_platforms
        self.timeout_ms = int(os.getenv("FITORNOT_BROWSER_TIMEOUT_MS", "45000"))
        self.scroll_rounds = int(os.getenv("FITORNOT_BROWSER_SCROLL_ROUNDS", "2"))
        self.total_xhs_comment_limit = int(os.getenv("FITORNOT_XHS_TOTAL_COMMENT_LIMIT", "20"))

    async def fetch_ecommerce_candidates(self, query: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
        del category  # reserved for future platform-specific tuning
        if not query.strip():
            return []

        async with self._browser_context() as context:
            collected: list[dict[str, Any]] = []
            blocked_reasons: list[str] = []
            for platform in self.ecommerce_platforms:
                page = await context.new_page()
                response_texts: list[str] = []
                response_tasks: set[asyncio.Task[Any]] = set()

                def _schedule_response_capture(response: Any) -> None:
                    task = asyncio.create_task(self._capture_relevant_response_text(response, platform, response_texts))
                    response_tasks.add(task)
                    task.add_done_callback(response_tasks.discard)

                page.on("response", _schedule_response_capture)
                try:
                    await self._open_search_page(page, platform, query)
                    await self._lazy_scroll(page)
                    await asyncio.sleep(1)
                    page_candidates = await self._extract_ecommerce_candidates(page, platform, limit)
                    if platform == "taobao":
                        for response_text in response_texts:
                            page_candidates.extend(parse_taobao_search_response(response_text, limit=limit))
                        page_candidates = self._dedupe_candidates(page_candidates, limit)

                    block_reason = detect_platform_block_reason(
                        platform,
                        await page.title(),
                        await self._body_text(page),
                        response_texts,
                    )
                    if block_reason and not page_candidates:
                        blocked_reasons.append(block_reason)
                        continue

                    collected.extend(page_candidates)
                finally:
                    if response_tasks:
                        await asyncio.gather(*response_tasks, return_exceptions=True)
                    await page.close()

            normalized = self._dedupe_candidates(collected, limit)
            if normalized:
                return normalized
            if blocked_reasons:
                raise RuntimeError("; ".join(blocked_reasons))
            return []

    async def fetch_xiaohongshu_feedback(self, queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
        cleaned_queries = [query.strip() for query in queries if query and query.strip()]
        if not cleaned_queries:
            return []

        per_query_limit = max(1, min(3, limit))
        hits: list[dict[str, Any]] = []
        async with self._browser_context() as context:
            for query in cleaned_queries:
                search_page = await context.new_page()
                try:
                    await self._open_xhs_search(search_page, query)
                    block_reason = detect_platform_block_reason(
                        "xiaohongshu",
                        await search_page.title(),
                        await self._body_text(search_page),
                    )
                    if block_reason:
                        raise RuntimeError(block_reason)

                    await self._lazy_scroll(search_page, rounds=1)
                    note_summaries = await self._extract_xhs_search_results(search_page, per_query_limit)
                finally:
                    await search_page.close()

                notes: list[dict[str, Any]] = []
                comments: list[dict[str, str]] = []
                detail_url = ""
                for summary in note_summaries[:per_query_limit]:
                    detail_page = await context.new_page()
                    try:
                        detail_url = summary.get("url", "")
                        if not detail_url:
                            continue
                        await self._goto_and_wait(detail_page, detail_url)
                        detail_block_reason = detect_platform_block_reason(
                            "xiaohongshu",
                            await detail_page.title(),
                            await self._body_text(detail_page),
                        )
                        if detail_block_reason:
                            continue
                        detail_payload = await self._extract_xhs_note_detail(detail_page)
                    finally:
                        await detail_page.close()

                    note_text = (detail_payload.get("text") or summary.get("text") or "").strip()
                    if note_text:
                        notes.append({"text": note_text[:500], "title": summary.get("title", "")})
                    for comment in detail_payload.get("comments", [])[:20]:
                        text = str(comment.get("text") if isinstance(comment, dict) else comment).strip()
                        if text:
                            comments.append({"text": text[:240]})

                if notes or comments:
                    hits.append(
                        {
                            "query": query,
                            "url": detail_url,
                            "notes": notes[:per_query_limit],
                            "comments": comments,
                            "platform": "xiaohongshu",
                        }
                    )

                if len(hits) >= limit:
                    break
        return cap_xhs_hits(hits[:limit], total_comment_limit=max(self.total_xhs_comment_limit, limit))

    @contextlib.asynccontextmanager
    async def _browser_context(self):
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - depends on local runtime
            raise RuntimeError(
                "Playwright browser adapter is unavailable. Install it with `pip install playwright` and run "
                "`playwright install chromium`."
            ) from exc

        session_config = build_browser_session_config(self.profile_dir)
        async with async_playwright() as playwright:
            if session_config["mode"] == "cdp":
                browser = await playwright.chromium.connect_over_cdp(session_config["cdp_url"])
                try:
                    context = browser.contexts[0] if browser.contexts else await browser.new_context(
                        locale="zh-CN",
                        viewport={"width": 1440, "height": 1080},
                        user_agent=session_config["user_agent"],
                        extra_http_headers=session_config["extra_http_headers"],
                    )
                    yield context
                finally:
                    await browser.close()
                return

            self.profile_dir.mkdir(parents=True, exist_ok=True)
            if session_config.get("sync_system_profile") and session_config.get("profile_source_root"):
                sync_browser_profile(session_config["profile_source_root"], self.profile_dir)
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                channel=session_config["channel"],
                locale="zh-CN",
                viewport={"width": 1440, "height": 1080},
                user_agent=session_config["user_agent"],
                extra_http_headers=session_config["extra_http_headers"],
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--lang=zh-CN",
                ],
            )
            try:
                yield context
            finally:
                await context.close()

    async def _open_search_page(self, page: Any, platform: str, query: str) -> None:
        if platform == "jd":
            url = f"https://search.jd.com/Search?keyword={quote_plus(query)}"
        elif platform == "taobao":
            url = f"https://s.taobao.com/search?q={quote_plus(query)}"
        else:
            raise RuntimeError(f"Unsupported ecommerce platform: {platform}")
        await self._goto_and_wait(page, url)

    async def _open_xhs_search(self, page: Any, query: str) -> None:
        url = f"https://www.xiaohongshu.com/search_result?keyword={quote_plus(query)}&source=web_explore_feed"
        await self._goto_and_wait(page, url)

    async def _goto_and_wait(self, page: Any, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=5000)
        await asyncio.sleep(1)

    async def _lazy_scroll(self, page: Any, rounds: int | None = None) -> None:
        total_rounds = self.scroll_rounds if rounds is None else rounds
        for _ in range(max(total_rounds, 0)):
            await page.mouse.wheel(0, 1600)
            await asyncio.sleep(0.8)

    async def _capture_relevant_response_text(
        self,
        response: Any,
        platform: str,
        response_texts: list[str],
    ) -> None:
        url = response.url.lower()
        if platform == "taobao" and TAOBAO_RESPONSE_MARKER in url:
            with contextlib.suppress(Exception):
                response_texts.append(await response.text())

    async def _body_text(self, page: Any) -> str:
        with contextlib.suppress(Exception):
            return await page.locator("body").inner_text(timeout=3000)
        return ""

    async def _extract_ecommerce_candidates(self, page: Any, platform: str, limit: int) -> list[dict[str, Any]]:
        if platform == "jd":
            return await page.evaluate(
                """(limit) => {
                    const nodes = Array.from(document.querySelectorAll('li.gl-item'));
                    return nodes.slice(0, limit).map((node) => {
                        const anchor = node.querySelector('.p-name a');
                        const title = (node.querySelector('.p-name em')?.innerText || anchor?.innerText || '').trim();
                        const price = (node.querySelector('.p-price strong i')?.innerText || node.querySelector('.p-price')?.innerText || '').trim();
                        const shop = (node.querySelector('.p-shop a')?.innerText || '').trim();
                        const href = anchor?.href || '';
                        return { title, price, shop_name: shop, url: href, platform: 'jd' };
                    }).filter((item) => item.title);
                }""",
                limit,
            )

        return await page.evaluate(
            """(limit) => {
                const cardSelectors = [
                    'a[href*="item.taobao.com"]',
                    'a[href*="detail.tmall.com"]',
                    '[data-index]',
                    'div[class*="doubleCardWrapper"]',
                    'div[class*="Card--doubleCardWrapper"]',
                    '.item'
                ];
                let nodes = [];
                for (const selector of cardSelectors) {
                    nodes = Array.from(document.querySelectorAll(selector));
                    if (nodes.length) break;
                }
                return nodes.slice(0, limit).map((node) => {
                    const anchor = node.tagName === 'A' ? node : (
                        node.querySelector('a[href*="item.taobao.com"], a[href*="detail.tmall.com"], a[href*="item.htm"]')
                        || node.querySelector('a')
                    );
                    const host = node.tagName === 'A' ? node.parentElement || node : node;
                    const title = (host.querySelector('[class*="title"]')?.innerText || anchor?.innerText || '').replace(/\\s+/g, ' ').trim();
                    const price = (host.querySelector('[class*="price"]')?.innerText || '').replace(/[^0-9.]/g, '').trim();
                    const shop = (host.querySelector('[class*="shop"]')?.innerText || host.querySelector('[class*="seller"]')?.innerText || '').replace(/\\s+/g, ' ').trim();
                    const href = anchor?.href || '';
                    return { title, price, shop_name: shop, url: href, platform: 'taobao' };
                }).filter((item) => item.title);
            }""",
            limit,
        )

    async def _extract_xhs_search_results(self, page: Any, limit: int) -> list[dict[str, Any]]:
        raw_results = await page.evaluate(
            """(limit) => {
                const nodes = Array.from(document.querySelectorAll(
                    'a[href*="/explore/"], a[href*="/discovery/item/"], a[href*="/search_result/"]'
                ));
                const results = [];
                for (const node of nodes) {
                    const href = node.href || '';
                    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                    const className = typeof node.className === 'string' ? node.className : '';
                    if (!href) continue;
                    results.push({
                        url: href.startsWith('http') ? href : `https://www.xiaohongshu.com${href}`,
                        title: text.slice(0, 60),
                        text: text,
                        class_name: className,
                    });
                    if (results.length >= limit * 8) break;
                }
                return results;
            }""",
            limit,
        )
        return normalize_xhs_search_candidates(raw_results, limit=limit)

    async def _extract_xhs_note_detail(self, page: Any) -> dict[str, Any]:
        return await page.evaluate(
            """() => {
                const noteTextCandidates = [
                    '#detail-desc',
                    '[class*="note-content"]',
                    '[class*="desc"]',
                    'article'
                ];
                let text = '';
                for (const selector of noteTextCandidates) {
                    const node = document.querySelector(selector);
                    if (node?.innerText) {
                        text = node.innerText.replace(/\\s+/g, ' ').trim();
                        if (text) break;
                    }
                }

                const commentSelectors = [
                    '[class*="comment-item"]',
                    '[class*="CommentItem"]',
                    '[class*="comment-content"]'
                ];
                let commentNodes = [];
                for (const selector of commentSelectors) {
                    commentNodes = Array.from(document.querySelectorAll(selector));
                    if (commentNodes.length) break;
                }

                return {
                    text,
                    comments: commentNodes.slice(0, 20).map((node) => ({
                        text: (node.innerText || '').replace(/\\s+/g, ' ').trim(),
                    })).filter((item) => item.text),
                };
            }""",
        )

    def _dedupe_candidates(self, items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            title = re.sub(r"\s+", " ", str(item.get("title", "")).strip())
            if not title:
                continue
            url = str(item.get("url", "")).strip()
            key = f"{title.lower()}|{url}"
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "title": title,
                    "price": str(item.get("price", "")).strip(),
                    "shop_name": str(item.get("shop_name", "")).strip(),
                    "url": url,
                    "platform": str(item.get("platform", "")).strip() or "search",
                }
            )
            if len(normalized) >= limit:
                break
        return normalized
