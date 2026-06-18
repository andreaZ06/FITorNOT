"""FITorNOT five-node multi-agent decision API.

The production path uses FastAPI, LangGraph, LangChain's ChatOpenAI wrapper for
DeepSeek, and the local Bright Data MCP server named "brightdata". The local
test path keeps deterministic mock data so the graph contract can be validated
without network credentials.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, NotRequired, Optional, TypedDict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from data_cleaning import clean_and_filter_data as _base_clean_and_filter_data

try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI
except Exception:  # pragma: no cover - local test fallback
    _ChatOpenAI = None

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except Exception:  # pragma: no cover - local test fallback
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None

try:
    from langgraph.graph import END, StateGraph as _StateGraph
except Exception:  # pragma: no cover - local test fallback
    END = "__end__"
    _StateGraph = None

try:
    import asyncpg
except Exception:  # pragma: no cover - optional runtime dependency
    asyncpg = None

try:
    from domestic_browser import PlaywrightDomesticBrowserAdapter
except Exception:  # pragma: no cover - optional runtime dependency
    PlaywrightDomesticBrowserAdapter = None


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


class RiskDictionary(BaseModel):
    category_key: str
    critical_terms: list[str] = Field(default_factory=list)
    veto_terms: list[str] = Field(default_factory=list)
    soft_terms: list[str] = Field(default_factory=list)
    source: Literal["fallback", "neon"] = "fallback"


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


class BrightDataFetchInput(BaseModel):
    user_raw_input: str
    slots: IntentSlots
    retrieval_plan: RetrievalPlan
    user_bound_urls: list[str] = Field(default_factory=list)
    generated_xhs_queries: list[str] = Field(default_factory=list)
    use_mock: bool = False


class BrightDataFetchOutput(BaseModel):
    raw_data: RawPlatformData
    ecommerce_data: list[dict[str, Any]] = Field(default_factory=list)
    xiaohongshu_data: list[dict[str, Any]] = Field(default_factory=list)
    blocked_sources: list[dict[str, str]] = Field(default_factory=list)
    risk_dictionary: RiskDictionary | None = None
    fetch_status: str = "success"


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


class AnalyzerInput(BaseModel):
    raw_data: RawPlatformData
    ecommerce_data: list[dict[str, Any]] = Field(default_factory=list)
    xiaohongshu_data: list[dict[str, Any]] = Field(default_factory=list)
    risk_dictionary: RiskDictionary | None = None


class ScenarioAdapterInput(BaseModel):
    user_raw_input: str
    slots: IntentSlots
    raw_data: RawPlatformData
    cleaned_findings: CleanedFindings
    ecommerce_data: list[dict[str, Any]] = Field(default_factory=list)
    xiaohongshu_data: list[dict[str, Any]] = Field(default_factory=list)
    risk_dictionary: RiskDictionary | None = None


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
    xiaohongshu_data: list[dict[str, Any]] = Field(default_factory=list)
    social_data: list[dict[str, Any]]
    blocked_sources: list[dict[str, str]]
    report: str


class DecisionState(TypedDict):
    user_raw_input: str
    target_language: str
    use_mock: NotRequired[bool]
    slots: NotRequired[IntentSlots]
    retrieval_plan: NotRequired[RetrievalPlan]
    user_bound_urls: NotRequired[list[str]]
    generated_xhs_queries: NotRequired[list[str]]
    raw_data: NotRequired[RawPlatformData]
    ecommerce_data: NotRequired[list[dict[str, Any]]]
    xiaohongshu_data: NotRequired[list[dict[str, Any]]]
    blocked_sources: NotRequired[list[dict[str, str]]]
    risk_dictionary: NotRequired[RiskDictionary]
    fetch_status: NotRequired[str]
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

    def bind_tools(self, tools: list[dict[str, Any]]) -> "_CompatToolBoundLLM":
        return _CompatToolBoundLLM(tools)


class _CompatToolResponse:
    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self.tool_calls = tool_calls


class _CompatToolBoundLLM:
    def __init__(self, tools: list[dict[str, Any]]) -> None:
        self.tools = tools

    async def ainvoke(self, value: Any) -> _CompatToolResponse:
        text = _messages_to_text(value)
        tool_name = _preferred_tool_name(self.tools)
        tool_calls: list[dict[str, Any]] = []
        for url in URL_PATTERN.findall(text):
            tool_calls.append({"name": tool_name, "args": {"url": url}})
        for line in text.splitlines():
            if '"kind": "xiaohongshu"' in line and '"query": "' in line:
                query = line.split('"query": "', 1)[1].split('"', 1)[0]
                tool_calls.append({"name": tool_name, "args": {"query": query}})
            elif '"kind": "ecommerce"' in line and '"query": "' in line:
                query = line.split('"query": "', 1)[1].split('"', 1)[0]
                tool_calls.append({"name": tool_name, "args": {"query": query}})
        return _CompatToolResponse(tool_calls)


class _CompatStructuredLLM:
    def __init__(self, schema: type[BaseModel]) -> None:
        self.schema = schema

    async def ainvoke(self, value: Any) -> BaseModel:
        if self.schema is IntentSlots:
            text = _last_user_message_text(value)
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
LOGGER = logging.getLogger("fitornot.brightdata")
RISK_TERMS_CONTEXT: ContextVar[dict[str, tuple[str, ...]]] = ContextVar("fitornot_risk_terms", default={})
RISK_DICTIONARY_CACHE: dict[str, tuple[float, "RiskDictionary"]] = {}
DEFAULT_RISK_DICTIONARIES: dict[str, dict[str, list[str]]] = {
    "power_bank": {
        "critical_terms": ["发热", "烫", "断连", "鼓包", "虚标", "降功率", "overheat", "disconnect"],
        "veto_terms": ["额定能量超标", "无3C", "带不上飞机", "安检被拦", "flight banned", "security rejected"],
        "soft_terms": ["太重", "沉", "放不下", "heavy", "bulky"],
    },
    "facial_mask": {
        "critical_terms": ["刺痛", "过敏", "发红", "爆痘", "红肿", "stinging", "allergy"],
        "veto_terms": ["烂脸", "屏障受损", "辣眼睛", "barrier damage"],
        "soft_terms": ["不服帖", "太香", "闷", "slippery", "fragrance"],
    },
    "dog_food": {
        "critical_terms": ["软便", "拉稀", "血便", "吐", "soft stool", "diarrhea"],
        "veto_terms": ["不吃", "拒食", "black stool", "refuse to eat"],
        "soft_terms": ["颗粒大", "适口性一般", "口味挑", "large kibble", "picky eater"],
    },
}
DEFAULT_NEON_VETO_QUERY = """
SELECT
    term,
    COALESCE(risk_level, severity, 'critical') AS risk_level
