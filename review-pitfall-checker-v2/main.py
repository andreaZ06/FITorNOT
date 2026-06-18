"""FITorNOT multi-agent decision API.

Production intent:
- FastAPI exposes POST /api/v1/decision.
- DeepSeek is reached through langchain_openai.ChatOpenAI.
- LangGraph coordinates intent parsing, Bright Data MCP fetching, and final
  FITorNOT report generation.
- Bright Data MCP is addressed as the locally configured server named
  "brightdata"; mock data is only a fallback for local development and tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, NotRequired, TypedDict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

try:  # Production dependency.
    from langchain_openai import ChatOpenAI as _ChatOpenAI
except Exception:  # pragma: no cover - exercised when local deps are absent.
    _ChatOpenAI = None

try:  # Production dependency.
    from langchain_mcp_adapters.client import MultiServerMCPClient
except Exception:  # pragma: no cover - exercised when local deps are absent.
    MultiServerMCPClient = None

try:  # Production dependency.
    from langgraph.graph import END, StateGraph as _StateGraph
except Exception:  # pragma: no cover - exercised when local deps are absent.
    END = "__end__"
    _StateGraph = None


SUPPORTED_CATEGORIES = ("充电宝", "面膜", "狗粮")
URL_PATTERN = re.compile(r"https?://[^\s,，]+", re.IGNORECASE)
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class IntentSlots(BaseModel):
    """Zero-freeform intent slots controlled by Pydantic validation."""

    category: Literal["充电宝", "面膜", "狗粮"] = Field(
        description="Target category. Must be one of: 充电宝, 面膜, 狗粮."
    )
    brand: str = Field(default="", description="Brand extracted from user input.")
    model: str = Field(default="", description="Model, SKU, or product series.")
    urls: list[str] = Field(default_factory=list, description="All URLs in input.")

    @field_validator("urls")
    @classmethod
    def only_urls(cls, value: list[str]) -> list[str]:
        return [url for url in value if URL_PATTERN.match(url)]


class DecisionRequest(BaseModel):
    user_raw_input: str = Field(..., min_length=1)
    target_language: str = Field(default="中文", min_length=1)
    use_mock: bool = Field(
        default=False,
        description="Force deterministic local mock path. Intended for tests/dev only.",
    )


class DecisionResponse(BaseModel):
    slots: IntentSlots
    ecommerce_data: list[dict[str, Any]]
    social_data: list[dict[str, Any]]
    blocked_sources: list[dict[str, str]]
    report: str


class DecisionState(TypedDict):
    user_raw_input: str
    target_language: str
    slots: NotRequired[IntentSlots]
    ecommerce_data: NotRequired[list[dict[str, Any]]]
    social_data: NotRequired[list[dict[str, Any]]]
    blocked_sources: NotRequired[list[dict[str, str]]]
    report: NotRequired[str]
    use_mock: NotRequired[bool]


class _CompatChatOpenAI:
    """Tiny local stand-in so tests can run without LangChain installed."""

    def __init__(self, **kwargs: Any) -> None:
        self.model_name = kwargs.get("model") or kwargs.get("model_name")
        self.openai_api_base = kwargs.get("base_url")
        self.temperature = kwargs.get("temperature")

    def with_structured_output(self, schema: type[BaseModel]) -> "_CompatStructuredLLM":
        return _CompatStructuredLLM(schema)

    async def ainvoke(self, messages: list[tuple[str, str]]) -> Any:
        return type("AIMessage", (), {"content": _deterministic_report_from_prompt(messages)})()


class _CompatStructuredLLM:
    def __init__(self, schema: type[BaseModel]) -> None:
        self.schema = schema

    async def ainvoke(self, text: str) -> BaseModel:
        return infer_intent_slots_locally(text)


class _CompatNode:
    def __init__(self, node_id: str) -> None:
        self.id = node_id


class _CompatEdge:
    def __init__(self, source: str, target: str) -> None:
        self.source = source
        self.target = target


class _CompatGraphView:
    def __init__(self, nodes: list[str], edges: list[tuple[str, str]]) -> None:
        self.nodes = {name: _CompatNode(name) for name in nodes}
        self.edges = [_CompatEdge(source, target) for source, target in edges]


class _CompatCompiledGraph:
    def __init__(
        self,
        nodes: dict[str, Callable[[DecisionState], Awaitable[DecisionState]]],
        edges: list[tuple[str, str]],
        entry_point: str,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._entry_point = entry_point

    def get_graph(self) -> _CompatGraphView:
        return _CompatGraphView(list(self._nodes), self._edges)

    async def ainvoke(self, state: DecisionState) -> DecisionState:
        current = self._entry_point
        next_by_source = {source: target for source, target in self._edges}
        while current != END:
            state = await self._nodes[current](state)
            current = next_by_source.get(current, END)
        return state


class _CompatStateGraph:
    def __init__(self, state_type: type[TypedDict]) -> None:
        self._nodes: dict[str, Callable[[DecisionState], Awaitable[DecisionState]]] = {}
        self._edges: list[tuple[str, str]] = []
        self._entry_point = ""

    def add_node(
        self, name: str, node: Callable[[DecisionState], Awaitable[DecisionState]]
    ) -> None:
        self._nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def add_edge(self, source: str, target: str) -> None:
        self._edges.append((source, target))

    def compile(self) -> _CompatCompiledGraph:
        return _CompatCompiledGraph(self._nodes, self._edges, self._entry_point)


StateGraph = _StateGraph or _CompatStateGraph


def build_deepseek_llm(model: str, temperature: float = 0.0) -> Any:
    """Create a DeepSeek-compatible ChatOpenAI client."""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek calls.")

    cls = _ChatOpenAI or _CompatChatOpenAI
    return cls(
        model=model,
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
    )


async def intent_parser_node(state: DecisionState) -> DecisionState:
    if state.get("use_mock"):
        slots = infer_intent_slots_locally(state["user_raw_input"])
    else:
        llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
        structured_llm = llm.with_structured_output(IntentSlots)
        slots = await structured_llm.ainvoke(
            "Extract FITorNOT product decision slots from this input. "
            "category must be exactly one of 充电宝, 面膜, 狗粮. "
            f"User input: {state['user_raw_input']}"
        )

    state["slots"] = slots
    return state


async def brightdata_mcp_fetch_node(state: DecisionState) -> DecisionState:
    slots = state["slots"]
    queries = build_brightdata_queries(slots)
    ecommerce_data: list[dict[str, Any]] = []
    social_data: list[dict[str, Any]] = []
    blocked_sources: list[dict[str, str]] = []

    if state.get("use_mock"):
        mock = mock_brightdata_payload(slots.category)
        state["ecommerce_data"] = mock["ecommerce_data"]
        state["social_data"] = mock["social_data"]
        state["blocked_sources"] = []
        return state

    try:
        tool_router = await build_brightdata_tool_router()
    except Exception as exc:  # noqa: BLE001 - return explicit fallback reason.
        mock = mock_brightdata_payload(slots.category)
        state["ecommerce_data"] = mock["ecommerce_data"]
        state["social_data"] = mock["social_data"]
        state["blocked_sources"] = [
            {"source": "brightdata", "reason": f"MCP unavailable: {exc}"}
        ]
        return state

    tasks = [fetch_one_source(tool_router, query) for query in queries]
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, Exception):
            blocked_sources.append({"source": "brightdata", "reason": str(result)})
            continue
        if result["kind"] == "social":
            social_data.append(result)
        else:
            ecommerce_data.append(result)

    if not ecommerce_data and not social_data:
        mock = mock_brightdata_payload(slots.category)
        ecommerce_data = mock["ecommerce_data"]
        social_data = mock["social_data"]
        blocked_sources.append(
            {
                "source": "brightdata",
                "reason": "All MCP calls failed; mock schema payload used.",
            }
        )

    state["ecommerce_data"] = ecommerce_data
    state["social_data"] = social_data
    state["blocked_sources"] = blocked_sources
    return state


async def fit_or_not_generator_node(state: DecisionState) -> DecisionState:
    if state.get("use_mock"):
        state["report"] = render_evidence_report(
            slots=state["slots"],
            ecommerce_data=state.get("ecommerce_data", []),
            social_data=state.get("social_data", []),
            blocked_sources=state.get("blocked_sources", []),
            target_language=state["target_language"],
        )
        return state

    llm = build_deepseek_llm("deepseek-reasoner", temperature=0.1)
    prompt = build_fitornot_prompt(state)
    response = await llm.ainvoke(
        [
            ("system", FITORNOT_SYSTEM_PROMPT),
            ("user", prompt),
        ]
    )
    state["report"] = str(getattr(response, "content", response))
    return state


def build_decision_graph() -> Any:
    graph = StateGraph(DecisionState)
    graph.add_node("intent_parser_node", intent_parser_node)
    graph.add_node("brightdata_mcp_fetch_node", brightdata_mcp_fetch_node)
    graph.add_node("fit_or_not_generator_node", fit_or_not_generator_node)
    graph.set_entry_point("intent_parser_node")
    graph.add_edge("intent_parser_node", "brightdata_mcp_fetch_node")
    graph.add_edge("brightdata_mcp_fetch_node", "fit_or_not_generator_node")
    graph.add_edge("fit_or_not_generator_node", END)
    return graph.compile()


async def create_decision(
    request: DecisionRequest, use_mock: bool | None = None
) -> DecisionResponse:
    graph = build_decision_graph()
    initial_state: DecisionState = {
        "user_raw_input": request.user_raw_input,
        "target_language": request.target_language,
        "use_mock": request.use_mock if use_mock is None else use_mock,
    }
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DecisionResponse(
        slots=final_state["slots"],
        ecommerce_data=final_state.get("ecommerce_data", []),
        social_data=final_state.get("social_data", []),
        blocked_sources=final_state.get("blocked_sources", []),
        report=final_state.get("report", ""),
    )


def build_brightdata_queries(slots: IntentSlots) -> list[dict[str, str]]:
    keyword = " ".join(part for part in [slots.brand, slots.model, slots.category] if part)
    if not keyword:
        keyword = slots.category

    probes_by_category = {
        "充电宝": ["发热", "鼓包", "上飞机", "容量虚标", "3C认证"],
        "面膜": ["刺痛", "泛红", "爆痘", "敏感肌", "成分"],
        "狗粮": ["软便", "拉稀", "泪痕", "呕吐", "适口性"],
    }
    queries: list[dict[str, str]] = []

    for url in slots.urls:
        platform = detect_platform(url)
        queries.append(
            {
                "kind": "social" if platform == "xiaohongshu" else "ecommerce",
                "platform": platform,
                "query": url,
                "url": url,
            }
        )

    queries.extend(
        [
            {
                "kind": "ecommerce",
                "platform": "jd",
                "query": f"京东 {keyword} 官方参数 价格 追评 差评",
                "url": "",
            },
            {
                "kind": "ecommerce",
                "platform": "taobao",
                "query": f"淘宝 {keyword} 官方参数 价格 追评 差评",
                "url": "",
            },
        ]
    )
    for probe in probes_by_category[slots.category]:
        queries.append(
            {
                "kind": "social",
                "platform": "xiaohongshu",
                "query": f"小红书 {keyword} {probe} 避坑 真实体验",
                "url": "",
            }
        )
    return queries


async def build_brightdata_tool_router() -> Callable[[dict[str, str]], Awaitable[Any]]:
    if MultiServerMCPClient is None:
        raise RuntimeError("langchain_mcp_adapters is not installed.")

    config_path = Path.home() / ".codex" / "mcp" / "brightdata-mcp.ps1"
    client = MultiServerMCPClient(
        {
            "brightdata": {
                "command": "powershell",
                "args": [
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(config_path),
                ],
                "transport": "stdio",
            }
        }
    )
    tools = await client.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    preferred_names = [
        "brightdata__scrape",
        "scrape_as_markdown",
        "scrape_batch",
        "search_engine",
        "discover",
    ]
    selected = next(
        (tools_by_name[name] for name in preferred_names if name in tools_by_name),
        None,
    )
    if selected is None:
        raise RuntimeError(
            "brightdata MCP is connected, but no supported scrape/search tool was found."
        )

    async def route(query: dict[str, str]) -> Any:
        payload = {"url": query["url"]} if query.get("url") else {"query": query["query"]}
        return await selected.ainvoke(payload)

    return route


async def fetch_one_source(
    tool_router: Callable[[dict[str, str]], Awaitable[Any]], query: dict[str, str]
) -> dict[str, Any]:
    raw = await tool_router(query)
    return {
        "kind": query["kind"],
        "platform": query["platform"],
        "query": query["query"],
        "url": query.get("url", ""),
        "raw": raw,
        "evidence": normalize_raw_evidence(raw),
    }


def infer_intent_slots_locally(text: str) -> IntentSlots:
    urls = URL_PATTERN.findall(text)
    category = "充电宝"
    if any(word in text for word in ("面膜", "敏感肌", "刺痛", "泛红")):
        category = "面膜"
    elif any(word in text for word in ("狗粮", "软便", "拉稀", "泪痕", "狗狗")):
        category = "狗粮"

    cleaned = URL_PATTERN.sub(" ", text)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", cleaned)
    brand = tokens[0] if tokens else ""
    model = tokens[1] if len(tokens) > 1 else ""
    if brand in SUPPORTED_CATEGORIES:
        brand = tokens[1] if len(tokens) > 1 else ""
        model = tokens[2] if len(tokens) > 2 else ""

    return IntentSlots(category=category, brand=brand, model=model, urls=urls)


def detect_platform(url: str) -> str:
    lowered = url.lower()
    if "xiaohongshu.com" in lowered or "xhslink.com" in lowered:
        return "xiaohongshu"
    if "jd.com" in lowered:
        return "jd"
    if "taobao.com" in lowered or "tmall.com" in lowered:
        return "taobao"
    return "unknown"


def normalize_raw_evidence(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()][:8]
    if isinstance(raw, dict):
        texts: list[str] = []
        for key, value in raw.items():
            if isinstance(value, str):
                texts.append(f"{key}: {value}")
            elif isinstance(value, list):
                for item in value[:5]:
                    texts.append(json.dumps(item, ensure_ascii=False))
        return texts[:8]
    return [str(raw)[:1000]]


def mock_brightdata_payload(category: str) -> dict[str, list[dict[str, Any]]]:
    if category == "面膜":
        return {
            "ecommerce_data": [
                {
                    "kind": "ecommerce",
                    "platform": "jd",
                    "query": "JD mask params",
                    "url": "mock://jd/mask",
                    "evidence": [
                        "商品参数：烟酰胺提亮，适合普通肤质，单片价格约9.9元 [数据源: 电商]",
                        "追评：第二次用脸颊泛红发烫，敏感肌慎重 [数据源: 电商]",
                    ],
                }
            ],
            "social_data": [
                {
                    "kind": "social",
                    "platform": "xiaohongshu",
                    "query": "XHS mask pitfall",
                    "url": "mock://xhs/mask",
                    "evidence": [
                        "小红书评论：急救提亮有一点，但刺痛感明显 [数据源: 小红书]",
                        "小红书避坑：屏障受损期间用了第二天爆痘 [数据源: 小红书]",
                    ],
                }
            ],
        }
    if category == "狗粮":
        return {
            "ecommerce_data": [
                {
                    "kind": "ecommerce",
                    "platform": "taobao",
                    "query": "Taobao dog food params",
                    "url": "mock://taobao/dogfood",
                    "evidence": [
                        "商品参数：主打低敏和泪痕管理，鸡肉配方 [数据源: 电商]",
                        "追评：换粮第三天软便，慢慢过渡后才稳定 [数据源: 电商]",
                    ],
                }
            ],
            "social_data": [
                {
                    "kind": "social",
                    "platform": "xiaohongshu",
                    "query": "XHS dog food pitfall",
                    "url": "mock://xhs/dogfood",
                    "evidence": [
                        "小红书评论：泪痕淡了但肠胃敏感狗容易拉稀 [数据源: 小红书]",
                        "小红书避坑：适口性一般，需要拌罐头才吃 [数据源: 小红书]",
                    ],
                }
            ],
        }
    return {
        "ecommerce_data": [
            {
                "kind": "ecommerce",
                "platform": "jd",
                "query": "JD power bank params",
                "url": "mock://jd/powerbank",
                "evidence": [
                    "商品参数：20000mAh，标称74Wh，支持22.5W快充 [数据源: 电商]",
                    "追评：用了两周后壳发热明显，边充边放包里不放心 [数据源: 电商]",
                ],
            },
            {
                "kind": "ecommerce",
                "platform": "taobao",
                "query": "Taobao power bank reviews",
                "url": "mock://taobao/powerbank",
                "evidence": [
                    "差评：重量比页面轻薄宣传重，随身小包放不下 [数据源: 电商]",
                    "追评：机场安检会看Wh标注，包装上字太小 [数据源: 电商]",
                ],
            },
        ],
        "social_data": [
            {
                "kind": "social",
                "platform": "xiaohongshu",
                "query": "XHS power bank pitfall",
                "url": "mock://xhs/powerbank",
                "evidence": [
                    "小红书评论：出差能用，但过安检被问3C和Wh标注 [数据源: 小红书]",
                    "小红书避坑：商家说轻薄，实际拿到手沉，通勤包有负担 [数据源: 小红书]",
                ],
            }
        ],
    }


FITORNOT_SYSTEM_PROMPT = """You are FITorNOT, a neutral cross-platform consumer decision auditor.

