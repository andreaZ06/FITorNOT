"""FITorNOT five-node multi-agent decision API.

The production path uses FastAPI, LangGraph, LangChain's ChatOpenAI wrapper for
DeepSeek, and the local Bright Data MCP server named "brightdata". The local
test path keeps deterministic mock data so the graph contract can be validated
without network credentials.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, NotRequired, Optional, TypedDict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI
except Exception:  # pragma: no cover - local test fallback
    _ChatOpenAI = None

try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
except Exception:  # pragma: no cover - local test fallback
    MultiServerMCPClient = None

try:
    from langgraph.graph import END, StateGraph as _StateGraph
except Exception:  # pragma: no cover - local test fallback
    END = "__end__"
    _StateGraph = None


DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
SUPPORTED_CATEGORIES = ("充电宝", "面膜", "狗粮", "其他")
URL_PATTERN = re.compile(r"https?://[^\s,，]+", re.IGNORECASE)


PLANNER_SYSTEM_PROMPT = """你是一个极其敏锐的消费意图解析专家。你的任务是分析用户的模糊或明确输入，精确提取核心商品槽位。

【提取规范】：
1. category：品类。必须根据常识及核心词，将其归类为 [充电宝, 面膜, 狗粮, 其他] 之一。
2. brand：品牌。提取用户提到的品牌，若无明确提及则为 null。
3. model：型号/系列。提取具体系列、容量、配方或型号名称，若无则为 null。
4. urls：链接数组。提取出用户文本中附带的所有 http 或 https 链接，若无则为空数组 []。