FROM fitornot_veto_dictionary
WHERE category = $1
  AND COALESCE(enabled, TRUE) = TRUE
"""


def build_deepseek_llm(model: str, temperature: float = 0.0) -> Any:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek calls.")

    use_compat = api_key == "test-deepseek-key" or os.getenv("FITORNOT_FORCE_COMPAT_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    cls = _CompatChatOpenAI if use_compat or _ChatOpenAI is None else _ChatOpenAI
    return cls(
        model=model,
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
    )


def render_prompt_template(template: str, **kwargs: Any) -> str:
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def _fallback_risk_dictionary(category_key: str) -> RiskDictionary:
    payload = DEFAULT_RISK_DICTIONARIES.get(category_key, {})
    return RiskDictionary(
        category_key=category_key,
        critical_terms=list(payload.get("critical_terms", [])),
        veto_terms=list(payload.get("veto_terms", [])),
        soft_terms=list(payload.get("soft_terms", [])),
        source="fallback",
    )


async def load_risk_dictionary(category_key: str) -> RiskDictionary:
    normalized_category = category_key or "power_bank"
    cache_ttl = int(os.getenv("NEON_VETO_CACHE_TTL_SECONDS", "300"))
    now = time.time()
    cached = RISK_DICTIONARY_CACHE.get(normalized_category)
    if cached and now - cached[0] < cache_ttl:
        return cached[1]

    fallback = _fallback_risk_dictionary(normalized_category)
    database_url = os.getenv("NEON_DATABASE_URL")
    if not database_url or asyncpg is None:
        RISK_DICTIONARY_CACHE[normalized_category] = (now, fallback)
        return fallback

    query = os.getenv("NEON_VETO_QUERY", DEFAULT_NEON_VETO_QUERY)
    connection = None
    try:
        connection = await asyncpg.connect(database_url, timeout=10)
        rows = await connection.fetch(query, normalized_category)
        risk_dictionary = _merge_risk_dictionary_rows(normalized_category, rows, fallback)
        RISK_DICTIONARY_CACHE[normalized_category] = (now, risk_dictionary)
        return risk_dictionary
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to load Neon risk dictionary for %s: %s", normalized_category, exc)
        RISK_DICTIONARY_CACHE[normalized_category] = (now, fallback)
        return fallback
    finally:
        if connection is not None:
            await connection.close()


def _merge_risk_dictionary_rows(
    category_key: str,
    rows: list[Any],
    fallback: RiskDictionary,
) -> RiskDictionary:
    if not rows:
        return fallback

    critical_terms = list(fallback.critical_terms)
    veto_terms = list(fallback.veto_terms)
    soft_terms = list(fallback.soft_terms)
    seen = {term.lower() for term in critical_terms + veto_terms + soft_terms}

    for row in rows:
        record = dict(row) if not isinstance(row, dict) else row
        term = str(record.get("term", "")).strip()
        if not term or term.lower() in seen:
            continue
        risk_level = str(record.get("risk_level", record.get("severity", "critical"))).lower().strip()
        if risk_level in {"veto", "one_vote_veto", "one-vote-veto", "blocker"}:
            veto_terms.append(term)
        elif risk_level in {"soft", "preference", "warning"}:
            soft_terms.append(term)
        else:
            critical_terms.append(term)
        seen.add(term.lower())

    return RiskDictionary(
        category_key=category_key,
        critical_terms=critical_terms,
        veto_terms=veto_terms,
        soft_terms=soft_terms,
        source="neon",
    )


@contextlib.contextmanager
def _risk_terms_scope(category_key: str, risk_dictionary: RiskDictionary | None):
    if risk_dictionary is None:
        yield
        return

    current = dict(RISK_TERMS_CONTEXT.get())
    current[category_key] = tuple(risk_dictionary.critical_terms)
    token = RISK_TERMS_CONTEXT.set(current)
    try:
        yield
    finally:
        RISK_TERMS_CONTEXT.reset(token)


def _match_terms_in_payload(cleaned_payload: dict[str, Any], terms: list[str]) -> list[str]:
    if not terms:
        return []

    haystacks: list[str] = []
    if cleaned_payload.get("specs_text"):
        haystacks.append(str(cleaned_payload["specs_text"]))
    haystacks.extend(str(note.get("text", "")) for note in cleaned_payload.get("notes", []))
    haystacks.extend(str(comment.get("text", "")) for comment in cleaned_payload.get("comments", []))
    combined = "\n".join(text for text in haystacks if text)

    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        lowered = term.lower()
        if lowered in seen:
            continue
        if term and (term in combined or lowered in combined.lower()):
            matches.append(term)
            seen.add(lowered)
    return matches


def clean_and_filter_data(raw_data: dict, platform: str, category: str) -> dict:
    cleaned_payload = _base_clean_and_filter_data(raw_data, platform, category)
    override_terms = RISK_TERMS_CONTEXT.get().get(str(category), ())
    if not override_terms:
        return cleaned_payload

    for comment in cleaned_payload.get("comments", []):
        text = str(comment.get("text", ""))
        lowered = text.lower()
        comment["is_critical_issue"] = any(
            term and (term in text or term.lower() in lowered) for term in override_terms
        )
    return cleaned_payload


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
    else:
        llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
        structured_llm = llm.with_structured_output(RetrievalPlan)
        retrieval_plan = await structured_llm.ainvoke(
            [
                (
                    "system",
                    render_prompt_template(
                        RETRIEVER_SYSTEM_PROMPT,
                        category=payload.slots.category,
                        brand=payload.slots.brand,
                        model=payload.slots.model,
                    ),
                ),
                ("user", payload.slots.model_dump_json()),
            ]
        )
        retrieval_plan = RetrievalPlan.model_validate(retrieval_plan)

    state["retrieval_plan"] = retrieval_plan
    state["user_bound_urls"] = list(payload.slots.urls)
    state["generated_xhs_queries"] = list(retrieval_plan.xiaohongshu_queries)
    return await brightdata_mcp_fetch_node(state)


async def analyzer_node(state: DecisionState) -> DecisionState:
    """Node 3: clean raw platform data and classify hard/soft risks."""

    payload = AnalyzerInput(
        raw_data=state["raw_data"],
        ecommerce_data=list(state.get("ecommerce_data", [])),
        xiaohongshu_data=list(state.get("xiaohongshu_data", [])),
        risk_dictionary=state.get("risk_dictionary"),
    )
    if state.get("use_mock"):
        findings = analyze_raw_data_locally(
            payload.raw_data,
            payload.ecommerce_data,
            payload.xiaohongshu_data,
            payload.risk_dictionary,
        )
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
        ecommerce_data=list(state.get("ecommerce_data", [])),
        xiaohongshu_data=list(state.get("xiaohongshu_data", [])),
        risk_dictionary=state.get("risk_dictionary"),
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
                    render_prompt_template(
                        GENERATOR_SYSTEM_PROMPT,
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
        ecommerce_data=final_state.get("ecommerce_data", [item.model_dump() for item in raw_data.ecommerce_evidence]),
        xiaohongshu_data=final_state.get(
            "xiaohongshu_data",
            [item.model_dump() for item in raw_data.xiaohongshu_evidence],
        ),
        social_data=final_state.get(
            "xiaohongshu_data",
            [item.model_dump() for item in raw_data.xiaohongshu_evidence],
        ),
        blocked_sources=final_state.get("blocked_sources", raw_data.blocked_sources),
        report=final_state["final_report"].report,
    )


_DOMESTIC_BROWSER_ADAPTER: Any = None


def _browser_automation_enabled() -> bool:
    return os.getenv("FITORNOT_ENABLE_BROWSER_AUTOMATION", "").strip().lower() in {"1", "true", "yes", "on"}


def build_default_domestic_browser_adapter() -> Any:
    if not _browser_automation_enabled():
        return None
    if PlaywrightDomesticBrowserAdapter is None:
        return None
    return PlaywrightDomesticBrowserAdapter()


def set_domestic_browser_adapter(adapter: Any) -> None:
    global _DOMESTIC_BROWSER_ADAPTER
    _DOMESTIC_BROWSER_ADAPTER = adapter


def get_domestic_browser_adapter() -> Any:
    global _DOMESTIC_BROWSER_ADAPTER
    if _DOMESTIC_BROWSER_ADAPTER is None:
        _DOMESTIC_BROWSER_ADAPTER = build_default_domestic_browser_adapter()
    return _DOMESTIC_BROWSER_ADAPTER


def _browser_adapter_unavailable_error() -> RuntimeError:
    return RuntimeError(
        "Playwright browser adapter is unavailable. Install it with `pip install playwright`, run "
        "`playwright install chromium`, and set `FITORNOT_ENABLE_BROWSER_AUTOMATION=1` before using domestic "
        "browser recall."
    )


async def fetch_ecommerce_candidates(query: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
    adapter = get_domestic_browser_adapter()
    if adapter is None:
        raise _browser_adapter_unavailable_error()
    return await adapter.fetch_ecommerce_candidates(query, category, limit=limit)


def normalize_ecommerce_candidates(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        dedupe_key = re.sub(r"\s+", " ", title.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
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


def build_candidate_xhs_queries(candidates: list[dict[str, Any]], category: str) -> list[str]:
    negative_terms = {
        SUPPORTED_CATEGORIES[0]: ["避雷", "真实测评", "缺点"],
        SUPPORTED_CATEGORIES[1]: ["避雷", "刺痛", "缺点"],
        SUPPORTED_CATEGORIES[2]: ["避雷", "软便", "缺点"],
        SUPPORTED_CATEGORIES[3]: ["避雷", "真实测评", "缺点"],
    }.get(category, ["避雷", "真实测评", "缺点"])

    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates[:5]:
        title = candidate.get("title", "").strip()
        if not title:
            continue
        for suffix in negative_terms[:2]:
            query = f"{title} {suffix}"
            if query in seen:
                continue
            seen.add(query)
            queries.append(query)
    return queries[:10]


async def fetch_xiaohongshu_feedback(queries: list[str], limit: int = 10) -> list[dict[str, Any]]:
    adapter = get_domestic_browser_adapter()
    if adapter is None:
        raise _browser_adapter_unavailable_error()
    return await adapter.fetch_xiaohongshu_feedback(queries, limit=limit)


def _candidate_to_evidence(candidate: dict[str, Any]) -> EvidenceItem:
    text = " | ".join(
        part for part in [candidate.get("title", ""), candidate.get("price", ""), candidate.get("shop_name", "")] if part
    )
    return EvidenceItem(
        source="官方参数",
        text=text or "候选商品信息缺失",
        platform=candidate.get("platform") or "search",
        url=candidate.get("url") or None,
    )


def _xhs_hit_to_evidence(hit: dict[str, Any]) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for note in hit.get("notes", [])[:10]:
        note_text = str(note.get("text") or note.get("content") or "").strip()
        if note_text:
            evidence.append(
                EvidenceItem(
                    source="小红书笔记",
                    text=note_text[:500],
                    platform="xiaohongshu",
                    url=hit.get("url") or None,
                )
            )
    for comment in hit.get("comments", [])[:20]:
        comment_text = str(comment.get("text") if isinstance(comment, dict) else comment).strip()
        if comment_text:
            evidence.append(
                EvidenceItem(
                    source="小红书真实评论",
                    text=comment_text[:500],
                    platform="xiaohongshu",
                    url=hit.get("url") or None,
                )
            )
    return evidence


def _build_domestic_fetch_output(
    payload: DomesticRecallInput,
    ecommerce_candidates: list[dict[str, Any]],
    generated_xhs_queries: list[str],
    xiaohongshu_hits: list[dict[str, Any]],
    blocked_sources: list[dict[str, str]],
) -> DomesticRecallOutput:
    raw_data = RawPlatformData(retrieval_plan=payload.retrieval_plan, blocked_sources=list(blocked_sources))
    raw_data.ecommerce_evidence.extend(_candidate_to_evidence(candidate) for candidate in ecommerce_candidates)
    for hit in xiaohongshu_hits:
        raw_data.xiaohongshu_evidence.extend(_xhs_hit_to_evidence(hit))

    fetch_status = "success"
    if blocked_sources and not (ecommerce_candidates or xiaohongshu_hits):
        fetch_status = "partial_failed"
    elif blocked_sources:
        fetch_status = "partial_failed"

    return DomesticRecallOutput(
        raw_data=raw_data,
        ecommerce_candidates=ecommerce_candidates,
        generated_xhs_queries=generated_xhs_queries,
        xiaohongshu_hits=xiaohongshu_hits,
        ecommerce_data=list(ecommerce_candidates),
        xiaohongshu_data=list(xiaohongshu_hits),
        blocked_sources=list(blocked_sources),
        fetch_status=fetch_status,
    )


async def domestic_recall_fetch(payload: DomesticRecallInput) -> DomesticRecallOutput:
    if payload.use_mock:
        mock_candidates = [
            {
                "title": f"{payload.slots.brand or '候选'} {payload.slots.model or ''} 充电宝".strip(),
                "price": "149",
                "shop_name": f"{payload.slots.brand or '品牌'}旗舰店",
                "url": "",
                "platform": "jd",
            }
        ]
        mock_queries = build_candidate_xhs_queries(mock_candidates, payload.slots.category) or list(
            payload.retrieval_plan.xiaohongshu_queries
        )
        raw_data = mock_raw_platform_data(payload.slots, payload.retrieval_plan)
        return DomesticRecallOutput(
            raw_data=raw_data,
            ecommerce_candidates=mock_candidates,
            generated_xhs_queries=mock_queries,
            xiaohongshu_hits=[],
            ecommerce_data=[item.model_dump() for item in raw_data.ecommerce_evidence],
            xiaohongshu_data=[item.model_dump() for item in raw_data.xiaohongshu_evidence],
            blocked_sources=[],
            fetch_status="success",
        )

    blocked_sources: list[dict[str, str]] = []
    try:
        raw_candidates = await fetch_ecommerce_candidates(
            payload.retrieval_plan.ecommerce_query,
            payload.slots.category,
            limit=20,
        )
        ecommerce_candidates = normalize_ecommerce_candidates(raw_candidates, limit=5)
    except Exception as exc:  # noqa: BLE001
        ecommerce_candidates = []
        blocked_sources.append({"source": "domestic_ecommerce", "reason": str(exc)})

    generated_xhs_queries = build_candidate_xhs_queries(ecommerce_candidates, payload.slots.category)
    if not generated_xhs_queries:
        generated_xhs_queries = list(payload.retrieval_plan.xiaohongshu_queries)

    try:
        xiaohongshu_hits = await fetch_xiaohongshu_feedback(generated_xhs_queries, limit=10)
    except Exception as exc:  # noqa: BLE001
        xiaohongshu_hits = []
        blocked_sources.append({"source": "xiaohongshu", "reason": str(exc)})

    return _build_domestic_fetch_output(
        payload,
        ecommerce_candidates,
        generated_xhs_queries,
        xiaohongshu_hits,
        blocked_sources,
    )


async def brightdata_mcp_fetch_node(state: DecisionState) -> DecisionState:
    """Node 2 fetch path: connect to local Bright Data MCP through the official Python SDK."""

    payload = BrightDataFetchInput(
        user_raw_input=state["user_raw_input"],
        slots=state["slots"],
        retrieval_plan=state["retrieval_plan"],
        user_bound_urls=list(state.get("user_bound_urls", state["slots"].urls)),
        generated_xhs_queries=list(
            state.get("generated_xhs_queries", state["retrieval_plan"].xiaohongshu_queries)
        ),
        use_mock=bool(state.get("use_mock")),
    )
    risk_dictionary = await load_risk_dictionary(_category_for_cleaning(payload.slots.category))
    domestic_output = await domestic_recall_fetch(
        DomesticRecallInput(
            user_raw_input=payload.user_raw_input,
            slots=payload.slots,
            retrieval_plan=payload.retrieval_plan,
            use_mock=payload.use_mock,
        )
    )

    if payload.use_mock or domestic_output.ecommerce_candidates or domestic_output.xiaohongshu_hits:
        state["raw_data"] = domestic_output.raw_data
        state["ecommerce_data"] = domestic_output.ecommerce_data
        state["xiaohongshu_data"] = domestic_output.xiaohongshu_data
        state["blocked_sources"] = domestic_output.blocked_sources
        state["risk_dictionary"] = risk_dictionary
        state["fetch_status"] = domestic_output.fetch_status
        state["generated_xhs_queries"] = domestic_output.generated_xhs_queries
        return state

    if payload.use_mock:
        output = _build_mock_fetch_output(payload, risk_dictionary=risk_dictionary)
    else:
        try:
            if ClientSession is None or StdioServerParameters is None or stdio_client is None:
                raise RuntimeError("python mcp SDK is not installed.")

            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "@brightdata/mcp-server-scraper"],
                env=_build_brightdata_server_env(),
            )
            tasks = _build_brightdata_tasks(payload)

            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = _extract_mcp_tools(await session.list_tools())
                    tool_schemas = [schema for schema in (_tool_to_openai_schema(tool) for tool in tools) if schema]
                    if not tool_schemas:
                        raise RuntimeError("Bright Data MCP exposed no callable tools.")

                    llm = build_deepseek_llm("deepseek-chat", temperature=0.0)
                    bound_llm = llm.bind_tools(tool_schemas)
                    response = await bound_llm.ainvoke(_build_brightdata_fetch_messages(payload, tasks))
                    tool_calls = _extract_tool_calls(response)
                    if not tool_calls:
                        tool_calls = _build_fallback_tool_calls(_preferred_tool_name(tool_schemas), tasks)

                    output = await _execute_brightdata_tool_calls(
                        session,
                        payload,
                        tasks,
                        tool_calls,
                        risk_dictionary,
                    )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Bright Data MCP fetch failed: %s", exc)
            output = _build_mock_fetch_output(
                payload,
                reason=str(exc),
                allow_synthetic_payload=False,
                risk_dictionary=risk_dictionary,
            )
            output.blocked_sources = output.blocked_sources + domestic_output.blocked_sources
            output.raw_data.blocked_sources = output.raw_data.blocked_sources + domestic_output.blocked_sources

    state["raw_data"] = output.raw_data
    state["ecommerce_data"] = output.ecommerce_data
    state["xiaohongshu_data"] = output.xiaohongshu_data
    state["blocked_sources"] = output.blocked_sources
    state["risk_dictionary"] = output.risk_dictionary or risk_dictionary
    state["fetch_status"] = output.fetch_status
    return state


async def fetch_brightdata_sources(slots: IntentSlots, retrieval_plan: RetrievalPlan) -> RawPlatformData:
    output = await _run_brightdata_fetch(
        BrightDataFetchInput(
            user_raw_input="",
            slots=slots,
            retrieval_plan=retrieval_plan,
            user_bound_urls=list(slots.urls),
            generated_xhs_queries=list(retrieval_plan.xiaohongshu_queries),
        )
    )
    return output.raw_data


async def _run_brightdata_fetch(payload: BrightDataFetchInput) -> BrightDataFetchOutput:
    state: DecisionState = {
        "user_raw_input": payload.user_raw_input,
        "target_language": "",
        "slots": payload.slots,
        "retrieval_plan": payload.retrieval_plan,
        "user_bound_urls": payload.user_bound_urls,
        "generated_xhs_queries": payload.generated_xhs_queries,
        "use_mock": payload.use_mock,
    }
    state = await brightdata_mcp_fetch_node(state)
    return BrightDataFetchOutput(
        raw_data=state["raw_data"],
        ecommerce_data=state.get("ecommerce_data", []),
        xiaohongshu_data=state.get("xiaohongshu_data", []),
        blocked_sources=state.get("blocked_sources", []),
        fetch_status=state.get("fetch_status", "success"),
    )


def _build_mock_fetch_output(
    payload: BrightDataFetchInput,
    reason: str | None = None,
    allow_synthetic_payload: bool = True,
    blocked_sources: list[dict[str, str]] | None = None,
    risk_dictionary: RiskDictionary | None = None,
) -> BrightDataFetchOutput:
    if allow_synthetic_payload:
        raw_data = mock_raw_platform_data(payload.slots, payload.retrieval_plan)
    else:
        raw_data = RawPlatformData(retrieval_plan=payload.retrieval_plan)
    for blocked_source in blocked_sources or []:
        raw_data.blocked_sources.append(dict(blocked_source))
    if reason:
        raw_data.blocked_sources.append({"source": "brightdata", "reason": reason})
    ecommerce_data = [item.model_dump() for item in raw_data.ecommerce_evidence]
    xiaohongshu_data = [item.model_dump() for item in raw_data.xiaohongshu_evidence]
    return BrightDataFetchOutput(
        raw_data=raw_data,
        ecommerce_data=ecommerce_data,
        xiaohongshu_data=xiaohongshu_data,
        blocked_sources=raw_data.blocked_sources,
        risk_dictionary=risk_dictionary,
        fetch_status="success" if allow_synthetic_payload and not reason else "partial_failed",
    )


def _build_brightdata_server_env() -> dict[str, str]:
    env = dict(os.environ)
    api_key = os.getenv("BRIGHTDATA_API_KEY")
    if api_key:
        env["BRIGHTDATA_API_KEY"] = api_key
    return env


def _extract_mcp_tools(list_tools_result: Any) -> list[Any]:
    if isinstance(list_tools_result, list):
        return list_tools_result
    if hasattr(list_tools_result, "tools"):
        return list(getattr(list_tools_result, "tools"))
    if isinstance(list_tools_result, dict) and "tools" in list_tools_result:
        return list(list_tools_result["tools"])
    return []


def _tool_to_openai_schema(tool: Any) -> dict[str, Any] | None:
    name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
    if not name:
        return None
    description = getattr(tool, "description", None) or (
        tool.get("description") if isinstance(tool, dict) else ""
    )
    input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    if input_schema is None and isinstance(tool, dict):
        input_schema = tool.get("inputSchema") or tool.get("input_schema")
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or "Bright Data MCP tool",
            "parameters": input_schema or {"type": "object", "properties": {}},
        },
    }


def _preferred_tool_name(tool_schemas: list[dict[str, Any]]) -> str:
    preferred_fragments = ("brightdata__scrape", "scrape", "search", "discover")
    names = [schema.get("function", {}).get("name", "") for schema in tool_schemas]
    for fragment in preferred_fragments:
        for name in names:
            if fragment in name:
                return name
    return names[0] if names else "brightdata__scrape"


def _build_brightdata_tasks(payload: BrightDataFetchInput) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_task(kind: str, platform: str, url: str = "", query: str = "") -> None:
        key = (kind, url, query)
        if key in seen:
            return
        seen.add(key)
        tasks.append({"kind": kind, "platform": platform, "url": url, "query": query})

    for url in payload.user_bound_urls:
        add_task("ecommerce", _infer_platform(url), url=url, query=payload.retrieval_plan.ecommerce_query)
    if payload.retrieval_plan.ecommerce_query:
        add_task("ecommerce", "search", query=payload.retrieval_plan.ecommerce_query)
    for query in payload.generated_xhs_queries or payload.retrieval_plan.xiaohongshu_queries:
        add_task("xiaohongshu", "xiaohongshu", query=query)
    return tasks


def _build_brightdata_fetch_messages(
    payload: BrightDataFetchInput, tasks: list[dict[str, str]]
) -> list[tuple[str, str]]:
    system_prompt = """# Role: Bright Data MCP 自动化数据调度员

