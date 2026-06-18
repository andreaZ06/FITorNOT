# FITorNOT Domestic Recall Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Bright Data-first fetch path with a domestic browser automation-first recall flow that gathers lightweight JD/Taobao candidates, reverse-searches Xiaohongshu with negative probes, and keeps graceful fallback behavior.

**Architecture:** Keep the five-node LangGraph shape intact and refactor the fetch layer inside `review-pitfall-checker-v2/main.py`. The retriever will still build a coarse ecommerce query, but the fetch node will first collect ecommerce candidates, normalize the top models, derive Xiaohongshu probe queries from those candidates, and only use Bright Data as an optional fallback when the domestic adapters are unavailable.

**Tech Stack:** FastAPI, LangGraph, Pydantic, optional Playwright/DrissionPage browser automation hooks, existing DeepSeek bridge, existing local cleaning pipeline.

---

### Task 1: Lock the New Recall Behavior in Tests

**Files:**
- Modify: `review-pitfall-checker-v2/tests/test_main_decision_api.py`
- Test: `review-pitfall-checker-v2/tests/test_main_decision_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_domestic_fetch_node_builds_xhs_queries_from_top_ecommerce_candidates(self):
    module = importlib.import_module("main")
    slots = module.IntentSlots(category=module.SUPPORTED_CATEGORIES[0], brand="Anker", model="10000", urls=[])
    retrieval_plan = module.build_local_retrieval_plan(slots)

    async def fake_ecommerce(query, category, limit):
        return [
            {"title": "Anker 10000mAh Nano", "price": "149", "shop_name": "Anker旗舰店", "url": "https://item.jd.com/1.html", "platform": "jd"},
            {"title": "Anker 20000mAh PowerCore", "price": "229", "shop_name": "Anker京东自营", "url": "https://item.jd.com/2.html", "platform": "jd"},
        ]

    async def fake_xhs(queries, limit):
        return [{"query": queries[0], "notes": [], "comments": []}]

    module.fetch_ecommerce_candidates = fake_ecommerce
    module.fetch_xiaohongshu_feedback = fake_xhs
    result = asyncio.run(
        module.domestic_recall_fetch(
            module.DomesticRecallInput(
                user_raw_input="我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
                slots=slots,
                retrieval_plan=retrieval_plan,
                use_mock=False,
            )
        )
    )

    self.assertIn("Anker 10000mAh Nano", result.ecommerce_candidates[0]["title"])
    self.assertTrue(any("避雷" in query or "缺点" in query or "真实测评" in query for query in result.generated_xhs_queries))


def test_domestic_fetch_node_falls_back_cleanly_when_local_browser_tools_are_missing(self):
    module = importlib.import_module("main")
    slots = module.IntentSlots(category=module.SUPPORTED_CATEGORIES[0], brand="Anker", model="10000", urls=[])
    retrieval_plan = module.build_local_retrieval_plan(slots)

    async def broken_ecommerce(query, category, limit):
        raise RuntimeError("Playwright and DrissionPage are unavailable")

    module.fetch_ecommerce_candidates = broken_ecommerce
    result = asyncio.run(
        module.domestic_recall_fetch(
            module.DomesticRecallInput(
                user_raw_input="我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
                slots=slots,
                retrieval_plan=retrieval_plan,
                use_mock=False,
            )
        )
    )

    self.assertEqual(result.fetch_status, "partial_failed")
    self.assertTrue(result.blocked_sources)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_builds_xhs_queries_from_top_ecommerce_candidates tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_falls_back_cleanly_when_local_browser_tools_are_missing`

Expected: FAIL because `DomesticRecallInput` / `domestic_recall_fetch` do not exist yet.

- [ ] **Step 3: Commit the red test checkpoint**

```bash
git add review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "test: cover domestic recall fetch flow"
```

### Task 2: Add Domestic Recall Data Contracts

**Files:**
- Modify: `review-pitfall-checker-v2/main.py`
- Test: `review-pitfall-checker-v2/tests/test_main_decision_api.py`

- [ ] **Step 1: Write the minimal data models needed by the new fetch path**

```python
class DomesticRecallInput(BaseModel):
    user_raw_input: str
    slots: IntentSlots
    retrieval_plan: RetrievalPlan
    use_mock: bool = False


class DomesticRecallOutput(BaseModel):
    raw_data: RawPlatformData
    ecommerce_candidates: list[dict[str, Any]] = Field(default_factory=list)
    generated_xhs_queries: list[str] = Field(default_factory=list)
    xiaohongshu_hits: list[dict[str, Any]] = Field(default_factory=list)
    ecommerce_data: list[dict[str, Any]] = Field(default_factory=list)
    xiaohongshu_data: list[dict[str, Any]] = Field(default_factory=list)
    blocked_sources: list[dict[str, str]] = Field(default_factory=list)
    fetch_status: str = "success"
```

