from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResumeParseResult:
    text: str


@dataclass
class SkillExtractionResult:
    skills: list[str]


@dataclass
class PipelineResult:
    resume_path: Path
    resume_text: str
    skills: list[str]
    query: str
    jobs: list[dict[str, str]]
    ranked_jobs: list[dict[str, str | float]]
    csv_path: Path
