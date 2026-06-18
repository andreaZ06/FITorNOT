# Playwright Domestic Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder domestic recall fetchers with a real Playwright-backed browser adapter for JD/Taobao product recall and Xiaohongshu note/comment recall.

**Architecture:** Keep LangGraph and `main.py` as the orchestration boundary, but move browser automation into a focused Python helper module. `main.py` will call adapter-backed async functions, and the adapter will use lazy Playwright imports plus persistent browser profiles so login state can survive across runs.

**Tech Stack:** Python 3, FastAPI, LangGraph, Playwright async API, unittest, PowerShell

---

### Task 1: Define the browser adapter contract and red tests

**Files:**
- Create: `C:\W\product\analysis agent\review-pitfall-checker-v2\domestic_browser.py`
- Modify: `C:\W\product\analysis agent\review-pitfall-checker-v2\tests\test_main_decision_api.py`
- Test: `C:\W\product\analysis agent\review-pitfall-checker-v2\tests\test_main_decision_api.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_fetch_ecommerce_candidates_uses_registered_browser_adapter(self):
        module = importlib.import_module("main")

        class FakeAdapter:
            async def fetch_ecommerce_candidates(self, query, category, limit=20):
                return [{"title": "Anker 10000mAh Nano", "price": "149", "shop_name": "Anker旗舰店", "url": "https://item.jd.com/1.html", "platform": "jd"}]

        module.set_domestic_browser_adapter(FakeAdapter())

        result = asyncio.run(module.fetch_ecommerce_candidates("Anker 10000", module.SUPPORTED_CATEGORIES[0], limit=20))

        self.assertEqual(result[0]["title"], "Anker 10000mAh Nano")

    def test_fetch_xiaohongshu_feedback_uses_registered_browser_adapter(self):
        module = importlib.import_module("main")

        class FakeAdapter:
            async def fetch_xiaohongshu_feedback(self, queries, limit=10):
                return [{"query": queries[0], "notes": [{"text": "说能上飞机，但有点热"}], "comments": [{"text": "我带过，安检能过"}]}]

        module.set_domestic_browser_adapter(FakeAdapter())

        result = asyncio.run(module.fetch_xiaohongshu_feedback(["Anker 10000mAh Nano 避雷"], limit=10))

        self.assertEqual(result[0]["query"], "Anker 10000mAh Nano 避雷")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_fetch_ecommerce_candidates_uses_registered_browser_adapter tests.test_main_decision_api.MainDecisionApiTest.test_fetch_xiaohongshu_feedback_uses_registered_browser_adapter`

Expected: `FAIL` because `main.py` does not yet expose `set_domestic_browser_adapter` and the fetch functions still raise the placeholder runtime error.

- [ ] **Step 3: Write the minimal implementation**

```python
_DOMESTIC_BROWSER_ADAPTER = None

def set_domestic_browser_adapter(adapter):
    global _DOMESTIC_BROWSER_ADAPTER
    _DOMESTIC_BROWSER_ADAPTER = adapter

async def fetch_ecommerce_candidates(query: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
    if _DOMESTIC_BROWSER_ADAPTER is None:
        raise RuntimeError("Playwright browser adapter is unavailable")
    return await _DOMESTIC_BROWSER_ADAPTER.fetch_ecommerce_candidates(query, category, limit=limit)

async def fetch_xiaohongshu_feedback(queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
    if _DOMESTIC_BROWSER_ADAPTER is None:
        raise RuntimeError("Playwright browser adapter is unavailable")
    return await _DOMESTIC_BROWSER_ADAPTER.fetch_xiaohongshu_feedback(queries, limit=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_fetch_ecommerce_candidates_uses_registered_browser_adapter tests.test_main_decision_api.MainDecisionApiTest.test_fetch_xiaohongshu_feedback_uses_registered_browser_adapter`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add review-pitfall-checker-v2/tests/test_main_decision_api.py review-pitfall-checker-v2/main.py
