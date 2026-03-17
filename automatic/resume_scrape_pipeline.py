from __future__ import annotations

from pathlib import Path

import pdfplumber

from .careers_search import run_batch_search_multithreaded




def extract_resume_text(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    collected: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                collected.append(text)

    output = "\n".join(collected).strip()
    if not output:
        raise ValueError("No readable text found in resume PDF")
    return output


import re

def extract_resume_skills(resume_text: str) -> list[str]:
    # Extract all unique words (case-insensitive) from the resume text as skills
    words = re.findall(r"\b\w+\b", resume_text.lower())
    unique_skills = sorted(set(words))
    return unique_skills


def build_resume_search_terms(skills: list[str], max_skills: int = 3) -> str:
    selected = skills[: max(0, max_skills)]
    if not selected:
        return "careers"
    return "careers " + " ".join(selected)


def run_resume_scrape_pipeline(
    resume_path: str | Path,
    companies: list[str],
    wait_seconds: int = 10,
    pause_seconds: int = 5,
    max_workers: int = 4,
    max_attempts: int = 2,
    output_dir: str | Path = "automatic/generated",
    min_interval_seconds: float = 3.0,
    backoff_base_seconds: float = 1.5,
    block_cooldown_seconds: float = 8.0,
    max_skills: int = 3,
) -> tuple[str, list[str], str]:
    resume_text = extract_resume_text(resume_path)
    skills = extract_resume_skills(resume_text)
    search_terms = build_resume_search_terms(skills, max_skills=max_skills)

    run_batch_search_multithreaded(
        companies,
        wait_seconds=wait_seconds,
        pause_seconds=pause_seconds,
        max_workers=max_workers,
        max_attempts=max_attempts,
        output_dir=output_dir,
        min_interval_seconds=min_interval_seconds,
        backoff_base_seconds=backoff_base_seconds,
        block_cooldown_seconds=block_cooldown_seconds,
        search_terms=search_terms,
    )

    return resume_text, skills, search_terms