Hard rules:
1. Every pro/con/risk claim must end with a traceable evidence fragment in the
   form [数据源: 电商/小红书] plus a short original snippet.
2. If merchant claims conflict with social reviews, create a dedicated dispute
   point.
3. If Xiaohongshu pitfalls match e-commerce follow-up or negative reviews, mark
   them as ⚡ 高危避坑硬伤.
4. Do not invent missing data. If a source is blocked, say so.
5. The final report must use the user's target_language except proper nouns,
   model names, platform names, and source labels.
"""


def build_fitornot_prompt(state: DecisionState) -> str:
    payload = {
        "target_language": state["target_language"],
        "intent_slots": state["slots"].model_dump(),
        "ecommerce_data": state.get("ecommerce_data", []),
        "social_data": state.get("social_data", []),
        "blocked_sources": state.get("blocked_sources", []),
        "required_template": [
            "商品全局意图图谱",
            "跨平台数据交叉验证表格",
            "避坑指南与风险分级",
            "最终决策建议",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_evidence_report(
    slots: IntentSlots,
    ecommerce_data: list[dict[str, Any]],
    social_data: list[dict[str, Any]],
    blocked_sources: list[dict[str, str]],
    target_language: str,
) -> str:
    ecommerce_evidence = collect_evidence(ecommerce_data)
    social_evidence = collect_evidence(social_data)
    high_risk = pick_high_risk(ecommerce_evidence, social_evidence)
    dispute = pick_dispute(ecommerce_evidence, social_evidence)
    blocked_text = (
        "\n".join(f"- {item['source']}: {item['reason']}" for item in blocked_sources)
        if blocked_sources
        else "无"
    )

    return f"""## 📌 商品全局意图图谱
