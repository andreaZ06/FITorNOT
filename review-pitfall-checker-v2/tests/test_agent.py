import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class FakeBrightDataClient:
    def __init__(self):
        self.calls = []

    def scrape(self, url):
        self.calls.append(url)
        if "jd.com" in url:
            return {
                "platform": "jd",
                "product_title": "Sample Power Bank 20000mAh",
                "parameters": {"capacity": "20000mAh", "rated_energy": "74Wh"},
                "reviews": [
                    {"text": "追加评论：用了两周发热明显，放包里不放心", "rating": 2},
                    {"text": "默认好评", "rating": 5},
                ],
            }
        if "xiaohongshu.com" in url:
            return {
                "platform": "xiaohongshu",
                "note_text": "出差带这个充电宝很方便，但有用户提醒机场会看 Wh 标注。",
                "likes": 320,
                "collects": 98,
                "comments": [
                    "真实体验：有点重，小包放不下",
                    "太绝了闭眼冲姐妹们",
                ],
            }
        raise RuntimeError("404 not found")


class FitOrNotBrightDataAgentTest(unittest.TestCase):
    def test_analyze_scrapes_each_url_and_returns_language_specific_report(self):
        from fitornot_brightdata_agent.agent import analyze_product_links

        client = FakeBrightDataClient()
        request = {
            "links": [
                "https://www.xiaohongshu.com/explore/sample",
                "https://item.jd.com/100000.html",
            ],
            "output_language": "中文",
        }

        result = analyze_product_links(request, brightdata_client=client)

        self.assertEqual(client.calls, request["links"])
        self.assertEqual(result["blocked_links"], [])
        self.assertEqual(result["language"], "中文")
        self.assertIn("## 📌 商品全局意图图谱", result["report"])
        self.assertIn("小红书 (种草/玩法)", result["report"])
        self.assertIn("电商平台 (价格/质量)", result["report"])
        self.assertIn("发热", result["report"])
        self.assertNotIn("默认好评", result["report"])

    def test_analyze_reports_blocked_links_without_inventing_data(self):
        from fitornot_brightdata_agent.agent import analyze_product_links

        client = FakeBrightDataClient()
        request = {
            "links": [
                "https://item.jd.com/100000.html",
                "https://item.taobao.com/item.htm?id=missing",
            ],
            "output_language": "English",
        }

        result = analyze_product_links(request, brightdata_client=client)

        self.assertEqual(client.calls, request["links"])
        self.assertEqual(
            result["blocked_links"],
            [
                {
                    "url": "https://item.taobao.com/item.htm?id=missing",
                    "reason": "404 not found",
                }
            ],
        )
        self.assertIn("Partial analysis", result["report"])
        self.assertIn("https://item.taobao.com/item.htm?id=missing", result["report"])
        self.assertIn("Sample Power Bank 20000mAh", result["report"])
        self.assertNotIn("taobao users said", result["report"])

    def test_analyze_requires_urls_and_brightdata_client(self):
        from fitornot_brightdata_agent.agent import analyze_product_links

        with self.assertRaises(ValueError):
            analyze_product_links({"links": [], "output_language": "中文"})

        with self.assertRaises(ValueError):
            analyze_product_links(
                {"links": ["https://item.jd.com/100000.html"], "output_language": "中文"}
            )


if __name__ == "__main__":
    unittest.main()
