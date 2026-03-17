from __future__ import annotations

import logging
import re
from pathlib import Path

from config import DEFAULT_HR_CSV_NAME, GENERATED_DIR, SEARCH_MAX_WORKERS, UPLOADS_DIR
from lead_builder import build_hr_csv
from job_ranker import rank_jobs
from job_search import build_query, build_query_variants, search_jobs_multi
from resume_parser import extract_text
from settings import load_settings
from skill_extractor import extract_skills
from models import PipelineResult


_SETTINGS = load_settings()
logger = logging.getLogger(__name__)


def _debug_log(message: str, *args: object) -> None:
    logger.info(message, *args)
    try:
        print(message % args if args else message)
    except Exception:
        print(message)


def _find_matching_skills(job: dict[str, str | float], skills: list[str]) -> list[str]:
    title = str(job.get("title", job.get("role", ""))).lower()
    description = str(job.get("description", "")).lower()
    haystack = f"{title} {description}"

    matches: list[str] = []
    seen = set()
    for skill in skills:
        normalized = skill.strip().lower()
        if not normalized or normalized in seen:
            continue

        if " " in normalized:
            is_match = normalized in haystack
        else:
            is_match = re.search(rf"\b{re.escape(normalized)}\b", haystack) is not None

        if is_match:
            matches.append(normalized)
            seen.add(normalized)
    return matches


def _build_emergency_fallback_jobs(
    skills: list[str],
    location: str,
    job_type: str,
    top_n: int,
) -> list[dict[str, str]]:
    """Create guaranteed fallback rows when external APIs are unavailable."""
    safe_skills = [item.strip().lower() for item in skills if item and item.strip()]
    primary_skill = safe_skills[0] if safe_skills else "python"
    role_prefix = "Intern" if job_type.lower() == "internship" else "Developer"
    role = f"{primary_skill.title()} {role_prefix}".strip()
    location_value = location.strip() or "Remote"

    rows: list[dict[str, str]] = []
    count = max(1, min(top_n, 5))
    for index in range(1, count + 1):
        company = f"Target Company {index}"
        matched = ", ".join(safe_skills[:3])
        rows.append(
            {
                "job_id": f"fallback-{index}",
                "company": company,
                "role": role,
                "title": role,
                "location": location_value,
                "url": "",
                "description": (
                    f"Fallback opportunity for {role}. Generated because external APIs returned no jobs."
                ),
                "mail": "",
                "email": "",
                "source": "EmergencyFallback",
                "source_url": "",
                "matched_skills": matched,
                "matched_skills_count": str(len([s for s in safe_skills[:3] if s])),
            }
        )
    return rows


def sanitize_user_id(email: str) -> str:
    return email.replace("@", "_at_").replace(".", "_").replace("/", "_").lower()