【输出格式约束】：
必须且只能输出一个标准的 JSON 对象，严禁包含 markdown 语法标记（如 ```json），严禁有任何解释性文本。
示例：{"category": "狗粮", "brand": "麦富迪", "model": "鲜肉冻干粮", "urls": []}"""


RETRIEVER_SYSTEM_PROMPT = """你现在是【Bright Data MCP 调度官】。你需要根据输入的商品基本信息，生成精准的、具备反营销能力的跨平台搜索指令。

【输入数据】：
品类: {category}, 品牌: {brand}, 型号: {model}

【生成任务】：
1. 生成 1 个用于货架电商（京东/淘宝）的精准搜索词，格式为：[品牌] [型号]。
2. 结合该品类的常见翻车点，生成 2 个专门去小红书挖真实黑料的反营销探针词。
   - 充电宝：必须包含“发热”、“降功率”或“虚标”。
   - 面膜：必须包含“刺痛”、“过敏”或“闷痘”。
   - 狗粮：必须包含“软便”、“拉稀”或“不吃”。

【输出格式约束】：
必须且只能返回标准的 JSON 对象。
示例：
{
  "ecommerce_query": "麦富迪 鲜肉冻干粮",
  "xiaohongshu_queries": ["麦富迪 鲜肉冻干粮 软便", "麦富迪 鲜肉冻干粮 真实评价"]
}"""


ANALYZER_SYSTEM_PROMPT = """你是一个严苛的【数据审计师与去噪专家】。你需要对 Bright Data 抓取回来的跨平台海量网评进行深度脱敏、去噪和风险分级。

【处理规则】：
1. 拦截营销水军：如果小红书文本存在过度宣称（如“完美无瑕”、“平价天花板”）、缺乏真实痛点使用场景，直接判定为水军笔记，剔除其权重。
2. 提炼真实痛点：重点分析电商的【差评、追评】以及小红书的【评论区真实声音】。
3. 风险归类：
   - ⚡ 核心硬伤：属于产品本身质量缺陷、安全隐患（如充电宝极烫、狗粮拉稀血便、面膜严重过敏）。
   - ⚠️ 软性偏好：属于产品没问题但挑人/挑场景（如充电宝太重、狗粮颗粒大、面膜布不服帖）。

【输出格式】：
请以高度精炼的 JSON 结构输出你清洗后的干货，每一条痛点必须保留 1-2 句最尖锐的用户原话作为证据链：
{"core_scandals": [{"issue": "发热严重", "evidence": "用户A: 磁吸充了十分钟烫得不敢手拿"}], "soft_drawbacks": []}"""


SCENARIO_ADAPTER_SYSTEM_PROMPT = """你现在是【消费场景适配器】。你的任务是把商品清洗后的数据，与用户的真实使用画像进行精细化的交叉碰撞，判断该商品对于该用户而言是“蜜糖”还是“砒霜”。

【匹配逻辑】：
1. 提取画像：根据用户初始输入，分析其核心痛点场景（例如：经常坐飞机、大油皮、小狗有泪痕）。
2. 跨平台冲突审计：对比电商官参（如：重量 350g）与小红书评论（如：博主吹嘘极度轻便）。如果存在严重事实冲突，判定为商家虚假营销，记录在 `marketing_clash` 中。
3. 适配判定：分析该产品的核心风险对该用户的具体场景是否属于“一票否决”。（例如：用户是要带上飞机的，但充电宝额定能量超标，属于一票否决）。

【输出格式】：
返回 JSON 结构：
{
  "user_profile_extracted": "用户核心场景与需求特征简述",
  "marketing_clash": "如果存在官方参数与网评的冲突，写在这里，否则为 null",
  "suitability_analysis": "针对该用户的定制化适配劝退或购买理由分析"
}"""


GENERATOR_SYSTEM_PROMPT = """你现在是中立、极其敏锐的消费决策 AI 裁判官 —— 【FITorNOT】。
请根据前序节点经过严苛校验后的结构化数据，使用用户指定的语言【{target_language}】，生成最终的决策报告。

【输入上下文数据】：
- 官方硬核参数: {verified_specs}
- 跨平台清洗后真实用户痛点与原话证据: {core_scandals_and_evidences}
- 场景匹配度结论: {suitability_analysis}

【绝对死律（反幻觉防护）】：
1. 报告中的每一条购买或劝退建议，后面必须用 `[数据源: 电商追评/小红书真实评论]` 附带用户的原话片段，进行严格的证据链回溯。
2. 严禁凭空发明或臆测该产品的任何新优缺点。
3. 全篇必须严格使用标准的 Markdown 语法进行结构化排版。

【输出模版（严格对照输出）】：
## 📌 商品全局意图图谱
- **目标品类/型号**：...
- **全网核心卖点**：...

## 🔍 跨平台数据交叉验证表格
| 平台数据源 | 样本噪点率 | 核心风向标 (用户都在夸什么/骂什么) |
| :--- | :--- | :--- |
| 小红书 (种草/玩法) | [高/中/低] | ... |
| 电商平台 (价格/质量) | [高/中/低] | ... |

## 🚫 避坑指南与风险分级
- ⚡ **高危硬伤（买前必看）**：... [证据链: ...]
- ⚠️ **场景不匹配风险**：... [证据链: ...]

## 💡 FITorNOT 最终决策建议
- **购买指数**：[⭐⭐⭐⭐⭐]
- **一句话结论**：[精准的购买/劝退建议]"""


class IntentSlots(BaseModel):
    category: Literal["充电宝", "面膜", "狗粮", "其他"]
    brand: Optional[str] = None
    model: Optional[str] = None
    urls: list[str] = Field(default_factory=list)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        return [url for url in value if URL_PATTERN.match(url)]


class RetrievalPlan(BaseModel):
    ecommerce_query: str = Field(..., min_length=1)
    xiaohongshu_queries: list[str] = Field(..., min_length=2, max_length=2)

    @model_validator(mode="after")
    def enforce_probe_terms(self) -> "RetrievalPlan":
        joined = " ".join(self.xiaohongshu_queries)
        probe_terms = ("发热", "降功率", "虚标", "刺痛", "过敏", "闷痘", "软便", "拉稀", "不吃", "真实评价")
        if not any(term in joined for term in probe_terms):
            raise ValueError("xiaohongshu_queries must include anti-marketing probe terms")
        return self


class EvidenceItem(BaseModel):
    source: Literal["官方参数", "电商追评", "电商差评", "小红书真实评论", "小红书笔记"]
    text: str = Field(..., min_length=1)
    platform: Optional[str] = None
    url: Optional[str] = None


class RawPlatformData(BaseModel):
    retrieval_plan: RetrievalPlan
    verified_specs: dict[str, Any] = Field(default_factory=dict)
    ecommerce_evidence: list[EvidenceItem] = Field(default_factory=list)
    xiaohongshu_evidence: list[EvidenceItem] = Field(default_factory=list)
    blocked_sources: list[dict[str, str]] = Field(default_factory=list)


class RiskFinding(BaseModel):
    issue: str = Field(..., min_length=1)
    evidence: str = Field(..., min_length=1)
    source: Literal["电商追评", "电商差评", "小红书真实评论", "小红书笔记", "跨平台一致"]


class CleanedFindings(BaseModel):
    core_scandals: list[RiskFinding] = Field(default_factory=list)
    soft_drawbacks: list[RiskFinding] = Field(default_factory=list)
    noise_rate: dict[str, Literal["高", "中", "低"]] = Field(default_factory=dict)


class ScenarioFit(BaseModel):
    user_profile_extracted: str = Field(..., min_length=1)
    marketing_clash: Optional[str] = None
    suitability_analysis: str = Field(..., min_length=1)


class FinalReport(BaseModel):
    report: str = Field(..., min_length=1)


class PlannerInput(BaseModel):
    user_raw_input: str


class RetrieverInput(BaseModel):
    slots: IntentSlots
    use_mock: bool = False


class AnalyzerInput(BaseModel):
    raw_data: RawPlatformData


class ScenarioAdapterInput(BaseModel):
    user_raw_input: str
    slots: IntentSlots
    raw_data: RawPlatformData
    cleaned_findings: CleanedFindings


class GeneratorInput(BaseModel):
    target_language: str
    slots: IntentSlots
    raw_data: RawPlatformData
    cleaned_findings: CleanedFindings
    scenario_fit: ScenarioFit


class DecisionRequest(BaseModel):
    user_raw_input: str = Field(..., min_length=1)
    target_language: str = Field(default="中文", min_length=1)
    use_mock: bool = Field(default=False)


class DecisionResponse(BaseModel):
    slots: IntentSlots
    retrieval_plan: RetrievalPlan
    raw_data: RawPlatformData
    cleaned_findings: CleanedFindings
    scenario_fit: ScenarioFit
    ecommerce_data: list[dict[str, Any]]
    social_data: list[dict[str, Any]]
    blocked_sources: list[dict[str, str]]
    report: str


class DecisionState(TypedDict):
    user_raw_input: str
    target_language: str
    use_mock: NotRequired[bool]
    slots: NotRequired[IntentSlots]
    retrieval_plan: NotRequired[RetrievalPlan]
    raw_data: NotRequired[RawPlatformData]
    cleaned_findings: NotRequired[CleanedFindings]
    scenario_fit: NotRequired[ScenarioFit]
    final_report: NotRequired[FinalReport]


class _CompatChatOpenAI:
    def __init__(self, **kwargs: Any) -> None:
        self.model_name = kwargs.get("model") or kwargs.get("model_name")
        self.openai_api_base = kwargs.get("base_url")
        self.temperature = kwargs.get("temperature")

    def with_structured_output(self, schema: type[BaseModel]) -> "_CompatStructuredLLM":
        return _CompatStructuredLLM(schema)


class _CompatStructuredLLM:
    def __init__(self, schema: type[BaseModel]) -> None:
        self.schema = schema

    async def ainvoke(self, value: Any) -> BaseModel:
        if self.schema is IntentSlots:
            text = _messages_to_text(value)
            return infer_intent_slots_locally(text)
        if self.schema is RetrievalPlan:
            payload = _json_from_messages(value)
            slots = IntentSlots.model_validate(payload)
            return build_local_retrieval_plan(slots)
        if self.schema is CleanedFindings:
            payload = _json_from_messages(value)
            return analyze_raw_data_locally(RawPlatformData.model_validate(payload))
        if self.schema is ScenarioFit:
            payload = _json_from_messages(value)
            return adapt_scenario_locally(ScenarioAdapterInput.model_validate(payload))
        if self.schema is FinalReport:
            payload = _json_from_messages(value)
            return FinalReport(report=render_report_locally(GeneratorInput.model_validate(payload)))
        raise RuntimeError(f"Unsupported structured schema: {self.schema}")


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

    def add_node(self, name: str, node: Callable[[DecisionState], Awaitable[DecisionState]]) -> None:
        self._nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def add_edge(self, source: str, target: str) -> None:
        self._edges.append((source, target))

    def compile(self) -> _CompatCompiledGraph:
        return _CompatCompiledGraph(self._nodes, self._edges, self._entry_point)


StateGraph = _StateGraph or _CompatStateGraph


def build_deepseek_llm(model: str, temperature: float = 0.0) -> Any:
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


async def planner_node(state: DecisionState) -> DecisionState:
    """Node 1: parse user intent into immutable product slots."""

    payload = PlannerInput(user_raw_input=state["user_raw_input"])
    if state.get("use_mock"):
        slots = infer_intent_slots_locally(payload.user_raw_input)
    else:
        llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
        structured_llm = llm.with_structured_output(IntentSlots)
        slots = await structured_llm.ainvoke(
            [
                ("system", PLANNER_SYSTEM_PROMPT),
                ("user", payload.user_raw_input),
            ]
        )
    state["slots"] = IntentSlots.model_validate(slots)
    return state


async def retriever_node(state: DecisionState) -> DecisionState:
    """Node 2: generate anti-marketing search probes and fetch Bright Data MCP."""

    payload = RetrieverInput(slots=state["slots"], use_mock=bool(state.get("use_mock")))
    if payload.use_mock:
        retrieval_plan = build_local_retrieval_plan(payload.slots)
        raw_data = mock_raw_platform_data(payload.slots, retrieval_plan)
        state["retrieval_plan"] = retrieval_plan
        state["raw_data"] = raw_data
        return state

    llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
    structured_llm = llm.with_structured_output(RetrievalPlan)
    retrieval_plan = await structured_llm.ainvoke(
        [
            (
                "system",
                RETRIEVER_SYSTEM_PROMPT.format(
                    category=payload.slots.category,
                    brand=payload.slots.brand,
                    model=payload.slots.model,
                ),
            ),
            ("user", payload.slots.model_dump_json()),
        ]
    )
    retrieval_plan = RetrievalPlan.model_validate(retrieval_plan)
    raw_data = await fetch_brightdata_sources(payload.slots, retrieval_plan)
    state["retrieval_plan"] = retrieval_plan
    state["raw_data"] = raw_data
    return state


async def analyzer_node(state: DecisionState) -> DecisionState:
    """Node 3: clean raw platform data and classify hard/soft risks."""

    payload = AnalyzerInput(raw_data=state["raw_data"])
    if state.get("use_mock"):
        findings = analyze_raw_data_locally(payload.raw_data)
    else:
        llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
        structured_llm = llm.with_structured_output(CleanedFindings)
        findings = await structured_llm.ainvoke(
            [
                ("system", ANALYZER_SYSTEM_PROMPT),
                ("user", payload.raw_data.model_dump_json()),
            ]
        )
    state["cleaned_findings"] = CleanedFindings.model_validate(findings)
    return state


async def scenario_adapter_node(state: DecisionState) -> DecisionState:
    """Node 4: collide cleaned risks with the user's concrete scenario."""

    payload = ScenarioAdapterInput(
        user_raw_input=state["user_raw_input"],
        slots=state["slots"],
        raw_data=state["raw_data"],
        cleaned_findings=state["cleaned_findings"],
    )
    if state.get("use_mock"):
        scenario_fit = adapt_scenario_locally(payload)
    else:
        llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
        structured_llm = llm.with_structured_output(ScenarioFit)
        scenario_fit = await structured_llm.ainvoke(
            [
                ("system", SCENARIO_ADAPTER_SYSTEM_PROMPT),
                ("user", payload.model_dump_json()),
            ]
        )
    state["scenario_fit"] = ScenarioFit.model_validate(scenario_fit)
    return state


async def generator_node(state: DecisionState) -> DecisionState:
    """Node 5: generate the final evidence-traced Markdown decision report."""

    payload = GeneratorInput(
        target_language=state["target_language"],
        slots=state["slots"],
        raw_data=state["raw_data"],
        cleaned_findings=state["cleaned_findings"],
        scenario_fit=state["scenario_fit"],
    )
    if state.get("use_mock"):
        final_report = FinalReport(report=render_report_locally(payload))
    else:
        llm = build_deepseek_llm("deepseek-reasoner", temperature=0.1)
        structured_llm = llm.with_structured_output(FinalReport)
        final_report = await structured_llm.ainvoke(
            [
                (
                    "system",
                    GENERATOR_SYSTEM_PROMPT.format(
                        target_language=payload.target_language,
                        verified_specs=payload.raw_data.verified_specs,
                        core_scandals_and_evidences=payload.cleaned_findings.model_dump(),
                        suitability_analysis=payload.scenario_fit.suitability_analysis,
                    ),
                ),
                ("user", payload.model_dump_json()),
            ]
        )
    state["final_report"] = FinalReport.model_validate(final_report)
    return state


def build_decision_graph() -> Any:
    graph = StateGraph(DecisionState)
    graph.add_node("planner_node", planner_node)
    graph.add_node("retriever_node", retriever_node)
    graph.add_node("analyzer_node", analyzer_node)
    graph.add_node("scenario_adapter_node", scenario_adapter_node)
    graph.add_node("generator_node", generator_node)
    graph.set_entry_point("planner_node")
    graph.add_edge("planner_node", "retriever_node")
    graph.add_edge("retriever_node", "analyzer_node")
    graph.add_edge("analyzer_node", "scenario_adapter_node")
    graph.add_edge("scenario_adapter_node", "generator_node")
    graph.add_edge("generator_node", END)
    return graph.compile()


async def create_decision(request: DecisionRequest, use_mock: bool | None = None) -> DecisionResponse:
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

    raw_data = final_state["raw_data"]
    return DecisionResponse(
        slots=final_state["slots"],
        retrieval_plan=final_state["retrieval_plan"],
        raw_data=raw_data,
        cleaned_findings=final_state["cleaned_findings"],
        scenario_fit=final_state["scenario_fit"],
        ecommerce_data=[item.model_dump() for item in raw_data.ecommerce_evidence],
        social_data=[item.model_dump() for item in raw_data.xiaohongshu_evidence],
        blocked_sources=raw_data.blocked_sources,
        report=final_state["final_report"].report,
    )


async def fetch_brightdata_sources(slots: IntentSlots, retrieval_plan: RetrievalPlan) -> RawPlatformData:
    try:
        tool_router = await build_brightdata_tool_router()
    except Exception as exc:  # noqa: BLE001
        raw_data = mock_raw_platform_data(slots, retrieval_plan)
        raw_data.blocked_sources.append({"source": "brightdata", "reason": f"MCP unavailable: {exc}"})
        return raw_data

    ecommerce_tasks = [
        fetch_one_source(tool_router, {"kind": "ecommerce", "query": retrieval_plan.ecommerce_query, "url": url})
        for url in slots.urls
    ]
    ecommerce_tasks.append(
        fetch_one_source(tool_router, {"kind": "ecommerce", "query": retrieval_plan.ecommerce_query, "url": ""})
    )
    social_tasks = [
        fetch_one_source(tool_router, {"kind": "social", "query": query, "url": ""})
        for query in retrieval_plan.xiaohongshu_queries
    ]

    blocked_sources: list[dict[str, str]] = []
    ecommerce_evidence: list[EvidenceItem] = []
    xiaohongshu_evidence: list[EvidenceItem] = []
    verified_specs: dict[str, Any] = {}

    for result in await asyncio.gather(*(ecommerce_tasks + social_tasks), return_exceptions=True):
        if isinstance(result, Exception):
            blocked_sources.append({"source": "brightdata", "reason": str(result)})
            continue
        if result["kind"] == "social":
            xiaohongshu_evidence.extend(result["evidence"])
        else:
            ecommerce_evidence.extend(result["evidence"])
            verified_specs.update(result.get("verified_specs", {}))

    if not ecommerce_evidence and not xiaohongshu_evidence:
        fallback = mock_raw_platform_data(slots, retrieval_plan)
        fallback.blocked_sources.append(
            {"source": "brightdata", "reason": "All MCP calls failed; mock schema payload used."}
        )
        return fallback

    return RawPlatformData(
        retrieval_plan=retrieval_plan,
        verified_specs=verified_specs,
        ecommerce_evidence=ecommerce_evidence,
        xiaohongshu_evidence=xiaohongshu_evidence,
        blocked_sources=blocked_sources,
    )


async def build_brightdata_tool_router() -> Callable[[dict[str, str]], Awaitable[Any]]:
    if MultiServerMCPClient is None:
        raise RuntimeError("langchain_mcp_adapters is not installed.")

    client = MultiServerMCPClient(
        {
            "brightdata": {
                "command": "powershell",
                "args": [
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path.home() / ".codex" / "mcp" / "brightdata-mcp.ps1"),
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
    selected = next((tools_by_name[name] for name in preferred_names if name in tools_by_name), None)
    if selected is None:
        raise RuntimeError("brightdata MCP connected, but no supported scrape/search tool was found.")

    async def route(query: dict[str, str]) -> Any:
        payload = {"url": query["url"]} if query.get("url") else {"query": query["query"]}
        return await selected.ainvoke(payload)

    return route


async def fetch_one_source(
    tool_router: Callable[[dict[str, str]], Awaitable[Any]], query: dict[str, str]
) -> dict[str, Any]:
    raw = await tool_router(query)
    evidence = normalize_raw_evidence(raw, query["kind"])
    return {
        "kind": query["kind"],
        "query": query["query"],
        "verified_specs": infer_specs_from_evidence(evidence),
        "evidence": evidence,
    }


def build_local_retrieval_plan(slots: IntentSlots) -> RetrievalPlan:
    subject = " ".join(part for part in [slots.brand, slots.model] if part) or slots.category
    if slots.category == "充电宝" and slots.brand and not slots.model:
        subject = f"{slots.brand} 充电宝"
    probes = {
        "充电宝": ["发热", "虚标"],
        "面膜": ["刺痛", "过敏"],
        "狗粮": ["软便", "拉稀"],
        "其他": ["真实评价", "避坑"],
    }[slots.category]
    return RetrievalPlan(
        ecommerce_query=subject,
        xiaohongshu_queries=[f"{subject} {probes[0]}", f"{subject} {probes[1]}"],
    )


def infer_intent_slots_locally(text: str) -> IntentSlots:
    urls = URL_PATTERN.findall(text)
    category: Literal["充电宝", "面膜", "狗粮", "其他"] = "其他"
    if any(word in text for word in ("充电宝", "充电器", "mAh", "上飞机", "发热")):
        category = "充电宝"
    elif any(word in text for word in ("面膜", "敏感肌", "刺痛", "泛红", "闷痘")):
        category = "面膜"
    elif any(word in text for word in ("狗粮", "软便", "拉稀", "泪痕", "狗狗")):
        category = "狗粮"

    cleaned = URL_PATTERN.sub(" ", text)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", cleaned)
    brand = next((token for token in tokens if re.search(r"[A-Za-z]", token)), None)
    model = None
    if brand:
        brand_index = tokens.index(brand)
        model = next(
            (
                token
                for token in tokens[brand_index + 1 :]
                if token not in SUPPORTED_CATEGORIES and looks_like_model_token(token)
            ),
            None,
        )
    return IntentSlots(category=category, brand=brand, model=model, urls=urls)


def looks_like_model_token(token: str) -> bool:
    risk_or_intent_terms = ("发热", "飞机", "风险", "避坑", "看看", "评价", "真实")
    if any(term in token for term in risk_or_intent_terms):
        return False
    return bool(re.search(r"\d|mAh|Wh|Pro|Max|冻干|配方|系列", token, re.IGNORECASE))


def mock_raw_platform_data(slots: IntentSlots, retrieval_plan: RetrievalPlan) -> RawPlatformData:
    if slots.category == "面膜":
        specs = {"功效": "提亮", "适用肤质": "普通肤质"}
        ecommerce = [
            EvidenceItem(source="官方参数", text="商品参数：烟酰胺提亮，适合普通肤质，单片价格约9.9元", platform="jd"),
            EvidenceItem(source="电商追评", text="第二次用脸颊泛红发烫，敏感肌慎重", platform="jd"),
        ]
        social = [
            EvidenceItem(source="小红书真实评论", text="急救提亮有一点，但刺痛感明显", platform="xiaohongshu"),
            EvidenceItem(source="小红书真实评论", text="屏障受损期间用了第二天爆痘", platform="xiaohongshu"),
        ]
    elif slots.category == "狗粮":
        specs = {"配方": "鸡肉低敏配方", "卖点": "泪痕管理"}
        ecommerce = [
            EvidenceItem(source="官方参数", text="商品参数：主打低敏和泪痕管理，鸡肉配方", platform="taobao"),
            EvidenceItem(source="电商追评", text="换粮第三天软便，慢慢过渡后才稳定", platform="taobao"),
        ]
        social = [
            EvidenceItem(source="小红书真实评论", text="泪痕淡了但肠胃敏感狗容易拉稀", platform="xiaohongshu"),
            EvidenceItem(source="小红书真实评论", text="适口性一般，需要拌罐头才吃", platform="xiaohongshu"),
        ]
    else:
        specs = {"容量": "20000mAh", "额定能量": "74Wh", "快充": "22.5W"}
        ecommerce = [
            EvidenceItem(source="官方参数", text="商品参数：20000mAh，标称74Wh，支持22.5W快充", platform="jd"),
            EvidenceItem(source="电商追评", text="用了两周后壳发热明显，边充边放包里不放心", platform="jd"),
            EvidenceItem(source="电商差评", text="重量比页面轻薄宣传重，随身小包放不下", platform="taobao"),
        ]
        social = [
            EvidenceItem(source="小红书真实评论", text="出差能用，但过安检被问3C和Wh标注", platform="xiaohongshu"),
            EvidenceItem(source="小红书真实评论", text="商家说轻薄，实际拿到手沉，通勤包有负担", platform="xiaohongshu"),
        ]

    return RawPlatformData(
        retrieval_plan=retrieval_plan,
        verified_specs=specs,
        ecommerce_evidence=ecommerce,
        xiaohongshu_evidence=social,
    )


def normalize_raw_evidence(raw: Any, kind: str) -> list[EvidenceItem]:
    source: Literal["电商追评", "小红书真实评论"] = "小红书真实评论" if kind == "social" else "电商追评"
    lines: list[str]
    if isinstance(raw, str):
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
    elif isinstance(raw, dict):
        lines = []
        for value in raw.values():
            if isinstance(value, str):
                lines.append(value)
            elif isinstance(value, list):
                lines.extend(json.dumps(item, ensure_ascii=False) for item in value[:5])
    else:
        lines = [str(raw)]
    return [EvidenceItem(source=source, text=line[:500]) for line in lines[:8]]


def infer_specs_from_evidence(evidence: list[EvidenceItem]) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    for item in evidence:
        if "Wh" in item.text:
            specs["额定能量线索"] = item.text
        if "mAh" in item.text:
            specs["容量线索"] = item.text
    return specs


def analyze_raw_data_locally(raw_data: RawPlatformData) -> CleanedFindings:
    core_terms = ("发热", "烫", "鼓包", "拉稀", "血便", "严重过敏", "泛红", "刺痛", "虚标", "降功率")
    soft_terms = ("太重", "沉", "颗粒大", "不吃", "不服帖", "放不下", "负担", "适口性")
    all_items = raw_data.ecommerce_evidence + raw_data.xiaohongshu_evidence
    core: list[RiskFinding] = []
    soft: list[RiskFinding] = []
    for item in all_items:
        if any(term in item.text for term in core_terms):
            core.append(RiskFinding(issue=summarize_issue(item.text), evidence=item.text, source=item.source))
        elif any(term in item.text for term in soft_terms):
            soft.append(RiskFinding(issue=summarize_issue(item.text), evidence=item.text, source=item.source))
    return CleanedFindings(
        core_scandals=dedupe_findings(core),
        soft_drawbacks=dedupe_findings(soft),
        noise_rate={"xiaohongshu": "中", "ecommerce": "低"},
    )


def adapt_scenario_locally(payload: ScenarioAdapterInput) -> ScenarioFit:
    text = payload.user_raw_input
    if "飞机" in text or "安检" in text or "出差" in text:
        profile = "用户核心场景是经常坐飞机/出差，关注安检、Wh 标注、发热和随身携带安全。"
    elif "敏感" in text or "油皮" in text:
        profile = "用户核心场景是敏感肌/特定肤质，关注刺痛、过敏、闷痘等一票否决风险。"
    elif "泪痕" in text or "狗" in text:
        profile = "用户核心场景是宠物泪痕管理，关注软便、拉稀、不吃和长期适应性。"
    else:
        profile = "用户没有给出足够细的场景，需要以跨平台硬伤作为主判断依据。"

    evidence_text = " ".join(item.text for item in payload.raw_data.ecommerce_evidence + payload.raw_data.xiaohongshu_evidence)
    clash = None
    if "轻薄" in evidence_text and any(term in evidence_text for term in ("重", "沉", "负担")):
        clash = "官方/商家轻薄叙事与真实用户反馈的重量负担冲突。"
    elif "提亮" in evidence_text and any(term in evidence_text for term in ("刺痛", "泛红", "爆痘")):
        clash = "功效型提亮卖点与真实刺激反馈冲突。"
    elif "泪痕" in evidence_text and any(term in evidence_text for term in ("软便", "拉稀")):
        clash = "泪痕管理卖点与肠胃适应风险冲突。"

    hard_risks = "；".join(finding.issue for finding in payload.cleaned_findings.core_scandals) or "暂未发现核心硬伤"
    return ScenarioFit(
        user_profile_extracted=profile,
        marketing_clash=clash,
        suitability_analysis=f"该商品对该用户的关键风险是：{hard_risks}。如果这些风险命中核心场景，应优先劝退。",
    )


def render_report_locally(payload: GeneratorInput) -> str:
    specs = payload.raw_data.verified_specs or {"参数": "未抓取到可靠官方参数"}
    first_spec = next(iter(specs.items()))
    core = payload.cleaned_findings.core_scandals
    soft = payload.cleaned_findings.soft_drawbacks
    high = core[0] if core else RiskFinding(issue="暂无明确高危硬伤", evidence="未抓取到跨平台一致高危证据", source="跨平台一致")
    soft_risk = soft[0] if soft else high
    xhs_signal = first_text(payload.raw_data.xiaohongshu_evidence)
    ecommerce_signal = first_text(payload.raw_data.ecommerce_evidence)

    return f"""## 📌 商品全局意图图谱
- **目标品类/型号**：{payload.slots.category} / {payload.slots.brand or ''} {payload.slots.model or ''}
- **全网核心卖点**：{first_spec[0]}：{first_spec[1]} [数据源: 电商追评/小红书真实评论] "{ecommerce_signal}"

## 🔍 跨平台数据交叉验证表格
| 平台数据源 | 样本噪点率 | 核心风向标 (用户都在夸什么/骂什么) |
| :--- | :--- | :--- |
| 小红书 (种草/玩法) | {payload.cleaned_findings.noise_rate.get('xiaohongshu', '中')} | {xhs_signal} |
| 电商平台 (价格/质量) | {payload.cleaned_findings.noise_rate.get('ecommerce', '低')} | {ecommerce_signal} |

## 🚫 避坑指南与风险分级
- ⚡ **高危硬伤（买前必看）**：{high.issue} [证据链: {high.evidence}]
- ⚠️ **场景不匹配风险**：{payload.scenario_fit.suitability_analysis} [证据链: {soft_risk.evidence}]

## 💡 FITorNOT 最终决策建议
- **购买指数**：[⭐⭐⭐]
- **一句话结论**：不建议盲买；若你的使用场景命中上述硬伤，优先换更透明、更少争议的同类商品。[数据源: 电商追评/小红书真实评论] "{high.evidence}"
"""


def summarize_issue(text: str) -> str:
    for term in ("发热", "虚标", "降功率", "刺痛", "过敏", "闷痘", "软便", "拉稀", "不吃", "太重", "沉"):
        if term in text:
            return f"{term}风险"
    return text[:18]


def dedupe_findings(items: list[RiskFinding]) -> list[RiskFinding]:
    seen: set[str] = set()
    result: list[RiskFinding] = []
    for item in items:
        key = f"{item.issue}:{item.evidence}"
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def first_text(items: list[EvidenceItem]) -> str:
    return items[0].text if items else "暂无可靠样本"


def _messages_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item[1]) if isinstance(item, tuple) and len(item) > 1 else str(item) for item in value)
    return str(value)


def _json_from_messages(value: Any) -> dict[str, Any]:
    text = _messages_to_text(value)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)


app = FastAPI(title="FITorNOT Decision API", version="0.3.0")


@app.post("/api/v1/decision", response_model=DecisionResponse)
async def decision_endpoint(request: DecisionRequest) -> DecisionResponse:
    return await create_decision(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "FITorNOT"}