git commit -m "test: cover domestic browser adapter contract"
```

### Task 2: Implement the real Playwright adapter

**Files:**
- Create: `C:\W\product\analysis agent\review-pitfall-checker-v2\domestic_browser.py`
- Modify: `C:\W\product\analysis agent\review-pitfall-checker-v2\main.py`
- Test: `C:\W\product\analysis agent\review-pitfall-checker-v2\tests\test_main_decision_api.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_default_domestic_browser_adapter_uses_factory_when_playwright_is_available(self):
        module = importlib.import_module("main")
        fake_adapter = object()
        module.build_default_domestic_browser_adapter = lambda: fake_adapter
        module.set_domestic_browser_adapter(None)

        adapter = module.get_domestic_browser_adapter()

        self.assertIs(adapter, fake_adapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_default_domestic_browser_adapter_uses_factory_when_playwright_is_available`

Expected: `FAIL` because `get_domestic_browser_adapter` and `build_default_domestic_browser_adapter` do not yet exist.

- [ ] **Step 3: Write minimal implementation**

```python
def get_domestic_browser_adapter():
    global _DOMESTIC_BROWSER_ADAPTER
    if _DOMESTIC_BROWSER_ADAPTER is None:
        _DOMESTIC_BROWSER_ADAPTER = build_default_domestic_browser_adapter()
    return _DOMESTIC_BROWSER_ADAPTER
```

Then implement `domestic_browser.py` with:
- `PlaywrightDomesticBrowserAdapter`
- lazy `playwright.async_api` import
- persistent Chromium profile directory
- `fetch_ecommerce_candidates()` for JD and Taobao list pages
- `fetch_xiaohongshu_feedback()` for Xiaohongshu search and note/comment extraction

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_default_domestic_browser_adapter_uses_factory_when_playwright_is_available`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add review-pitfall-checker-v2/domestic_browser.py review-pitfall-checker-v2/main.py review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "feat: add Playwright domestic recall adapter"
```

### Task 3: Wire runtime dependencies and docs

**Files:**
- Modify: `C:\W\product\analysis agent\review-pitfall-checker-v2\requirements.txt`
- Modify: `C:\W\product\analysis agent\review-pitfall-checker-v2\README.md`
- Test: `C:\W\product\analysis agent\review-pitfall-checker-v2\tests\test_main_decision_api.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_browser_unavailable_error_mentions_playwright_installation(self):
        module = importlib.import_module("main")
        module.set_domestic_browser_adapter(None)
        module.build_default_domestic_browser_adapter = lambda: None

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(module.fetch_ecommerce_candidates("Anker 10000", module.SUPPORTED_CATEGORIES[0], limit=20))

        self.assertIn("pip install playwright", str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_browser_unavailable_error_mentions_playwright_installation`

Expected: `FAIL` because the current error string does not explain how to enable browser automation.

- [ ] **Step 3: Write the minimal implementation**

```python
raise RuntimeError(
    "Playwright browser adapter is unavailable. Install it with `pip install playwright` and run `playwright install chromium`."
)
```

Also update `requirements.txt` with `playwright>=1.54.0` and add README notes for:
- profile dir env var
- first-time browser install
- manual login persistence for Xiaohongshu / Taobao

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_browser_unavailable_error_mentions_playwright_installation`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add review-pitfall-checker-v2/requirements.txt review-pitfall-checker-v2/README.md review-pitfall-checker-v2/main.py review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "docs: explain Playwright domestic recall setup"
```

### Task 4: Run focused and broad verification

**Files:**
- Modify: none expected
- Test: `C:\W\product\analysis agent\review-pitfall-checker-v2\tests\test_main_decision_api.py`

- [ ] **Step 1: Run focused Python tests**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_fetch_ecommerce_candidates_uses_registered_browser_adapter tests.test_main_decision_api.MainDecisionApiTest.test_fetch_xiaohongshu_feedback_uses_registered_browser_adapter tests.test_main_decision_api.MainDecisionApiTest.test_default_domestic_browser_adapter_uses_factory_when_playwright_is_available tests.test_main_decision_api.MainDecisionApiTest.test_browser_unavailable_error_mentions_playwright_installation`

Expected: `OK`

- [ ] **Step 2: Run the Python subproject suite**

Run: `python -m unittest discover -s tests`

Expected: `OK`

- [ ] **Step 3: Run repo verification**

Run: `npx pnpm test`
Expected: pass

Run: `npx pnpm lint`
Expected: pass with existing repository warnings only

Run: `npx pnpm typecheck`
Expected: pass

Run: `npx pnpm verify`
Expected: pass

- [ ] **Step 4: Commit**

```bash
git add review-pitfall-checker-v2/main.py review-pitfall-checker-v2/domestic_browser.py review-pitfall-checker-v2/requirements.txt review-pitfall-checker-v2/README.md review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "feat: enable Playwright domestic recall flow"
git push origin main
```
