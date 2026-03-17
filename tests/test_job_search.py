import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "Cold_mail.py"))

from job_search import build_query, build_query_variants
from job_search import _extract_first_email, _matches_query


class TestJobSearchUtilities(unittest.TestCase):
    def test_build_query_with_skills(self):
        skills = ["python", "nlp", "pytorch"]
        query = build_query(skills)
        self.assertIn("python", query)
        self.assertIn("internship", query)

    def test_build_query_fallback(self):
        query = build_query([])
        self.assertEqual(query, "python internship")

    def test_query_variants_include_company(self):
        variants = build_query_variants(["python"], ["OpenAI"])
        joined = " | ".join(variants).lower()
        self.assertIn("openai", joined)

    def test_extract_first_email_from_text(self):
        text = "For this role write to hiring@company.com with your resume."
        self.assertEqual(_extract_first_email(text), "hiring@company.com")

    def test_extract_first_email_when_missing(self):
        self.assertEqual(_extract_first_email("no email in this text"), "")

    def test_matches_query_finds_token_in_title(self):
        item = {"title": "Python Backend Intern", "description": "", "company_name": "Acme"}
        self.assertTrue(_matches_query(item, "python internship"))

    def test_matches_query_false_for_irrelevant_item(self):
        item = {"title": "Sales Manager", "description": "Retail operations", "company_name": "Acme"}
        self.assertFalse(_matches_query(item, "machine learning"))


if __name__ == "__main__":
    unittest.main()