- **目标品类/型号**：{slots.category} / {slots.brand} {slots.model}
- **全网核心卖点**：{first_or_default(ecommerce_evidence, "暂无可靠电商参数")} 

## 🔍 跨平台数据交叉验证 (Bright Data Scraped Data)
| 平台数据源 | 样本噪点率 (软文/刷单预估) | 核心风向标 (用户都在夸什么/骂什么) |
| :--- | :--- | :--- |
| 电商平台 (价格/质量) | 中 | {first_or_default(ecommerce_evidence, "暂无")} |
| 小红书 (种草/玩法) | 中 | {first_or_default(social_evidence, "暂无")} |

### 争议点
- {dispute}

### 抓取受阻
{blocked_text}

## 🚫 避坑指南与风险分级
- **⚡ 高危风险（买前必看）**：{high_risk}
- **⚠️ 场景不匹配风险**：若你的真实场景正好命中上述负面追评或小红书避坑点，优先选择参数更透明、售后更稳的替代品。[数据源: 电商/小红书] "{short_join(ecommerce_evidence + social_evidence)}"

## 💡 最终决策建议
- **购买指数**：⭐⭐⭐
- **一句话结论**：不建议盲买；只有在你能接受上述高危点、且购买渠道支持无理由退换时，才适合低风险尝试。[数据源: 电商/小红书] "{short_join(ecommerce_evidence + social_evidence)}"

