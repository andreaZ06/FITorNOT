import asyncio
import importlib
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class MainDecisionApiTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
        sys.modules.pop("main", None)

    def tearDown(self):
        sys.modules.pop("main", None)

    def test_intent_slots_restricts_supported_categories(self):
        module = importlib.import_module("main")

        slots = module.IntentSlots(
            category="充电宝",
            brand="Anker",
            model="PowerCore",
            urls=["https://item.jd.com/1.html"],
        )

        self.assertEqual(slots.category, "充电宝")
        other = module.IntentSlots(category="其他", brand=None, model=None, urls=[])
        self.assertEqual(other.category, "其他")
        with self.assertRaises(Exception):
            module.IntentSlots(category="手机", brand="", model="", urls=[])

    def test_node_contracts_are_pydantic_models(self):
        module = importlib.import_module("main")

        retrieval_plan = module.RetrievalPlan(
            ecommerce_query="Anker PowerCore",
            xiaohongshu_queries=["Anker PowerCore 发热", "Anker PowerCore 虚标"],
        )
        findings = module.CleanedFindings(
            core_scandals=[
                module.RiskFinding(
                    issue="发热严重",
                    evidence="用户A: 充了十分钟烫得不敢手拿",
                    source="电商追评",
                )
            ],
            soft_drawbacks=[],
            noise_rate={"xiaohongshu": "中", "ecommerce": "低"},
        )
        scenario = module.ScenarioFit(
            user_profile_extracted="经常坐飞机，关注安检和发热",
            marketing_clash=None,
            suitability_analysis="发热对随身携带场景构成明显风险",
        )

        self.assertEqual(len(retrieval_plan.xiaohongshu_queries), 2)
        self.assertEqual(findings.core_scandals[0].source, "电商追评")
        self.assertIn("发热", scenario.suitability_analysis)

    def test_deepseek_llm_factory_uses_expected_models(self):
        module = importlib.import_module("main")

        chat_llm = module.build_deepseek_llm("deepseek-chat", temperature=0.0)
        reasoner_llm = module.build_deepseek_llm("deepseek-reasoner", temperature=0.1)

        self.assertEqual(chat_llm.model_name, "deepseek-chat")
        self.assertEqual(reasoner_llm.model_name, "deepseek-reasoner")
        self.assertEqual(str(chat_llm.openai_api_base), "https://api.deepseek.com/v1")

    def test_decision_graph_contains_required_nodes_and_edges(self):
        module = importlib.import_module("main")

        graph = module.build_decision_graph()
        graph_def = graph.get_graph()
        node_names = {node.id for node in graph_def.nodes.values()}
        edge_pairs = {(edge.source, edge.target) for edge in graph_def.edges}

        self.assertIn("planner_node", node_names)
        self.assertIn("retriever_node", node_names)
        self.assertIn("analyzer_node", node_names)
        self.assertIn("scenario_adapter_node", node_names)
        self.assertIn("generator_node", node_names)
        self.assertIn(("planner_node", "retriever_node"), edge_pairs)
        self.assertIn(("retriever_node", "analyzer_node"), edge_pairs)
        self.assertIn(("analyzer_node", "scenario_adapter_node"), edge_pairs)
        self.assertIn(("scenario_adapter_node", "generator_node"), edge_pairs)

    def test_system_prompts_are_attached_to_all_five_nodes(self):
        module = importlib.import_module("main")

        self.assertIn("消费意图解析专家", module.PLANNER_SYSTEM_PROMPT)
        self.assertIn("Bright Data MCP 调度官", module.RETRIEVER_SYSTEM_PROMPT)
        self.assertIn("数据审计师与去噪专家", module.ANALYZER_SYSTEM_PROMPT)
        self.assertIn("消费场景适配器", module.SCENARIO_ADAPTER_SYSTEM_PROMPT)
        self.assertIn("FITorNOT", module.GENERATOR_SYSTEM_PROMPT)

    def test_decision_endpoint_uses_mock_fallback_without_network(self):
        module = importlib.import_module("main")
        request = module.DecisionRequest(
            user_raw_input="想买 Anker 充电宝，看看发热和上飞机风险 https://item.jd.com/1.html",
            target_language="中文",
        )

        response = asyncio.run(module.create_decision(request, use_mock=True))

        self.assertEqual(response.slots.category, "充电宝")
        self.assertEqual(response.retrieval_plan.ecommerce_query, "Anker 充电宝")
        self.assertTrue(response.cleaned_findings.core_scandals)
        self.assertIn("坐飞机", response.scenario_fit.user_profile_extracted)
        self.assertIn("商品全局意图图谱", response.report)
        self.assertIn("跨平台数据交叉验证", response.report)
        self.assertIn("[数据源:", response.report)
        self.assertTrue(response.ecommerce_data)
        self.assertTrue(response.social_data)


    def test_brightdata_mcp_fetch_node_binds_tools_and_writes_back_state(self):
        module = importlib.import_module("main")
        os.environ["BRIGHTDATA_API_KEY"] = "brightdata-test-key"
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)
        captures = {}

        class FakeTool:
            def __init__(self, name, description, input_schema):
                self.name = name
                self.description = description
                self.inputSchema = input_schema

        class FakeBoundLLM:
            async def ainvoke(self, messages):
                captures["messages"] = messages
                return type(
                    "FakeResponse",
                    (),
                    {
                        "tool_calls": [
                            {"name": "brightdata__scrape", "args": {"url": slots.urls[0]}},
                            {
                                "name": "brightdata__scrape",
                                "args": {"query": retrieval_plan.xiaohongshu_queries[0]},
                            },
                        ]
                    },
                )()

        class FakeLLM:
            def bind_tools(self, tools):
                captures["bound_tools"] = tools
                return FakeBoundLLM()

        class FakeServerParameters:
            def __init__(self, command, args, env=None):
                captures["server_command"] = command
                captures["server_args"] = args
                captures["server_env"] = env or {}

        class FakeClientSession:
            def __init__(self, read_stream, write_stream):
                self.calls = []
                captures["session_streams"] = (read_stream, write_stream)

            async def __aenter__(self):
                captures["session_entered"] = True
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                captures["initialized"] = True

            async def list_tools(self):
                captures["listed_tools"] = True
                return [
                    FakeTool(
                        "brightdata__scrape",
                        "Scrape a public page by url or query",
                        {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "query": {"type": "string"},
                            },
                        },
                    )
                ]

            async def call_tool(self, tool_name, tool_arguments):
                self.calls.append((tool_name, tool_arguments))
                captures["tool_calls"] = list(self.calls)
                if tool_arguments.get("url"):
                    return {
                        "product_title": "Official SKU",
                        "parameters": ["20000mAh", "74Wh"],
                        "reviews": ["heavier than expected but usable"],
                    }
                return {
                    "notes": ["发热明显，通勤包里偏重"],
                    "comments": ["评论区说安检会看 Wh 标注"],
                }

        class FakeStdioClient:
            async def __aenter__(self):
                captures["stdio_entered"] = True
                return ("read_stream", "write_stream")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def fake_stdio_client(server_params):
            captures["server_params"] = server_params
            return FakeStdioClient()

        module.StdioServerParameters = FakeServerParameters
        module.ClientSession = FakeClientSession
        module.stdio_client = fake_stdio_client
        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()

        state = {
            "user_raw_input": "Need a flight-safe power bank with fewer heat complaints.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertEqual(captures["server_command"], "npx")
        self.assertEqual(captures["server_args"], ["-y", "@brightdata/mcp-server-scraper"])
        self.assertEqual(captures["server_env"]["BRIGHTDATA_API_KEY"], "brightdata-test-key")
        self.assertTrue(captures["initialized"])
        self.assertTrue(captures["listed_tools"])
        self.assertEqual(captures["bound_tools"][0]["function"]["name"], "brightdata__scrape")
        self.assertEqual(captures["tool_calls"][0], ("brightdata__scrape", {"url": slots.urls[0]}))
        self.assertEqual(
            captures["tool_calls"][1],
            ("brightdata__scrape", {"query": retrieval_plan.xiaohongshu_queries[0]}),
        )
        self.assertTrue(result["ecommerce_data"])
        self.assertTrue(result["xiaohongshu_data"])
        self.assertTrue(result["raw_data"].ecommerce_evidence)
        self.assertTrue(result["raw_data"].xiaohongshu_evidence)

    def test_brightdata_mcp_fetch_node_gracefully_degrades_on_mcp_errors(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        class FakeServerParameters:
            def __init__(self, command, args, env=None):
                self.command = command
                self.args = args
                self.env = env or {}

        class BrokenStdioClient:
            async def __aenter__(self):
                raise TimeoutError("429 rate limited")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        module.StdioServerParameters = FakeServerParameters
        module.ClientSession = type("FakeClientSession", (), {"__init__": lambda self, *_args, **_kwargs: None})
        module.stdio_client = lambda server_params: BrokenStdioClient()

        state = {
            "user_raw_input": "Need a reliable power bank.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertTrue(result["raw_data"].blocked_sources)
        self.assertIn("429 rate limited", result["raw_data"].blocked_sources[0]["reason"])
        self.assertTrue(result["ecommerce_data"])
        self.assertTrue(result["xiaohongshu_data"])


if __name__ == "__main__":
    unittest.main()