# Context
你当前处于一个可以实时连接互联网的 Agent 节点中。你拥有 `brightdata__scrape_url` 和 `brightdata__search_keyword` 两个核心底层武器。

# Instruction Rules
1. **优先提取 URL**：如果全局状态中 `user_bound_urls` 不为空，必须依次且并行发起 `brightdata__scrape_url` 工具调用。
2. **动态构造负面探针**：若用户未提供链接，你必须根据规划器解析出的商品信息，联动行业常见通病，发起 `brightdata__search_keyword` 工具：
   - 平台：`jd` 或 `taobao` ── 关键词："[品牌] [型号]" (抓取商品页以提取官参和基本差评)。
   - 平台：`xhs` ── 关键词："[品牌] [型号] 翻车" 或 "[品牌] [型号] 真实体验"。
3. **拒绝凭空想象**：一旦工具返回 403、429（被防风控拦截），必须如实记录并在上下文中置入 `fetch_status: partial_failed`，严禁编造任何虚假的评论字句。
"""
    user_payload = {
        "user_raw_input": payload.user_raw_input,
        "slots": payload.slots.model_dump(),
        "user_bound_urls": payload.user_bound_urls,
        "generated_xhs_queries": payload.generated_xhs_queries,
        "tasks": tasks,
    }
    return [("system", system_prompt), ("user", json.dumps(user_payload, ensure_ascii=False))]


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    raw_calls = getattr(response, "tool_calls", None)
    if raw_calls is None and isinstance(response, dict):
        raw_calls = response.get("tool_calls")
    normalized: list[dict[str, Any]] = []
    for call in raw_calls or []:
        name = call.get("name") if isinstance(call, dict) else None
        args = call.get("args") if isinstance(call, dict) else None
        if isinstance(call, dict) and call.get("function"):
            function = call["function"]
            name = name or function.get("name")
            args = args or function.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"query": args}
        if name and isinstance(args, dict):
            normalized.append({"name": name, "args": args})
    return normalized


def _build_fallback_tool_calls(tool_name: str, tasks: list[dict[str, str]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for task in tasks:
        args = {"url": task["url"]} if task.get("url") else {"query": task["query"]}
        calls.append({"name": tool_name, "args": args})
    return calls


async def _execute_brightdata_tool_calls(
    session: Any,
    payload: BrightDataFetchInput,
    tasks: list[dict[str, str]],
    tool_calls: list[dict[str, Any]],
    risk_dictionary: RiskDictionary | None = None,
) -> BrightDataFetchOutput:
    blocked_sources: list[dict[str, str]] = []
    ecommerce_evidence: list[EvidenceItem] = []
    xiaohongshu_evidence: list[EvidenceItem] = []
    ecommerce_data: list[dict[str, Any]] = []
    xiaohongshu_data: list[dict[str, Any]] = []
    verified_specs: dict[str, Any] = {}

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_arguments = tool_call["args"]
        task = _match_task_for_call(tool_arguments, tasks)
        try:
            raw_result = await session.call_tool(tool_name, tool_arguments)
            normalized_result = _normalize_call_tool_result(raw_result)
            category_key = _category_for_cleaning(payload.slots.category)
            with _risk_terms_scope(category_key, risk_dictionary):
                cleaned_payload = clean_and_filter_data(
                    normalized_result,
                    platform=_platform_for_cleaning(task),
                    category=category_key,
                )
            if risk_dictionary is not None:
                cleaned_payload["matched_veto_terms"] = _match_terms_in_payload(
                    cleaned_payload,
                    risk_dictionary.veto_terms,
                )
                cleaned_payload["matched_soft_terms"] = _match_terms_in_payload(
                    cleaned_payload,
                    risk_dictionary.soft_terms,
                )
                cleaned_payload["risk_dictionary_source"] = risk_dictionary.source
            evidence_kind = "social" if task["kind"] == "xiaohongshu" else "ecommerce"
            evidence = _cleaned_payload_to_evidence(cleaned_payload, evidence_kind, task)
            record = {
                "tool_name": tool_name,
                "platform": task["platform"],
                "url": task["url"],
                "query": task["query"],
                "payload": cleaned_payload,
            }
            if task["kind"] == "xiaohongshu":
                xiaohongshu_data.append(record)
                xiaohongshu_evidence.extend(evidence)
            else:
                ecommerce_data.append(record)
                ecommerce_evidence.extend(evidence)
                verified_specs.update(_spec_pairs_to_dict(cleaned_payload))
                verified_specs.update(infer_specs_from_evidence(evidence))
        except Exception as exc:  # noqa: BLE001
            blocked_sources.append(
                {
                    "source": task["platform"],
                    "url": task["url"] or task["query"],
                    "reason": str(exc),
                }
            )

    if not ecommerce_evidence and not xiaohongshu_evidence:
        reason = blocked_sources[0]["reason"] if blocked_sources else "All MCP tool calls failed."
        return _build_mock_fetch_output(
            payload,
            reason=reason if not blocked_sources else None,
            allow_synthetic_payload=False,
            blocked_sources=blocked_sources,
            risk_dictionary=risk_dictionary,
        )

    raw_data = RawPlatformData(
        retrieval_plan=payload.retrieval_plan,
        verified_specs=verified_specs,
        ecommerce_evidence=ecommerce_evidence,
        xiaohongshu_evidence=xiaohongshu_evidence,
        blocked_sources=blocked_sources,
    )
    return BrightDataFetchOutput(
        raw_data=raw_data,
        ecommerce_data=ecommerce_data,
        xiaohongshu_data=xiaohongshu_data,
        blocked_sources=blocked_sources,
        risk_dictionary=risk_dictionary,
        fetch_status="partial_failed" if blocked_sources else "success",
    )


def _platform_for_cleaning(task: dict[str, str]) -> str:
    if task["kind"] == "xiaohongshu":
        return "xhs"
    if task["platform"] in {"jd", "taobao"}:
        return task["platform"]
    return "jd"


def _category_for_cleaning(category: str) -> str:
    if category == SUPPORTED_CATEGORIES[0]:
        return "power_bank"
    if category == SUPPORTED_CATEGORIES[1]:
        return "facial_mask"
    if category == SUPPORTED_CATEGORIES[2]:
        return "dog_food"

    lowered = str(category or "").lower()
    if "mask" in lowered:
        return "facial_mask"
    if "dog" in lowered or "food" in lowered:
        return "dog_food"
    return "power_bank"


def _cleaned_payload_to_evidence(
    cleaned_payload: dict[str, Any], evidence_kind: str, task: dict[str, str]
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    if evidence_kind == "ecommerce" and cleaned_payload.get("specs_text"):
        evidence.append(
            EvidenceItem(
                source="官方参数",
                text=cleaned_payload["specs_text"],
                platform=task["platform"],
                url=task["url"] or None,
            )
        )

    if evidence_kind == "social":
        for note in cleaned_payload.get("notes", []):
            if note.get("text"):
                evidence.append(
                    EvidenceItem(
                        source="小红书笔记",
                        text=note["text"],
                        platform=task["platform"],
                        url=task["url"] or None,
                    )
                )

    comment_source = "小红书真实评论" if evidence_kind == "social" else "电商追评"
    for comment in cleaned_payload.get("comments", []):
        if comment.get("text"):
            evidence.append(
                EvidenceItem(
                    source=comment_source,
                    text=comment["text"],
                    platform=task["platform"],
                    url=task["url"] or None,
                )
            )
    return evidence


def _spec_pairs_to_dict(cleaned_payload: dict[str, Any]) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    for pair in cleaned_payload.get("specs_pairs", []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            key = str(pair[0]).strip()
            value = str(pair[1]).strip()
            if key and value:
                specs[key] = value
    return specs


def _match_task_for_call(tool_arguments: dict[str, Any], tasks: list[dict[str, str]]) -> dict[str, str]:
    url = str(tool_arguments.get("url", "") or "")
    query = str(tool_arguments.get("query", "") or "")
    for task in tasks:
        if url and task["url"] == url:
            return task
        if query and task["query"] == query:
            return task
    if "xiaohongshu" in url.lower():
        return {"kind": "xiaohongshu", "platform": "xiaohongshu", "url": url, "query": query}
    return {"kind": "ecommerce", "platform": _infer_platform(url or query), "url": url, "query": query}


def _normalize_call_tool_result(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is None and isinstance(result, dict):
        structured = result.get("structuredContent")
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    if content:
        lines: list[str] = []
        for item in content:
            if isinstance(item, str):
                lines.append(item)
                continue
            if isinstance(item, dict):
                if item.get("text"):
                    lines.append(str(item["text"]))
                else:
                    lines.append(json.dumps(item, ensure_ascii=False))
                continue
            text = getattr(item, "text", None)
            lines.append(str(text if text is not None else item))
        return "\n".join(lines)
    if isinstance(result, BaseModel):
        return result.model_dump()
    return result


def _infer_platform(value: str) -> str:
    lowered = value.lower()
    if "xiaohongshu" in lowered:
        return "xiaohongshu"
    if "jd.com" in lowered:
        return "jd"
    if "taobao.com" in lowered or "tmall.com" in lowered:
        return "taobao"
    return "search"


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
        capacity_text = infer_capacity_text(slots, retrieval_plan)
        wh_value = infer_wh_value(capacity_text)
        specs = {"容量": capacity_text, "额定能量": wh_value, "快充": "22.5W"}
        ecommerce = [
            EvidenceItem(
                source="官方参数",
                text=f"商品参数：{capacity_text}，标称{wh_value}，支持22.5W快充",
                platform="jd",
            ),
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


def infer_capacity_text(slots: IntentSlots, retrieval_plan: RetrievalPlan) -> str:
    candidates = [slots.model or "", retrieval_plan.ecommerce_query]
    for candidate in candidates:
        match = re.search(r"(\d{4,6})\s*(mAh|毫安)?", candidate, re.IGNORECASE)
        if match:
            return f"{match.group(1)}mAh"
    return "20000mAh"


def infer_wh_value(capacity_text: str) -> str:
    match = re.search(r"(\d{4,6})", capacity_text)
    if not match:
        return "74Wh"
    mah_value = int(match.group(1))
    wh_value = round(mah_value * 3.7 / 1000, 1)
    if wh_value.is_integer():
        return f"{int(wh_value)}Wh"
    return f"{wh_value}Wh"


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


def _estimate_noise_bucket(platform_payloads: list[dict[str, Any]]) -> str:
    if not platform_payloads:
        return "\u4e2d"

    rates: list[float] = []
    for payload in platform_payloads:
        rate = payload.get("payload", {}).get("noise_rate_estimate")
        if isinstance(rate, (int, float)):
            rates.append(float(rate))

    if not rates:
        return "\u4e2d"

    average = sum(rates) / len(rates)
    if average >= 0.5:
        return "\u9ad8"
    if average >= 0.2:
        return "\u4e2d"
    return "\u4f4e"


def infer_category_key_from_raw_data(raw_data: RawPlatformData) -> str:
    specs_blob = " ".join(f"{key}:{value}" for key, value in raw_data.verified_specs.items())
    evidence_blob = " ".join(item.text for item in raw_data.ecommerce_evidence + raw_data.xiaohongshu_evidence)
    corpus = f"{raw_data.retrieval_plan.ecommerce_query} {specs_blob} {evidence_blob}".lower()
    if any(token in corpus for token in ("mask", "闈㈣啘", "鍒虹棝", "杩囨晱")):
        return "facial_mask"
    if any(token in corpus for token in ("dog", "鐙楃伯", "鎷夌█", "杞究")):
        return "dog_food"
    return "power_bank"


def collect_veto_hits(
    ecommerce_data: list[dict[str, Any]] | None,
    xiaohongshu_data: list[dict[str, Any]] | None,
) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for record in (ecommerce_data or []) + (xiaohongshu_data or []):
        for term in record.get("payload", {}).get("matched_veto_terms", []):
            lowered = str(term).lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            hits.append(str(term))
    return hits


def analyze_raw_data_locally(
    raw_data: RawPlatformData,
    ecommerce_data: list[dict[str, Any]] | None = None,
    xiaohongshu_data: list[dict[str, Any]] | None = None,
    risk_dictionary: RiskDictionary | None = None,
) -> CleanedFindings:
    category_key = infer_category_key_from_raw_data(raw_data)
    active_dictionary = risk_dictionary or _fallback_risk_dictionary(category_key)
    core_terms = tuple(active_dictionary.critical_terms + active_dictionary.veto_terms)
    soft_terms = tuple(active_dictionary.soft_terms)
    all_items = raw_data.ecommerce_evidence + raw_data.xiaohongshu_evidence
    core: list[RiskFinding] = []
    soft: list[RiskFinding] = []
    for item in all_items:
        item_text_lower = item.text.lower()
        if any(term and (term in item.text or term.lower() in item_text_lower) for term in core_terms):
            core.append(RiskFinding(issue=summarize_issue(item.text), evidence=item.text, source=item.source))
        elif any(term and (term in item.text or term.lower() in item_text_lower) for term in soft_terms):
            soft.append(RiskFinding(issue=summarize_issue(item.text), evidence=item.text, source=item.source))
    return CleanedFindings(
        core_scandals=dedupe_findings(core),
        soft_drawbacks=dedupe_findings(soft),
        noise_rate={
            "xiaohongshu": _estimate_noise_bucket(xiaohongshu_data or []),
            "ecommerce": _estimate_noise_bucket(ecommerce_data or []),
        },
    )


def adapt_scenario_locally(payload: ScenarioAdapterInput) -> ScenarioFit:
    text = payload.user_raw_input
    if "椋炴満" in text or "瀹夋" in text or "鍑哄樊" in text:
        profile = "鐢ㄦ埛鏍稿績鍦烘櫙鏄粡甯稿潗椋炴満/鍑哄樊锛屽叧娉ㄥ畨妫€銆乄h 鏍囨敞銆佸彂鐑拰闅忚韩鎼哄甫瀹夊叏銆?"
    elif "鏁忔劅" in text or "娌圭毊" in text:
        profile = "鐢ㄦ埛鏍稿績鍦烘櫙鏄晱鎰熻倢/鐗瑰畾鑲よ川锛屽叧娉ㄥ埡鐥涖€佽繃鏁忋€侀椃鐥樼瓑涓€绁ㄥ惁鍐抽闄┿€?"
    elif "娉棔" in text or "鐙?" in text:
        profile = "鐢ㄦ埛鏍稿績鍦烘櫙鏄疇鐗╂唱鐥曠鐞嗭紝鍏虫敞杞究銆佹媺绋€銆佷笉鍚冨拰闀挎湡閫傚簲鎬с€?"
    else:
        profile = "鐢ㄦ埛娌℃湁缁欏嚭瓒冲缁嗙殑鍦烘櫙锛岄渶瑕佷互璺ㄥ钩鍙扮‖浼や綔涓轰富鍒ゆ柇渚濇嵁銆?"

    evidence_text = " ".join(item.text for item in payload.raw_data.ecommerce_evidence + payload.raw_data.xiaohongshu_evidence)
    clash = None
    if "杞昏杽" in evidence_text and any(term in evidence_text for term in ("閲?", "娌?", "璐熸媴", "heavy")):
        clash = "瀹樻柟/鍟嗗杞昏杽鍙欎簨涓庣湡瀹炵敤鎴峰弽棣堢殑閲嶉噺璐熸媴鍐茬獊銆?"
    elif "鎻愪寒" in evidence_text and any(term in evidence_text for term in ("鍒虹棝", "娉涚孩", "鐖嗙棙")):
        clash = "鍔熸晥鍨嬫彁浜崠鐐逛笌鐪熷疄鍒烘縺鍙嶉鍐茬獊銆?"
    elif "娉棔" in evidence_text and any(term in evidence_text for term in ("杞究", "鎷夌█")):
        clash = "娉棔绠＄悊鍗栫偣涓庤偁鑳冮€傚簲椋庨櫓鍐茬獊銆?"

    veto_hits = collect_veto_hits(payload.ecommerce_data, payload.xiaohongshu_data)
    hard_risks = "锛?".join(finding.issue for finding in payload.cleaned_findings.core_scandals) or "鏆傛湭鍙戠幇鏍稿績纭激"
    if veto_hits:
        hard_risks = f"{hard_risks}锛屽凡鍛戒腑涓€绁ㄥ惁鍐宠鍒?{' / '.join(veto_hits)}"
    return ScenarioFit(
        user_profile_extracted=profile,
        marketing_clash=clash,
        suitability_analysis=f"璇ュ晢鍝佸璇ョ敤鎴风殑鍏抽敭椋庨櫓鏄細{hard_risks}銆傚鏋滆繖浜涢闄╁懡涓牳蹇冨満鏅紝搴斾紭鍏堝姖閫€銆?",
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


def summarize_issue(text: str) -> str:
    canonical_terms = (
        "鍙戠儹",
        "铏氭爣",
        "闄嶅姛鐜?",
        "鍒虹棝",
        "杩囨晱",
        "闂风棙",
        "杞究",
        "鎷夌█",
        "涓嶅悆",
        "澶噸",
        "娌?",
        "overheat",
        "flight banned",
        "security rejected",
        "heavy",
    )
    lowered = text.lower()
    for term in canonical_terms:
        if term in text or term.lower() in lowered:
            return f"{term}椋庨櫓"
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


def summarize_issue(text: str) -> str:
    canonical_terms = (
        "\u53d1\u70ed",
        "\u865a\u6807",
        "\u964d\u529f\u7387",
        "\u523a\u75db",
        "\u8fc7\u654f",
        "\u95f7\u75d8",
        "\u8f6f\u4fbf",
        "\u62c9\u7a00",
        "\u4e0d\u5403",
        "\u592a\u91cd",
        "\u6c89",
        "overheat",
        "flight banned",
        "security rejected",
        "heavy",
    )
    lowered = text.lower()
    for term in canonical_terms:
        if term in text or term.lower() in lowered:
            return f"{term}\u98ce\u9669"
    return text[:18]


def adapt_scenario_locally(payload: ScenarioAdapterInput) -> ScenarioFit:
    text = payload.user_raw_input
    category_key = _category_for_cleaning(payload.slots.category)
    if any(token in text for token in ("\u98de\u673a", "\u5b89\u68c0", "\u51fa\u5dee")) or category_key == "power_bank":
        profile = (
            "\u7528\u6237\u6838\u5fc3\u573a\u666f\u662f\u5750\u98de\u673a/\u51fa\u5dee\uff0c"
            "\u5173\u6ce8\u5b89\u68c0\u3001Wh \u6807\u6ce8\u3001\u53d1\u70ed\u548c\u968f\u8eab\u643a\u5e26\u5b89\u5168\u3002"
        )
    elif any(token in text for token in ("\u654f\u611f", "\u6cb9\u76ae")) or category_key == "facial_mask":
        profile = (
            "\u7528\u6237\u6838\u5fc3\u573a\u666f\u662f\u654f\u611f\u808c/\u7279\u5b9a\u80a4\u8d28\uff0c"
            "\u5173\u6ce8\u523a\u75db\u3001\u8fc7\u654f\u3001\u95f7\u75d8\u7b49\u4e00\u7968\u5426\u51b3\u98ce\u9669\u3002"
        )
    elif any(token in text for token in ("\u6cea\u75d5", "\u72d7")) or category_key == "dog_food":
        profile = (
            "\u7528\u6237\u6838\u5fc3\u573a\u666f\u662f\u5ba0\u7269\u6cea\u75d5\u7ba1\u7406\uff0c"
            "\u5173\u6ce8\u8f6f\u4fbf\u3001\u62c9\u7a00\u3001\u4e0d\u5403\u548c\u957f\u671f\u9002\u5e94\u6027\u3002"
        )
    else:
        profile = (
            "\u7528\u6237\u672a\u63d0\u4f9b\u8db3\u591f\u7ec6\u7684\u573a\u666f\uff0c"
            "\u9700\u8981\u4ee5\u8de8\u5e73\u53f0\u786c\u4f24\u4f5c\u4e3a\u4e3b\u5224\u65ad\u4f9d\u636e\u3002"
        )

    evidence_text = " ".join(item.text for item in payload.raw_data.ecommerce_evidence + payload.raw_data.xiaohongshu_evidence)
    clash = None
    if (
        any(token in evidence_text for token in ("\u8f7b\u8584", "lightweight"))
        and any(token in evidence_text for token in ("\u91cd", "\u6c89", "\u8d1f\u62c5", "heavy"))
    ):
        clash = "\u5b98\u65b9\u8f7b\u8584\u53d9\u4e8b\u4e0e\u771f\u5b9e\u7528\u6237\u91cd\u91cf\u8d1f\u62c5\u53cd\u9988\u51b2\u7a81\u3002"
    elif (
        any(token in evidence_text for token in ("\u63d0\u4eae", "brightening"))
        and any(token in evidence_text for token in ("\u523a\u75db", "\u53d1\u7ea2", "\u7206\u75d8"))
    ):
        clash = "\u5b98\u65b9\u529f\u6548\u5356\u70b9\u4e0e\u771f\u5b9e\u523a\u6fc0\u53cd\u9988\u51b2\u7a81\u3002"
    elif (
        any(token in evidence_text for token in ("\u6cea\u75d5", "tear stain"))
        and any(token in evidence_text for token in ("\u8f6f\u4fbf", "\u62c9\u7a00"))
    ):
        clash = "\u6cea\u75d5\u7ba1\u7406\u5356\u70b9\u4e0e\u80a0\u80c3\u9002\u5e94\u98ce\u9669\u51b2\u7a81\u3002"

    veto_hits = collect_veto_hits(payload.ecommerce_data, payload.xiaohongshu_data)
    hard_risks = "\u3001".join(finding.issue for finding in payload.cleaned_findings.core_scandals) or "\u6682\u672a\u53d1\u73b0\u6838\u5fc3\u786c\u4f24"
    if veto_hits:
        hard_risks = f"{hard_risks}\uff0c\u5df2\u547d\u4e2d\u4e00\u7968\u5426\u51b3\u89c4\u5219: {' / '.join(veto_hits)}"
    return ScenarioFit(
        user_profile_extracted=profile,
        marketing_clash=clash,
        suitability_analysis=(
            f"\u8be5\u5546\u54c1\u5bf9\u8be5\u7528\u6237\u7684\u5173\u952e\u98ce\u9669\u662f\uff1a{hard_risks}\u3002"
            "\u5982\u679c\u8fd9\u4e9b\u98ce\u9669\u547d\u4e2d\u6838\u5fc3\u573a\u666f\uff0c\u5e94\u4f18\u5148\u52a1\u9000\u3002"
        ),
    )


def _messages_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item[1]) if isinstance(item, tuple) and len(item) > 1 else str(item) for item in value)
    return str(value)


def _last_user_message_text(value: Any) -> str:
    if isinstance(value, list):
        for item in reversed(value):
            if isinstance(item, tuple) and len(item) > 1:
                return str(item[1])
    return str(value)


def _json_from_messages(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        for item in reversed(value):
            if isinstance(item, tuple) and len(item) > 1:
                message_text = str(item[1]).strip()
                if message_text.startswith("{") and message_text.endswith("}"):
                    return json.loads(message_text)

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("FITORNOT_HOST", "0.0.0.0"),
        port=int(os.getenv("FITORNOT_PORT", "8000")),
        reload=bool(os.getenv("FITORNOT_RELOAD")),
    )
