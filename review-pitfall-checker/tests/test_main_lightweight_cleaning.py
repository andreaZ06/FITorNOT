import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.clean_reviews import lightweight_clean_reviews_text


class LightweightCleaningTest(unittest.TestCase):
    def test_removes_blank_and_emoji_only_lines_without_semantic_filtering(self) -> None:
        raw = "\n\n质量不好\n😀😀\n  \n好评返现但这里先交给 Dify 判断\n👍\n包装破了"

        cleaned = lightweight_clean_reviews_text(raw)

        self.assertEqual(cleaned, "质量不好\n好评返现但这里先交给 Dify 判断\n包装破了")


if __name__ == "__main__":
    unittest.main()
