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
        with self.assertRaises(Exception):
            module.IntentSlots(category="手机", brand="", model="", urls=[])

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

        self.assertIn("intent_parser_node", node_names)
        self.assertIn("brightdata_mcp_fetch_node", node_names)
        self.assertIn("fit_or_not_generator_node", node_names)
        self.assertIn(("intent_parser_node", "brightdata_mcp_fetch_node"), edge_pairs)
        self.assertIn(("brightdata_mcp_fetch_node", "fit_or_not_generator_node"), edge_pairs)

    def test_decision_endpoint_uses_mock_fallback_without_network(self):
        module = importlib.import_module("main")
        request = module.DecisionRequest(
            user_raw_input="想买 Anker 充电宝，看看发热和上飞机风险 https://item.jd.com/1.html",
            target_language="中文",
        )

        response = asyncio.run(module.create_decision(request, use_mock=True))

        self.assertEqual(response.slots.category, "充电宝")
        self.assertIn("商品全局意图图谱", response.report)
        self.assertIn("跨平台数据交叉验证", response.report)
        self.assertIn("[数据源:", response.report)
        self.assertTrue(response.ecommerce_data)
        self.assertTrue(response.social_data)


if __name__ == "__main__":
    unittest.main()