- [ ] **Step 2: Run the targeted tests and confirm they still fail for missing logic**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_builds_xhs_queries_from_top_ecommerce_candidates -v`

Expected: FAIL, now because `domestic_recall_fetch` is still missing.

- [ ] **Step 3: Commit the contract additions**

```bash
git add review-pitfall-checker-v2/main.py
git commit -m "feat: add domestic recall data contracts"
```

### Task 3: Implement the Domestic Ecommerce Candidate Recall

**Files:**
- Modify: `review-pitfall-checker-v2/main.py`
- Test: `review-pitfall-checker-v2/tests/test_main_decision_api.py`

- [ ] **Step 1: Add the lightweight ecommerce candidate fetch adapter and normalizer**

```python
async def fetch_ecommerce_candidates(query: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
    raise RuntimeError("Playwright/DrissionPage adapters are not configured")


def normalize_ecommerce_candidates(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        key = re.sub(r"\\s+", " ", title.lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "title": title,
                "price": str(item.get("price", "")).strip(),
                "shop_name": str(item.get("shop_name", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "platform": str(item.get("platform", "search")).strip(),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized
```

- [ ] **Step 2: Run the candidate-recall test and confirm it still fails on the missing XHS step**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_builds_xhs_queries_from_top_ecommerce_candidates -v`

Expected: FAIL because the orchestrator still does not build probe queries.

- [ ] **Step 3: Commit the ecommerce recall helpers**

```bash
git add review-pitfall-checker-v2/main.py
git commit -m "feat: add ecommerce candidate normalization"
```

### Task 4: Implement XHS Probe Generation and Orchestration

**Files:**
- Modify: `review-pitfall-checker-v2/main.py`
- Test: `review-pitfall-checker-v2/tests/test_main_decision_api.py`

- [ ] **Step 1: Add the XHS query builder and orchestration entry point**

```python
def build_candidate_xhs_queries(candidates: list[dict[str, Any]], category: str) -> list[str]:
    negative_terms = {
        "充电宝": ["避雷", "缺点", "真实测评"],
        "面膜": ["避雷", "刺痛", "缺点"],
        "狗粮": ["避雷", "软便", "缺点"],
        "其他": ["避雷", "真实测评", "缺点"],
    }[category]
    queries: list[str] = []
    for candidate in candidates[:5]:
        title = candidate["title"]
        for suffix in negative_terms[:2]:
            queries.append(f"{title} {suffix}")
    return queries[:10]


async def fetch_xiaohongshu_feedback(queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
    raise RuntimeError("Xiaohongshu browser adapter is not configured")


async def domestic_recall_fetch(payload: DomesticRecallInput) -> DomesticRecallOutput:
    blocked_sources: list[dict[str, str]] = []
    try:
        raw_candidates = await fetch_ecommerce_candidates(payload.retrieval_plan.ecommerce_query, payload.slots.category, limit=20)
        candidates = normalize_ecommerce_candidates(raw_candidates, limit=5)
    except Exception as exc:
        candidates = []
        blocked_sources.append({"source": "domestic_ecommerce", "reason": str(exc)})

    generated_xhs_queries = build_candidate_xhs_queries(candidates, payload.slots.category) or list(payload.retrieval_plan.xiaohongshu_queries)
    try:
        xhs_hits = await fetch_xiaohongshu_feedback(generated_xhs_queries, limit=10)
    except Exception as exc:
        xhs_hits = []
        blocked_sources.append({"source": "xiaohongshu", "reason": str(exc)})

    return _build_domestic_fetch_output(payload, candidates, generated_xhs_queries, xhs_hits, blocked_sources)
```

- [ ] **Step 2: Run both domestic recall tests and confirm they pass**

Run: `python -m unittest tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_builds_xhs_queries_from_top_ecommerce_candidates tests.test_main_decision_api.MainDecisionApiTest.test_domestic_fetch_node_falls_back_cleanly_when_local_browser_tools_are_missing`

Expected: PASS

- [ ] **Step 3: Commit the orchestration**

```bash
git add review-pitfall-checker-v2/main.py review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "feat: orchestrate domestic ecommerce and xiaohongshu recall"
```

### Task 5: Switch the Graph to the New Fetch Layer and Preserve Fallbacks

**Files:**
- Modify: `review-pitfall-checker-v2/main.py`
- Test: `review-pitfall-checker-v2/tests/test_main_decision_api.py`

- [ ] **Step 1: Route `retriever_node` through the domestic recall path first**

```python
async def retriever_node(state: DecisionState) -> DecisionState:
    ...
    state["retrieval_plan"] = retrieval_plan
    state["user_bound_urls"] = list(payload.slots.urls)
    recall_output = await domestic_recall_fetch(
        DomesticRecallInput(
            user_raw_input=state["user_raw_input"],
            slots=state["slots"],
            retrieval_plan=retrieval_plan,
            use_mock=payload.use_mock,
        )
    )
    state["raw_data"] = recall_output.raw_data
    state["ecommerce_data"] = recall_output.ecommerce_data
    state["xiaohongshu_data"] = recall_output.xiaohongshu_data
    state["blocked_sources"] = recall_output.blocked_sources
    state["fetch_status"] = recall_output.fetch_status
    return state
```

- [ ] **Step 2: Run the full FITorNOT Python test suite**

Run: `python -m unittest discover -s tests`

Expected: PASS

- [ ] **Step 3: Commit the graph switch**

```bash
git add review-pitfall-checker-v2/main.py review-pitfall-checker-v2/tests/test_main_decision_api.py
git commit -m "refactor: switch FITorNOT to domestic recall flow"
```

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run repository verification commands**

Run: `npx pnpm test`
Expected: PASS

Run: `npx pnpm lint`
Expected: PASS with the repo's pre-existing warnings only

Run: `npx pnpm typecheck`
Expected: PASS

Run: `npx pnpm verify`
Expected: PASS

- [ ] **Step 2: Push the scoped changes**

```bash
git add review-pitfall-checker-v2/main.py review-pitfall-checker-v2/tests/test_main_decision_api.py docs/superpowers/plans/2026-06-18-domestic-recall-flow.md
git commit -m "feat: refactor FITorNOT to domestic recall architecture"
git push origin main
```
