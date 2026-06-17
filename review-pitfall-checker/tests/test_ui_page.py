import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import render_index_page


class UiPageTest(unittest.TestCase):
    def test_index_page_contains_core_workflow_controls(self) -> None:
        html = render_index_page()

        self.assertIn("FITorNOT", html)
        self.assertIn("HELLO", html)
        self.assertIn("font-family: Arial, sans-serif", html)
        self.assertIn("立即分析", html)
        self.assertIn("最近查询", html)
        self.assertIn("结论", html)
        self.assertIn("根据你最近的使用场景，推荐适合你的商品~", html)
        self.assertIn('id="product-id"', html)
        self.assertIn('id="user-scenario"', html)
        self.assertIn('id="reviews"', html)
        self.assertIn('id="analyze-form"', html)
        self.assertIn('id="new-analysis"', html)
        self.assertIn('fetch("/analyze"', html)
        self.assertIn("fatal_risks", html)


if __name__ == "__main__":
    unittest.main()
