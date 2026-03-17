from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import DEFAULT_HR_CSV_NAME, GENERATED_DIR


LEAD_COLUMNS = [
    "job_id",
    "role",
    "company",
    "mail",
    "matched_skills",
    "matched_skills_count",
]


def build_hr_csv(jobs: list[dict[str, Any]], output_path: str | Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for job in jobs:
        job_id = str(job.get("job_id", ""))
        company = str(job.get("company", ""))
        title = str(job.get("role", job.get("title", "")))
        contact_email = str(job.get("mail", job.get("email", "")))
        matched_skills = str(job.get("matched_skills", ""))
        matched_skills_count = str(job.get("matched_skills_count", "0"))
        rows.append(
            {
                "job_id": job_id,
                "role": title,
                "company": company,
                "mail": contact_email,
                "matched_skills": matched_skills,
                "matched_skills_count": matched_skills_count,
            }
        )

    # Keep a stable schema even when rows is empty so downstream read_csv works.
    df = pd.DataFrame(rows, columns=LEAD_COLUMNS)

    target = Path(output_path) if output_path else (GENERATED_DIR / DEFAULT_HR_CSV_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)

    return df
