import asyncio
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class MainDecisionApiTest(unittest.TestCase):
    def setUp(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-key"
        os.environ.pop("FITORNOT_FORCE_COMPAT_LLM", None)
        os.environ.pop("FITORNOT_ENABLE_BROWSER_AUTOMATION", None)
        os.environ.pop("FITORNOT_BROWSER_CDP_URL", None)
        self._browser_profile_dir = tempfile.TemporaryDirectory()
        os.environ["FITORNOT_BROWSER_PROFILE_DIR"] = self._browser_profile_dir.name
        sys.modules.pop("main", None)

    def tearDown(self):
        os.environ.pop("FITORNOT_BROWSER_PROFILE_DIR", None)
        self._browser_profile_dir.cleanup()
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

    def test_deepseek_llm_factory_uses_compat_client_for_test_api_key(self):
        module = importlib.import_module("main")

        chat_llm = module.build_deepseek_llm("deepseek-chat", temperature=0.0)

        self.assertIsInstance(chat_llm, module._CompatChatOpenAI)

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

    def test_local_intent_parser_detects_power_bank_from_chinese_input(self):
        module = importlib.import_module("main")

        slots = module.infer_intent_slots_locally("我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀")

        self.assertEqual(slots.category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(slots.brand, "Anker")
        self.assertEqual(slots.model, "10000")

    def test_json_extractor_prefers_last_user_payload_over_prompt_examples(self):
        module = importlib.import_module("main")

        payload = module._json_from_messages(
            [
                (
                    "system",
                    '示例：{"ecommerce_query":"示例商品","xiaohongshu_queries":["示例 翻车","示例 真实评价"]}',
                ),
                (
                    "user",
                    '{"category":"充电宝","brand":"Anker","model":"10000","urls":[]}',
                ),
            ]
        )

        self.assertEqual(payload["category"], "充电宝")
        self.assertEqual(payload["brand"], "Anker")
        self.assertEqual(payload["model"], "10000")

    def test_retriever_node_survives_prompt_examples_in_compat_mode(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="10000",
            urls=[],
        )

        async def fake_fetch_node(state):
            state["raw_data"] = module.RawPlatformData(retrieval_plan=state["retrieval_plan"])
            state["ecommerce_data"] = []
            state["xiaohongshu_data"] = []
            state["blocked_sources"] = []
            state["fetch_status"] = "success"
            return state

        module.brightdata_mcp_fetch_node = fake_fetch_node

        state = {
            "user_raw_input": "我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
            "target_language": "中文",
            "slots": slots,
            "use_mock": False,
        }

        result = asyncio.run(module.retriever_node(state))

        self.assertEqual(result["retrieval_plan"].ecommerce_query, "Anker 10000 充电宝")
        self.assertEqual(len(result["retrieval_plan"].xiaohongshu_queries), 2)

    def test_planner_node_uses_user_text_in_compat_mode_without_prompt_pollution(self):
        module = importlib.import_module("main")

        state = {
            "user_raw_input": "我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
            "target_language": "中文",
            "use_mock": False,
        }

        result = asyncio.run(module.planner_node(state))

        self.assertEqual(result["slots"].category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(result["slots"].brand, "Anker")
        self.assertEqual(result["slots"].model, "10000")

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
        self.assertIn("Bright Data MCP 自动化数据调度员", captures["messages"][0][1])
        self.assertIn("brightdata__scrape_url", captures["messages"][0][1])
        self.assertIn("brightdata__search_keyword", captures["messages"][0][1])
        self.assertIn("user_bound_urls", captures["messages"][0][1])
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
        self.assertEqual(result["fetch_status"], "partial_failed")
        self.assertFalse(result["ecommerce_data"])
        self.assertFalse(result["xiaohongshu_data"])
        self.assertFalse(result["raw_data"].ecommerce_evidence)
        self.assertFalse(result["raw_data"].xiaohongshu_evidence)

    def test_brightdata_mcp_fetch_node_filters_noise_before_state_writeback(self):
        module = importlib.import_module("main")
        os.environ["BRIGHTDATA_API_KEY"] = "brightdata-test-key"
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        class FakeTool:
            def __init__(self, name, description, input_schema):
                self.name = name
                self.description = description
                self.inputSchema = input_schema

        class FakeBoundLLM:
            async def ainvoke(self, _messages):
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
            def bind_tools(self, _tools):
                return FakeBoundLLM()

        class FakeServerParameters:
            def __init__(self, command, args, env=None):
                self.command = command
                self.args = args
                self.env = env or {}

        class FakeClientSession:
            def __init__(self, _read_stream, _write_stream):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

            async def list_tools(self):
                return [
                    FakeTool(
                        "brightdata__scrape",
                        "Scrape a public page by url or query",
                        {"type": "object", "properties": {"url": {"type": "string"}, "query": {"type": "string"}}},
                    )
                ]

            async def call_tool(self, _tool_name, tool_arguments):
                if tool_arguments.get("url"):
                    return {
                        "specs_html": "<div>容量：20000mAh</div><div>额定能量：74Wh</div>",
                        "reviews": [
                            "系统默认好评",
                            "收到了",
                            {"text": "追加评论：用了两周开始发热，充电还断连两次"},
                        ],
                    }
                return {
                    "notes": [
                        {
                            "content": "姐妹们冲啊，宝藏单品，大数据推荐，这个真的是平替天花板！",
                            "top_comments": ["接广告吗"],
                        },
                        {
                            "content": "我出差用了一周，发热是有的，但安检主要会看 Wh 标注。",
                            "top_comments": ["我也觉得发热明显，夏天不太敢放包里"],
                        },
                    ]
                }

        class FakeStdioClient:
            async def __aenter__(self):
                return ("read_stream", "write_stream")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        module.StdioServerParameters = FakeServerParameters
        module.ClientSession = FakeClientSession
        module.stdio_client = lambda _server_params: FakeStdioClient()
        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()

        state = {
            "user_raw_input": "Need a travel power bank with fewer heat complaints.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        ecommerce_payload = result["ecommerce_data"][0]["payload"]
        xhs_payload = result["xiaohongshu_data"][0]["payload"]
        ecommerce_texts = [item["text"] for item in ecommerce_payload["comments"]]
        xhs_note_texts = [item["text"] for item in xhs_payload["notes"]]

        self.assertIn("追加评论：用了两周开始发热，充电还断连两次", ecommerce_texts)
        self.assertNotIn("系统默认好评", ecommerce_texts)
        self.assertNotIn("收到了", ecommerce_texts)
        self.assertTrue(any(item["is_critical_issue"] for item in ecommerce_payload["comments"]))
        self.assertEqual(len(xhs_payload["notes"]), 1)
        self.assertNotIn("姐妹们冲啊", xhs_note_texts[0])
        self.assertNotIn("系统默认好评", " ".join(item.text for item in result["raw_data"].ecommerce_evidence))


    def test_load_risk_dictionary_prefers_neon_rows_when_available(self):
        module = importlib.import_module("main")
        os.environ["NEON_DATABASE_URL"] = "postgresql://neon.example/db"
        captured = {}

        class FakeConnection:
            async def fetch(self, query, category):
                captured["query"] = query
                captured["category"] = category
                return [
                    {"term": "overheat", "risk_level": "critical"},
                    {"term": "flight banned", "risk_level": "veto"},
                    {"term": "heavy", "risk_level": "soft"},
                ]

            async def close(self):
                captured["closed"] = True

        class FakeAsyncpg:
            @staticmethod
            async def connect(dsn, timeout=None):
                captured["dsn"] = dsn
                captured["timeout"] = timeout
                return FakeConnection()

        module.asyncpg = FakeAsyncpg

        result = asyncio.run(module.load_risk_dictionary("power_bank"))

        self.assertEqual(captured["dsn"], "postgresql://neon.example/db")
        self.assertEqual(captured["category"], "power_bank")
        self.assertTrue(captured["closed"])
        self.assertEqual(result.source, "neon")
        self.assertIn("overheat", result.critical_terms)
        self.assertIn("flight banned", result.veto_terms)
        self.assertIn("heavy", result.soft_terms)

    def test_brightdata_fetch_writes_risk_dictionary_hits_back_to_state(self):
        module = importlib.import_module("main")
        os.environ["BRIGHTDATA_API_KEY"] = "brightdata-test-key"
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_load_risk_dictionary(category_key):
            self.assertEqual(category_key, "power_bank")
            return module.RiskDictionary(
                category_key=category_key,
                critical_terms=["overheat"],
                veto_terms=["flight banned"],
                soft_terms=["heavy"],
                source="neon",
            )

        class FakeTool:
            def __init__(self, name, description, input_schema):
                self.name = name
                self.description = description
                self.inputSchema = input_schema

        class FakeBoundLLM:
            async def ainvoke(self, _messages):
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
            def bind_tools(self, _tools):
                return FakeBoundLLM()

        class FakeServerParameters:
            def __init__(self, command, args, env=None):
                self.command = command
                self.args = args
                self.env = env or {}

        class FakeClientSession:
            def __init__(self, _read_stream, _write_stream):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

            async def list_tools(self):
                return [
                    FakeTool(
                        "brightdata__scrape",
                        "Scrape a public page by url or query",
                        {"type": "object", "properties": {"url": {"type": "string"}, "query": {"type": "string"}}},
                    )
                ]

            async def call_tool(self, _tool_name, tool_arguments):
                if tool_arguments.get("url"):
                    return {
                        "specs_html": "<div>capacity: 20000mAh</div>",
                        "reviews": [{"text": "follow-up: overheat and flight banned on airline"}],
                    }
                return {
                    "notes": [
                        {
                            "content": "Real travel use note",
                            "top_comments": ["heavy but usable", "flight banned at check-in"],
                        }
                    ]
                }

        class FakeStdioClient:
            async def __aenter__(self):
                return ("read_stream", "write_stream")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        module.load_risk_dictionary = fake_load_risk_dictionary
        module.StdioServerParameters = FakeServerParameters
        module.ClientSession = FakeClientSession
        module.stdio_client = lambda _server_params: FakeStdioClient()
        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()

        state = {
            "user_raw_input": "Need a flight-safe power bank.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertEqual(result["risk_dictionary"].source, "neon")
        self.assertIn("flight banned", result["ecommerce_data"][0]["payload"]["matched_veto_terms"])
        self.assertIn("heavy", result["xiaohongshu_data"][0]["payload"]["matched_soft_terms"])
        self.assertTrue(result["ecommerce_data"][0]["payload"]["comments"][0]["is_critical_issue"])

    def test_domestic_recall_fetch_builds_xhs_queries_from_top_ecommerce_candidates(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="10000",
            urls=[],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_ecommerce(query, category, limit):
            self.assertEqual(query, "Anker 10000 充电宝")
            self.assertEqual(category, module.SUPPORTED_CATEGORIES[0])
            self.assertEqual(limit, 20)
            return [
                {
                    "title": "Anker 10000mAh Nano",
                    "price": "149",
                    "shop_name": "Anker旗舰店",
                    "url": "https://item.jd.com/1.html",
                    "platform": "jd",
                },
                {
                    "title": "Anker 20000mAh PowerCore",
                    "price": "229",
                    "shop_name": "Anker京东自营",
                    "url": "https://item.jd.com/2.html",
                    "platform": "jd",
                },
            ]

        async def fake_xhs(queries, limit):
            self.assertEqual(limit, 10)
            self.assertTrue(any("发热" in query or "虚标" in query for query in queries))
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

        self.assertEqual(result.ecommerce_candidates[0]["title"], "Anker 10000mAh Nano")
        self.assertTrue(result.generated_xhs_queries)
        self.assertTrue(any("Anker 10000mAh Nano" in query for query in result.generated_xhs_queries))

    def test_domestic_recall_fetch_falls_back_cleanly_when_browser_tools_are_missing(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="10000",
            urls=[],
        )
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
        self.assertEqual(result.blocked_sources[0]["source"], "domestic_ecommerce")

    def test_fetch_ecommerce_candidates_uses_registered_browser_adapter(self):
        module = importlib.import_module("main")

        class FakeAdapter:
            async def fetch_ecommerce_candidates(self, query, category, limit=20):
                self.query = query
                self.category = category
                self.limit = limit
                return [
                    {
                        "title": "Anker 10000mAh Nano",
                        "price": "149",
                        "shop_name": "Anker旗舰店",
                        "url": "https://item.jd.com/1.html",
                        "platform": "jd",
                    }
                ]

        adapter = FakeAdapter()
        module.set_domestic_browser_adapter(adapter)

        result = asyncio.run(module.fetch_ecommerce_candidates("Anker 10000", module.SUPPORTED_CATEGORIES[0], limit=20))

        self.assertEqual(result[0]["title"], "Anker 10000mAh Nano")
        self.assertEqual(adapter.query, "Anker 10000")
        self.assertEqual(adapter.category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(adapter.limit, 20)

    def test_fetch_xiaohongshu_feedback_uses_registered_browser_adapter(self):
        module = importlib.import_module("main")

        class FakeAdapter:
            async def fetch_xiaohongshu_feedback(self, queries, limit=10):
                self.queries = list(queries)
                self.limit = limit
                return [
                    {
                        "query": queries[0],
                        "notes": [{"text": "说能上飞机，但有点热"}],
                        "comments": [{"text": "我带过，安检能过"}],
                    }
                ]

        adapter = FakeAdapter()
        module.set_domestic_browser_adapter(adapter)

        result = asyncio.run(module.fetch_xiaohongshu_feedback(["Anker 10000mAh Nano 避雷"], limit=10))

        self.assertEqual(result[0]["query"], "Anker 10000mAh Nano 避雷")
        self.assertEqual(adapter.queries, ["Anker 10000mAh Nano 避雷"])
        self.assertEqual(adapter.limit, 10)

    def test_default_domestic_browser_adapter_uses_factory_when_playwright_is_available(self):
        module = importlib.import_module("main")
        fake_adapter = object()
        module.build_default_domestic_browser_adapter = lambda: fake_adapter
        module.set_domestic_browser_adapter(None)

        adapter = module.get_domestic_browser_adapter()

        self.assertIs(adapter, fake_adapter)

    def test_browser_unavailable_error_mentions_playwright_installation(self):
        module = importlib.import_module("main")
        module.set_domestic_browser_adapter(None)
        module.build_default_domestic_browser_adapter = lambda: None

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(module.fetch_ecommerce_candidates("Anker 10000", module.SUPPORTED_CATEGORIES[0], limit=20))

        self.assertIn("pip install playwright", str(ctx.exception))

    def test_default_browser_adapter_requires_explicit_enable_flag(self):
        module = importlib.import_module("main")
        os.environ.pop("FITORNOT_ENABLE_BROWSER_AUTOMATION", None)
        module.set_domestic_browser_adapter(None)

        adapter = module.build_default_domestic_browser_adapter()

        self.assertIsNone(adapter)

    def test_default_browser_adapter_enables_when_cdp_session_is_configured(self):
        module = importlib.import_module("main")
        fake_adapter = object()
        original_adapter_class = module.PlaywrightDomesticBrowserAdapter
        os.environ.pop("FITORNOT_ENABLE_BROWSER_AUTOMATION", None)
        os.environ["FITORNOT_BROWSER_CDP_URL"] = "http://127.0.0.1:9222"
        module.set_domestic_browser_adapter(None)
        module.PlaywrightDomesticBrowserAdapter = lambda: fake_adapter

        try:
            adapter = module.build_default_domestic_browser_adapter()
        finally:
            module.PlaywrightDomesticBrowserAdapter = original_adapter_class
            os.environ.pop("FITORNOT_BROWSER_CDP_URL", None)

        self.assertIs(adapter, fake_adapter)

    def test_local_intent_parser_detects_power_bank_from_plain_chinese_input(self):
        module = importlib.import_module("main")

        slots = module.infer_intent_slots_locally("我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀")

        self.assertEqual(slots.category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(slots.brand, "Anker")
        self.assertEqual(slots.model, "10000")

    def test_planner_node_falls_back_when_structured_output_is_unavailable(self):
        module = importlib.import_module("main")

        class FakeStructuredLLM:
            async def ainvoke(self, _messages):
                raise RuntimeError("This response_format type is unavailable now")

        class FakeLLM:
            def with_structured_output(self, _schema):
                return FakeStructuredLLM()

        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()
        state = {
            "user_raw_input": "我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
            "target_language": "中文",
            "use_mock": False,
        }

        result = asyncio.run(module.planner_node(state))

        self.assertEqual(result["slots"].category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(result["slots"].brand, "Anker")
        self.assertEqual(result["slots"].model, "10000")

    def test_retriever_node_falls_back_when_structured_output_is_unavailable(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="10000",
            urls=[],
        )

        class FakeStructuredLLM:
            async def ainvoke(self, _messages):
                raise RuntimeError("This response_format type is unavailable now")

        class FakeLLM:
            def with_structured_output(self, _schema):
                return FakeStructuredLLM()

        async def fake_fetch_node(state):
            state["raw_data"] = module.RawPlatformData(retrieval_plan=state["retrieval_plan"])
            state["ecommerce_data"] = []
            state["xiaohongshu_data"] = []
            state["blocked_sources"] = []
            state["fetch_status"] = "success"
            return state

        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()
        module.brightdata_mcp_fetch_node = fake_fetch_node
        state = {
            "user_raw_input": "我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
            "target_language": "中文",
            "slots": slots,
            "use_mock": False,
        }

        result = asyncio.run(module.retriever_node(state))

        self.assertEqual(result["retrieval_plan"].ecommerce_query, "Anker 10000 充电宝")
        self.assertEqual(len(result["retrieval_plan"].xiaohongshu_queries), 2)

    def test_create_decision_falls_back_locally_when_deepseek_connection_fails(self):
        module = importlib.import_module("main")

        class FakeStructuredLLM:
            async def ainvoke(self, _messages):
                raise RuntimeError("Connection error.")

        class FakeLLM:
            def with_structured_output(self, _schema):
                return FakeStructuredLLM()

        async def fake_fetch_node(state):
            retrieval_plan = state["retrieval_plan"]
            state["raw_data"] = module.RawPlatformData(
                retrieval_plan=retrieval_plan,
                verified_specs={"容量": "10000mAh", "额定能量": "37Wh"},
                ecommerce_evidence=[
                    module.EvidenceItem(
                        source="电商追评",
                        text="到手能上飞机，但壳体会发热。",
                        platform="jd",
                    )
                ],
                xiaohongshu_evidence=[
                    module.EvidenceItem(
                        source="小红书真实评论",
                        text="安检会看 Wh 标注，37Wh 正常可带。",
                        platform="xiaohongshu",
                    )
                ],
            )
            state["ecommerce_data"] = [
                {
                    "title": "Anker 10000mAh Nano",
                    "price": "149",
                    "shop_name": "Anker旗舰店",
                    "url": "https://item.jd.com/1.html",
                    "platform": "jd",
                }
            ]
            state["xiaohongshu_data"] = [
                {
                    "query": retrieval_plan.xiaohongshu_queries[0],
                    "notes": [{"text": "安检会看 Wh 标注，37Wh 正常可带。"}],
                    "comments": [{"text": "能上飞机，但发热要注意。"}],
                }
            ]
            state["blocked_sources"] = []
            state["risk_dictionary"] = module._fallback_risk_dictionary("power_bank")
            state["fetch_status"] = "success"
            return state

        module.build_deepseek_llm = lambda model, temperature=0.0: FakeLLM()
        module.brightdata_mcp_fetch_node = fake_fetch_node

        result = asyncio.run(
            module.create_decision(
                module.DecisionRequest(
                    user_raw_input="我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
                    target_language="中文",
                    use_mock=False,
                )
            )
        )

        self.assertEqual(result.slots.category, module.SUPPORTED_CATEGORIES[0])
        self.assertEqual(result.retrieval_plan.ecommerce_query, "Anker 10000 充电宝")
        self.assertTrue(result.cleaned_findings.core_scandals)
        self.assertIn("Wh", result.report)
        self.assertTrue(result.ecommerce_data)
        self.assertTrue(result.social_data)

    def test_brightdata_mcp_fetch_node_stays_on_domestic_path_when_domestic_fetch_fails(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="10000",
            urls=[],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_domestic_fetch(_payload):
            return module.DomesticRecallOutput(
                raw_data=module.RawPlatformData(
                    retrieval_plan=retrieval_plan,
                    blocked_sources=[
                        {"source": "domestic_ecommerce", "reason": "captcha blocked"},
                        {"source": "xiaohongshu", "reason": "login required"},
                    ],
                ),
                ecommerce_candidates=[],
                generated_xhs_queries=list(retrieval_plan.xiaohongshu_queries),
                xiaohongshu_hits=[],
                ecommerce_data=[],
                xiaohongshu_data=[],
                blocked_sources=[
                    {"source": "domestic_ecommerce", "reason": "captcha blocked"},
                    {"source": "xiaohongshu", "reason": "login required"},
                ],
                fetch_status="partial_failed",
            )

        def explode(*_args, **_kwargs):
            raise AssertionError("Bright Data fallback should not be called")

        module.domestic_recall_fetch = fake_domestic_fetch
        module.StdioServerParameters = explode
        state = {
            "user_raw_input": "我想买Anker 10000毫安的充电宝但是我不知道它能不能上飞机呀",
            "target_language": "中文",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": [],
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
            "use_mock": False,
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertEqual(result["fetch_status"], "partial_failed")
        self.assertEqual(result["blocked_sources"][0]["source"], "domestic_ecommerce")
        self.assertEqual(result["blocked_sources"][1]["source"], "xiaohongshu")

    def test_brightdata_mcp_fetch_node_binds_tools_and_writes_back_state(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_domestic_fetch(_payload):
            return module.DomesticRecallOutput(
                raw_data=module.RawPlatformData(
                    retrieval_plan=retrieval_plan,
                    ecommerce_evidence=[
                        module.EvidenceItem(source="官方参数", text="Anker 10000mAh | 37Wh", platform="jd")
                    ],
                    xiaohongshu_evidence=[
                        module.EvidenceItem(source="小红书真实评论", text="能上飞机，但安检会看Wh", platform="xiaohongshu")
                    ],
                ),
                ecommerce_candidates=[
                    {
                        "title": "Anker 10000mAh Nano",
                        "price": "149",
                        "shop_name": "Anker旗舰店",
                        "url": "https://item.jd.com/1.html",
                        "platform": "jd",
                    }
                ],
                generated_xhs_queries=list(retrieval_plan.xiaohongshu_queries),
                xiaohongshu_hits=[
                    {
                        "query": retrieval_plan.xiaohongshu_queries[0],
                        "notes": [{"text": "能上飞机，但安检会看Wh"}],
                        "comments": [{"text": "我带过，没被拦"}],
                    }
                ],
                ecommerce_data=[
                    {
                        "title": "Anker 10000mAh Nano",
                        "price": "149",
                        "shop_name": "Anker旗舰店",
                        "url": "https://item.jd.com/1.html",
                        "platform": "jd",
                    }
                ],
                xiaohongshu_data=[
                    {
                        "query": retrieval_plan.xiaohongshu_queries[0],
                        "notes": [{"text": "能上飞机，但安检会看Wh"}],
                        "comments": [{"text": "我带过，没被拦"}],
                    }
                ],
                blocked_sources=[],
                fetch_status="success",
            )

        module.domestic_recall_fetch = fake_domestic_fetch
        state = {
            "user_raw_input": "Need a flight-safe power bank with fewer heat complaints.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertTrue(result["ecommerce_data"])
        self.assertTrue(result["xiaohongshu_data"])
        self.assertTrue(result["raw_data"].ecommerce_evidence)
        self.assertTrue(result["raw_data"].xiaohongshu_evidence)
        self.assertEqual(result["generated_xhs_queries"], list(retrieval_plan.xiaohongshu_queries))

    def test_brightdata_mcp_fetch_node_gracefully_degrades_on_mcp_errors(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)
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
        self.assertIn("Playwright browser adapter is unavailable", result["raw_data"].blocked_sources[0]["reason"])
        self.assertEqual(result["fetch_status"], "partial_failed")
        self.assertFalse(result["ecommerce_data"])
        self.assertFalse(result["xiaohongshu_data"])
        self.assertFalse(result["raw_data"].ecommerce_evidence)
        self.assertFalse(result["raw_data"].xiaohongshu_evidence)

    def test_brightdata_mcp_fetch_node_filters_noise_before_state_writeback(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_ecommerce(query, category, limit):
            self.assertEqual(query, "Anker A1647")
            self.assertEqual(category, module.SUPPORTED_CATEGORIES[0])
            self.assertEqual(limit, 20)
            return [
                {
                    "title": "Anker A1647 10000mAh",
                    "price": "149",
                    "shop_name": "Anker旗舰店",
                    "url": "https://item.jd.com/1.html",
                    "platform": "jd",
                }
            ]

        async def fake_xhs(queries, limit):
            self.assertEqual(limit, 10)
            self.assertTrue(queries)
            return [
                {
                    "query": queries[0],
                    "notes": [{"text": "我出差用了一周，发热是有的，但安检主要会看Wh标注。"}],
                    "comments": [{"text": "我也觉得发热明显，夏天不太敢放包里"}],
                }
            ]

        module.fetch_ecommerce_candidates = fake_ecommerce
        module.fetch_xiaohongshu_feedback = fake_xhs

        state = {
            "user_raw_input": "Need a travel power bank with fewer heat complaints.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertTrue(result["ecommerce_data"])
        self.assertTrue(result["xiaohongshu_data"])
        self.assertIn("Anker A1647 10000mAh", result["raw_data"].ecommerce_evidence[0].text)
        self.assertIn("发热", result["raw_data"].xiaohongshu_evidence[0].text)

    def test_brightdata_fetch_writes_risk_dictionary_hits_back_to_state(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(
            category=module.SUPPORTED_CATEGORIES[0],
            brand="Anker",
            model="A1647",
            urls=["https://item.jd.com/1.html"],
        )
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_load_risk_dictionary(_category_key):
            return module.RiskDictionary(
                category_key="power_bank",
                critical_terms=["overheat"],
                veto_terms=["flight banned"],
                soft_terms=["heavy"],
                source="neon",
            )

        async def fake_domestic_fetch(_payload):
            return module.DomesticRecallOutput(
                raw_data=module.RawPlatformData(
                    retrieval_plan=retrieval_plan,
                    ecommerce_evidence=[
                        module.EvidenceItem(
                            source="电商追评",
                            text="follow-up: overheat and flight banned on airline",
                            platform="jd",
                        )
                    ],
                    xiaohongshu_evidence=[
                        module.EvidenceItem(
                            source="小红书真实评论",
                            text="heavy but usable, flight banned at check-in",
                            platform="xiaohongshu",
                        )
                    ],
                ),
                ecommerce_candidates=[],
                generated_xhs_queries=list(retrieval_plan.xiaohongshu_queries),
                xiaohongshu_hits=[],
                ecommerce_data=[],
                xiaohongshu_data=[],
                blocked_sources=[],
                fetch_status="success",
            )

        module.load_risk_dictionary = fake_load_risk_dictionary
        module.domestic_recall_fetch = fake_domestic_fetch
        state = {
            "user_raw_input": "Need a flight-safe power bank.",
            "target_language": "English",
            "slots": slots,
            "retrieval_plan": retrieval_plan,
            "user_bound_urls": list(slots.urls),
            "generated_xhs_queries": list(retrieval_plan.xiaohongshu_queries),
        }

        result = asyncio.run(module.brightdata_mcp_fetch_node(state))

        self.assertEqual(result["risk_dictionary"].source, "neon")
        self.assertIn("flight banned", result["raw_data"].ecommerce_evidence[0].text)
        self.assertIn("heavy", result["raw_data"].xiaohongshu_evidence[0].text)

    def test_build_local_retrieval_plan_appends_category_for_numeric_power_bank_models(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(category="充电宝", brand="Anker", model="10000", urls=[])

        plan = module.build_local_retrieval_plan(slots)

        self.assertEqual(plan.ecommerce_query, "Anker 10000 充电宝")
        self.assertEqual(plan.xiaohongshu_queries[0], "Anker 10000 充电宝 发热")
        self.assertEqual(plan.xiaohongshu_queries[1], "Anker 10000 充电宝 虚标")

    def test_build_candidate_xhs_queries_uses_one_probe_per_top_five_candidates(self):
        module = importlib.import_module("main")

        queries = module.build_candidate_xhs_queries(
            [
                {"title": f"Anker 候选{i}", "price": "149", "shop_name": "Anker旗舰店", "url": "", "platform": "jd"}
                for i in range(1, 7)
            ],
            module.SUPPORTED_CATEGORIES[0],
        )

        self.assertEqual(len(queries), 5)
        self.assertEqual(queries[0], "Anker 候选1 避雷")
        self.assertEqual(queries[-1], "Anker 候选5 避雷")

    def test_domestic_recall_fetch_marks_empty_browser_results_as_partial_failure(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(category="充电宝", brand="Anker", model="10000", urls=[])
        retrieval_plan = module.build_local_retrieval_plan(slots)

        async def fake_ecommerce(_query, _category, limit):
            self.assertEqual(limit, 20)
            return []

        async def fake_xhs(queries, limit):
            self.assertEqual(limit, 10)
            self.assertTrue(queries)
            return []

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

        self.assertEqual(result.fetch_status, "partial_failed")
        self.assertFalse(result.ecommerce_candidates)
        self.assertFalse(result.xiaohongshu_hits)
        self.assertEqual(
            [item["source"] for item in result.blocked_sources],
            ["domestic_ecommerce", "xiaohongshu"],
        )
        self.assertIn("no browser results", result.blocked_sources[0]["reason"])
        self.assertIn("no browser results", result.blocked_sources[1]["reason"])

    def test_domestic_recall_fetch_adds_bootstrap_hint_when_trusted_session_is_required(self):
        module = importlib.import_module("main")
        slots = module.IntentSlots(category="充电宝", brand="Anker", model="10000", urls=[])
        retrieval_plan = module.build_local_retrieval_plan(slots)

        class FakeAdapter:
            profile_dir = Path("C:/tmp/fitornot/.browser-profile")

        async def blocked_ecommerce(_query, _category, limit):
            self.assertEqual(limit, 20)
            raise RuntimeError("JD search login required: use a trusted browser session.")

        async def blocked_xhs(_queries, limit):
            self.assertEqual(limit, 10)
            raise RuntimeError("Xiaohongshu search login required: use a trusted browser session.")

        module.fetch_ecommerce_candidates = blocked_ecommerce
        module.fetch_xiaohongshu_feedback = blocked_xhs
        module.set_domestic_browser_adapter(FakeAdapter())

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
        self.assertIn("FITORNOT_BROWSER_CDP_URL", result.blocked_sources[0]["reason"])
        self.assertIn(".browser-profile", result.blocked_sources[0]["reason"])
        self.assertIn("start_fitornot_browser.ps1", result.blocked_sources[0]["reason"])
        self.assertIn("log in once", result.blocked_sources[1]["reason"])


if __name__ == "__main__":
    unittest.main()
