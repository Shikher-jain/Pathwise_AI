import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "Cold_mail.py"))

from skill_extractor import extract_skills


class TestSkillExtractor(unittest.TestCase):
    def test_rule_based_extraction(self):
        text = "I work with Python, NLP, and Docker for machine learning systems."
        skills = [item.lower() for item in extract_skills(text)]
        self.assertIn("python", skills)
        self.assertIn("nlp", skills)
        self.assertIn("docker", skills)

    def test_no_duplicates(self):
        text = "Python python PYTHON"
        skills = [item.lower() for item in extract_skills(text, ["python"])]
        self.assertEqual(skills, ["python"])


if __name__ == "__main__":
    unittest.main()
