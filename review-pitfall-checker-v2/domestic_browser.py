from __future__ import annotations

import asyncio
import contextlib
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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

    async def fetch_ecommerce_candidates(self, query: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        async with self._browser_context() as context:
            collected: list[dict[str, Any]] = []
            for platform in self.ecommerce_platforms:
                page = await context.new_page()
                try:
                    await self._open_search_page(page, platform, query)
                    await self._lazy_scroll(page)
                    collected.extend(await self._extract_ecommerce_candidates(page, platform, limit))
                finally:
                    await page.close()
            return self._dedupe_candidates(collected, limit)

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
                            "comments": comments[:20],
                            "platform": "xiaohongshu",
                        }
                    )

                if len(hits) >= limit:
                    break
        return hits[:limit]

    @contextlib.asynccontextmanager
    async def _browser_context(self):
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # pragma: no cover - depends on local runtime
            raise RuntimeError(
                "Playwright browser adapter is unavailable. Install it with `pip install playwright` and run "
                "`playwright install chromium`."
            ) from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                locale="zh-CN",
                viewport={"width": 1440, "height": 1080},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
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
                    const anchor = node.querySelector('a[href*="item.taobao.com"], a[href*="detail.tmall.com"], a[href*="item.htm"]') || node.querySelector('a');
                    const title = (node.querySelector('[class*="title"]')?.innerText || anchor?.innerText || '').replace(/\\s+/g, ' ').trim();
                    const price = (node.querySelector('[class*="price"]')?.innerText || '').replace(/[^0-9.]/g, '').trim();
                    const shop = (node.querySelector('[class*="shop"]')?.innerText || node.querySelector('[class*="seller"]')?.innerText || '').replace(/\\s+/g, ' ').trim();
                    const href = anchor?.href || '';
                    return { title, price, shop_name: shop, url: href, platform: 'taobao' };
                }).filter((item) => item.title);
            }""",
            limit,
        )

    async def _extract_xhs_search_results(self, page: Any, limit: int) -> list[dict[str, Any]]:
        return await page.evaluate(
            """(limit) => {
                const nodes = Array.from(document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]'));
                const results = [];
                for (const node of nodes) {
                    const href = node.href || '';
                    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!href || !text) continue;
                    results.push({
                        url: href.startsWith('http') ? href : `https://www.xiaohongshu.com${href}`,
                        title: text.slice(0, 60),
                        text: text,
                    });
                    if (results.length >= limit) break;
                }
                return results;
            }""",
            limit,
        )

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
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "title": title,
                    "price": str(item.get("price", "")).strip(),
                    "shop_name": str(item.get("shop_name", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "platform": str(item.get("platform", "")).strip() or "search",
                }
            )
            if len(normalized) >= limit:
                break
        return normalized