def run_resume_to_leads_pipeline(
    user_email: str,
    user_id: int,
    resume_bytes: bytes,
    top_n: int = 20,
    query_override: str | None = None,
    skills_override: list[str] | None = None,
    target_companies: list[str] | None = None,
    max_workers: int = SEARCH_MAX_WORKERS,
    max_requests: int | None = None,
    location: str = "",
    job_type: str = "",
    experience_level: str = "",
) -> PipelineResult:
    user_id = sanitize_user_id(user_email)

    _debug_log(
        "[pipeline] start user=%r top_n=%s location=%r job_type=%r experience_level=%r",
        user_id,
        top_n,
        location,
        job_type,
        experience_level,
    )

    user_resume_dir = UPLOADS_DIR / user_id
    user_resume_dir.mkdir(parents=True, exist_ok=True)
    resume_path = user_resume_dir / "resume.pdf"

    with open(resume_path, "wb") as fh:
        fh.write(resume_bytes)

    resume_text = extract_text(str(resume_path))
    _debug_log("[pipeline] resume extracted chars=%s", len(resume_text))
    extracted_skills = extract_skills(resume_text)
    skills = [item.strip().lower() for item in (skills_override or extracted_skills) if item and item.strip()]
    _debug_log("[pipeline] skills_detected=%s sample=%s", len(skills), skills[:10])
    query = query_override.strip() if query_override else build_query(
        skills,
        job_type=job_type,
        experience_level=experience_level,
        location=location,
    )
    if query_override and query_override.strip():
        queries = [query_override.strip()]
        for company in (target_companies or [])[:8]:
            queries.append(f"{query_override.strip()} {company}")
    else:
        queries = build_query_variants(skills, target_companies)

    _debug_log("[pipeline] query_primary=%r", query)
    _debug_log("[pipeline] queries_sent=%s", queries)

    # Pass location and job_type to job search
    jobs = search_jobs_multi(
        queries,
        timeout=_SETTINGS.remotive_timeout_seconds,
        max_workers=max_workers,
        api_url=_SETTINGS.remotive_api_url,
        user_agent=_SETTINGS.remotive_user_agent,
        max_requests=max_requests or _SETTINGS.remotive_max_requests_per_run,
        location=location,
        job_type=job_type,
        adzuna_api_url=_SETTINGS.adzuna_api_url,
        adzuna_app_id=_SETTINGS.adzuna_app_id,
        adzuna_api_key=_SETTINGS.adzuna_api_key,
        adzuna_country=_SETTINGS.adzuna_country,
        adzuna_results_per_page=_SETTINGS.adzuna_results_per_page,
        jooble_api_url=_SETTINGS.jooble_api_url,
        jooble_api_key=_SETTINGS.jooble_api_key,
        jooble_location=_SETTINGS.jooble_location,
        jooble_results_per_page=_SETTINGS.jooble_results_per_page,
    )
    _debug_log("[pipeline] jobs_after_multi_search=%s", len(jobs))

    if not jobs:
        broad_queries = ["developer", "internship", "python developer"]
        _debug_log(
            "[pipeline] no jobs found; retrying broad fallback queries=%s with no location/job_type filters",
            broad_queries,
        )
        jobs = search_jobs_multi(
            broad_queries,
            timeout=_SETTINGS.remotive_timeout_seconds,
            max_workers=max_workers,
            api_url=_SETTINGS.remotive_api_url,
            user_agent=_SETTINGS.remotive_user_agent,
            max_requests=max_requests or _SETTINGS.remotive_max_requests_per_run,
            location="",
            job_type="",
            adzuna_api_url=_SETTINGS.adzuna_api_url,
            adzuna_app_id=_SETTINGS.adzuna_app_id,
            adzuna_api_key=_SETTINGS.adzuna_api_key,
            adzuna_country=_SETTINGS.adzuna_country,
            adzuna_results_per_page=_SETTINGS.adzuna_results_per_page,
            jooble_api_url=_SETTINGS.jooble_api_url,
            jooble_api_key=_SETTINGS.jooble_api_key,
            jooble_location="",
            jooble_results_per_page=_SETTINGS.jooble_results_per_page,
        )
        _debug_log("[pipeline] jobs_after_broad_fallback=%s", len(jobs))

    # Filter by experience_level if set
    if experience_level:
        before_filter = len(jobs)
        exp_kw = experience_level.lower()
        jobs = [job for job in jobs if exp_kw in job.get("title", "").lower() or exp_kw in job.get("description", "").lower()]
        _debug_log(
            "[pipeline] jobs_after_experience_filter=%s (before=%s keyword=%r)",
            len(jobs),
            before_filter,
            exp_kw,
        )

    ranked_jobs = rank_jobs(resume_text, jobs)
    _debug_log("[pipeline] ranked_jobs_count=%s", len(ranked_jobs))
    top_jobs = ranked_jobs[:top_n]

    matched_any_count = 0
    for job in top_jobs:
        matched_skills = _find_matching_skills(job, skills)
        if matched_skills:
            matched_any_count += 1
        job["matched_skills"] = ", ".join(matched_skills)
        job["matched_skills_count"] = str(len(matched_skills))

    matched_jobs = [job for job in top_jobs if int(str(job.get("matched_skills_count", "0"))) > 0]
    csv_jobs = matched_jobs if matched_jobs else top_jobs

    # If still empty, run broadest possible fallback and add at least one job
    if not csv_jobs:
        _debug_log("[pipeline] no jobs matched even after fallback; forcing broadest search.")
        broad_queries = ["internship", "developer", "python", "data", "ai", "ml"]
        jobs = search_jobs_multi(
            broad_queries,
            timeout=_SETTINGS.remotive_timeout_seconds,
            max_workers=max_workers,
            api_url=_SETTINGS.remotive_api_url,
            user_agent=_SETTINGS.remotive_user_agent,
            max_requests=max_requests or _SETTINGS.remotive_max_requests_per_run,
            location="",
            job_type="",
            adzuna_api_url=_SETTINGS.adzuna_api_url,
            adzuna_app_id=_SETTINGS.adzuna_app_id,
            adzuna_api_key=_SETTINGS.adzuna_api_key,
            adzuna_country=_SETTINGS.adzuna_country,
            adzuna_results_per_page=_SETTINGS.adzuna_results_per_page,
            jooble_api_url=_SETTINGS.jooble_api_url,
            jooble_api_key=_SETTINGS.jooble_api_key,
            jooble_location="",
            jooble_results_per_page=_SETTINGS.jooble_results_per_page,
        )
        ranked_jobs = rank_jobs(resume_text, jobs)
        csv_jobs = ranked_jobs[:max(1, top_n)]
        for job in csv_jobs:
            job["matched_skills"] = ""
            job["matched_skills_count"] = "0"
        _debug_log("[pipeline] broadest fallback jobs count=%s", len(csv_jobs))

    if not csv_jobs:
        csv_jobs = _build_emergency_fallback_jobs(
            skills=skills,
            location=location,
            job_type=job_type,
            top_n=top_n,
        )
        _debug_log("[pipeline] emergency fallback generated rows=%s", len(csv_jobs))

    _debug_log(
        "[pipeline] top_jobs=%s jobs_with_skill_match=%s csv_rows=%s",
        len(top_jobs),
        matched_any_count,
        len(csv_jobs),
    )

    csv_path = GENERATED_DIR / f"user_{user_id}" / DEFAULT_HR_CSV_NAME
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    build_hr_csv(csv_jobs, output_path=csv_path)
    _debug_log("[pipeline] csv_written path=%s rows=%s", csv_path, len(csv_jobs))

    return PipelineResult(
        resume_path=resume_path,
        resume_text=resume_text,
        skills=skills,
        query=query,
        jobs=jobs,
        ranked_jobs=top_jobs,
        csv_path=csv_path,
    )
