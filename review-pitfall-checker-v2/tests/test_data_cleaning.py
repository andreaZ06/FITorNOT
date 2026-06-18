import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class CleanAndFilterDataTest(unittest.TestCase):
    def test_filters_ecommerce_noise_extracts_specs_and_marks_critical_reviews(self):
        from data_cleaning import clean_and_filter_data

        raw_data = {
            "specs_html": """
                <div class='spec'>容量：20000mAh</div>
                <div class='spec'>额定能量：74Wh</div>
                <div class='spec'>快充：22.5W</div>
            """,
            "reviews": [
                "系统默认好评",
                "收到了",
                {"text": "很好"},
                {"text": "此用户没有填写评价"},
                {"text": "追加评论：用了两周开始发热，充电还断连两次"},
                {"text": "翻车了，外壳发热烫手，通勤不敢放包里"},
            ],
        }

        cleaned = clean_and_filter_data(raw_data, platform="jd", category="power_bank")

        self.assertIn("容量", cleaned["specs_text"])
        self.assertIn("20000mAh", cleaned["specs_text"])
        self.assertIn("74Wh", cleaned["specs_text"])
        self.assertEqual(len(cleaned["comments"]), 2)
        self.assertTrue(all(item["is_critical_issue"] for item in cleaned["comments"]))
        self.assertEqual(cleaned["comments"][0]["text"], "追加评论：用了两周开始发热，充电还断连两次")
        self.assertEqual(cleaned["noise_rate_estimate"], 0.67)

    def test_filters_xhs_marketing_notes_and_keeps_real_top_comments(self):
        from data_cleaning import clean_and_filter_data

        raw_data = {
            "notes": [
                {
                    "content": "姐妹们冲啊，宝藏单品，大数据推荐，这个真的是平替天花板，尊嘟假嘟！",
                    "top_comments": ["接广告吗", "求私信链接"],
                },
                {
                    "content": (
                        "我连敷三天，补水是有的，但第二天开始有点刺痛，鼻翼还发红。"
                        "后面减到一周一次就好很多，所以敏感肌别天天用。"
                    )
                    * 4,
                    "top_comments": [
                        "我也发红过两次，后面不敢连用",
                        "求私信",
                        {"text": "刺痛是真的，我下巴还长痘了"},
                    ],
                },
            ]
        }

        cleaned = clean_and_filter_data(raw_data, platform="xhs", category="facial_mask")

        self.assertEqual(len(cleaned["notes"]), 1)
        self.assertLessEqual(len(cleaned["notes"][0]["text"]), 500)
        self.assertEqual(len(cleaned["comments"]), 2)
        self.assertTrue(all(item["is_critical_issue"] for item in cleaned["comments"]))
        self.assertGreater(cleaned["noise_rate_estimate"], 0.0)

    def test_returns_empty_structure_on_malformed_input(self):
        from data_cleaning import clean_and_filter_data

        cleaned = clean_and_filter_data({"notes": object()}, platform="xhs", category="dog_food")

        self.assertEqual(cleaned["specs_text"], "")
        self.assertEqual(cleaned["comments"], [])
        self.assertEqual(cleaned["notes"], [])
        self.assertEqual(cleaned["noise_rate_estimate"], 0.0)


if __name__ == "__main__":
    unittest.main()
