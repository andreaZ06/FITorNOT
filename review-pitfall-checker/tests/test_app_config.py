import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import APP_NAME


class AppConfigTest(unittest.TestCase):
    def test_app_name_is_fitor_not(self) -> None:
        self.assertEqual(APP_NAME, "FITorNOT")


if __name__ == "__main__":
    unittest.main()
