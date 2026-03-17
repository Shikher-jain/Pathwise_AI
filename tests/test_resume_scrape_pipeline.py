import unittest

from automatic.resume_scrape_pipeline import build_resume_search_terms, extract_resume_skills


class TestResumeScrapePipeline(unittest.TestCase):
    def test_extract_resume_skills_finds_matches(self):
        text = "Built backend APIs in Python and Docker for machine learning systems."
        skills = [item.lower() for item in extract_resume_skills(text)]
        self.assertIn("python", skills)
        self.assertIn("docker", skills)
        self.assertIn("machine learning", skills)

    def test_build_resume_search_terms_uses_fallback(self):
        terms = build_resume_search_terms([])
        self.assertEqual(terms, "careers")

    def test_build_resume_search_terms_caps_skills(self):
        terms = build_resume_search_terms(["python", "nlp", "sql", "docker"], max_skills=2)
        self.assertEqual(terms, "careers python nlp")


if __name__ == "__main__":
    unittest.main()
