import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "Cold_mail.py"))

from target_companies import get_target_companies


class TestTargetCompanies(unittest.TestCase):
    def test_clean_and_unique(self):
        companies = get_target_companies()
        self.assertGreater(len(companies), 50)

        lowered = [item.casefold() for item in companies]
        self.assertEqual(len(lowered), len(set(lowered)))

    def test_max_items(self):
        companies = get_target_companies(max_items=10)
        self.assertEqual(len(companies), 10)


if __name__ == "__main__":
    unittest.main()