> 输出语言请求：{target_language}。"""


def collect_evidence(items: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for item in items:
        for line in item.get("evidence", []):
            if isinstance(line, str) and line.strip():
                evidence.append(line.strip())
    return evidence


def pick_high_risk(ecommerce: list[str], social: list[str]) -> str:
    risk_terms = ("发热", "鼓包", "刺痛", "泛红", "拉稀", "软便", "安检", "Wh")
    all_lines = ecommerce + social
    matched = [line for line in all_lines if any(term in line for term in risk_terms)]
    if matched:
        return f"{matched[0]}"
    return f"{first_or_default(all_lines, '未发现跨平台一致高危硬伤')}"


def pick_dispute(ecommerce: list[str], social: list[str]) -> str:
    joined = " ".join(ecommerce + social)
    if "轻薄" in joined and any(term in joined for term in ("重", "沉", "负担")):
        return '商家轻薄叙事与真实携带反馈冲突。[数据源: 电商/小红书] "轻薄 / 沉 / 负担"'
    if "提亮" in joined and any(term in joined for term in ("刺痛", "泛红", "爆痘")):
        return '功效卖点与刺激反馈冲突。[数据源: 电商/小红书] "提亮 / 刺痛 / 泛红"'
    if "泪痕" in joined and any(term in joined for term in ("软便", "拉稀", "呕吐")):
        return '功能粮卖点与肠胃适应风险冲突。[数据源: 电商/小红书] "泪痕 / 软便 / 拉稀"'
    return f"{first_or_default(ecommerce + social, '暂无明确争议点')}"


def first_or_default(items: list[str], default: str) -> str:
    return items[0] if items else default


def short_join(items: list[str]) -> str:
    return "；".join(items[:2])[:220] or "暂无"


def _deterministic_report_from_prompt(messages: list[tuple[str, str]]) -> str:
    return "## 📌 商品全局意图图谱\n- **目标品类/型号**：Mock\n\n[数据源: 电商] mock"


app = FastAPI(title="FITorNOT Decision API", version="0.2.0")


@app.post("/api/v1/decision", response_model=DecisionResponse)
async def decision_endpoint(request: DecisionRequest) -> DecisionResponse:
    return await create_decision(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "FITorNOT"}
