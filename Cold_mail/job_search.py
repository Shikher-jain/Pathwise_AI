from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Any

import requests

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
REMOTIVE_SOURCE_NAME = "Remotive"
ADZUNA_SOURCE_NAME = "Adzuna"
JOOBLE_SOURCE_NAME = "Jooble"
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
logger = logging.getLogger(__name__)


def _debug_log(message: str, *args: Any) -> None:
    """Log to logger and stdout so debug info is visible in all run modes."""
    logger.info(message, *args)
    try:
        print(message % args if args else message)
    except Exception:
        # Keep pipeline resilient if formatting fails unexpectedly.
        print(message)


def _safe_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _extract_first_email(text: str) -> str:
    if not text:
        return ""
    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else ""


def _query_tokens(query: str) -> list[str]:
    return [token for token in query.lower().split() if len(token) >= 3]


def _relaxed_query(query: str) -> str:
    tokens = _query_tokens(query)
    if not tokens:
        return query.strip()
    return tokens[0]


def _matches_query(item: dict[str, Any], query: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True

    title = _safe_str(item.get("title")).lower()
    description = _safe_str(item.get("description")).lower()
    company = _safe_str(item.get("company_name")).lower()
    haystack = f"{title} {description} {company}"
    return any(token in haystack for token in tokens)


@lru_cache(maxsize=1)
def _fetch_latest_jobs_payload(timeout: int, api_url: str, user_agent: str) -> list[dict[str, Any]]:
    response = requests.get(
        api_url,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("jobs", []))


def build_query(
    skills: list[str],
    job_type: str = "",
    experience_level: str = "",
    location: str = "",
    default: str = "python internship"
) -> str:
    """Build a primary search query from detected skills and selected filters."""
    parts = []
    # Use up to 5 skills for richer queries
    top_skills = [skill for skill in skills[:5] if skill]
    if top_skills:
        parts.extend(top_skills)
    # Add synonyms for common skills
    synonyms = {
        "ml": "machine learning",
        "ai": "artificial intelligence",
        "ds": "data science",
        "cv": "computer vision",
        "devops": "devops",
        "nlp": "natural language processing",
    }
    for skill in top_skills:
        if skill.lower() in synonyms and synonyms[skill.lower()] not in parts:
            parts.append(synonyms[skill.lower()])
    # Add experience level and job type if set
    if experience_level and experience_level.lower() not in parts:
        parts.append(experience_level.lower())
    if job_type and job_type.lower() not in parts:
        parts.append(job_type.lower())
    # Add location if set
    if location:
        parts.append(location)
    # Fallback to default if nothing
    if not parts:
        return default
    return " ".join(parts)


def build_query_variants(skills: list[str], target_companies: list[str] | None = None) -> list[str]:
    """Generate diversified search queries for broader job discovery."""
    base = build_query(skills)
    variants = [
        base,
        f"{base} remote",
        f"{base} machine learning",
        f"{base} backend",
        "python internship",
        "machine learning internship",
        "backend internship",
    ]

    for skill in [item.strip() for item in skills[:4] if item and item.strip()]:
        variants.append(f"{skill} internship")

    if target_companies:
        # Cap to avoid excessive external requests.
        for company in target_companies[:8]:
            variants.append(f"{base} {company}")

    # Keep order while removing duplicates/empties.
    seen = set()
    unique: list[str] = []
    for item in variants:
        q = item.strip()
        if q and q not in seen:
            unique.append(q)
            seen.add(q)
    return unique


def _normalize_queries(queries: list[str], max_requests: int) -> list[str]:
    """Deduplicate and cap query list to stay within API request budget."""
    unique: list[str] = []
    seen = set()
    for query in queries:
        normalized = query.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
        if len(unique) >= max_requests:
            break
    return unique


@lru_cache(maxsize=128)
def _fetch_jobs_cached(query: str, timeout: int, api_url: str, user_agent: str) -> list[dict[str, str]]:
    """Cache Remotive search responses by query to avoid repeated API calls."""
    response = requests.get(
        api_url,
        params={"search": query},
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    source_items = list(payload.get("jobs", []))
    if not source_items:
        source_items = [
            item
            for item in _fetch_latest_jobs_payload(timeout, api_url, user_agent)
            if _matches_query(item, query)
        ]

    jobs: list[dict[str, str]] = []
    for item in source_items:
        job_id = _safe_str(item.get("id"))
        company = _safe_str(item.get("company_name"))
        title = _safe_str(item.get("title"))
        location = _safe_str(item.get("candidate_required_location"))
        link = _safe_str(item.get("url"))
        description = _safe_str(item.get("description"))
        contact_email = _extract_first_email(description)

        if company and title:
            jobs.append(
                {
                    "job_id": job_id,
                    "company": company,
                    "role": title,
                    "title": title,
                    "location": location,
                    "url": link,
                    "mail": contact_email,
                    "email": contact_email,
                    "source": REMOTIVE_SOURCE_NAME,
                    "source_url": link,
                }
            )
    return jobs


def search_jobs(
    query: str,
    timeout: int = 20,
    api_url: str = REMOTIVE_API,
    user_agent: str = "ai-job-hunter-cold-mailer/1.0 (+https://remotive.com)",
    location: str = "",
    job_type: str = "",
) -> list[dict[str, str]]:
    """Fetch jobs from Remotive API for a single query, with optional location/job_type filters."""
    if not query.strip():
        return []
    _debug_log(
        "[search_jobs][remotive] query=%r location=%r job_type=%r",
        query.strip(),
        location,
        job_type,
    )
    params = {"search": query.strip()}
    if location:
        params["location"] = location
    if job_type:
        params["job_type"] = job_type
    response = requests.get(
        api_url,
        params=params,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    source_items = list(payload.get("jobs", []))
    _debug_log("[search_jobs][remotive] api_results=%s query=%r", len(source_items), query.strip())
    if not source_items:
        # Remotive can return an empty set for strict query filters.
        # Fallback to latest jobs and apply local token matching.
        source_items = [
            item
            for item in _fetch_latest_jobs_payload(timeout, api_url, user_agent)
            if _matches_query(item, query)
        ]

    jobs: list[dict[str, str]] = []
    for item in source_items:
        job_id = _safe_str(item.get("id"))
        company = _safe_str(item.get("company_name"))
        title = _safe_str(item.get("title"))
        location_val = _safe_str(item.get("candidate_required_location"))
        link = _safe_str(item.get("url"))
        description = _safe_str(item.get("description"))
        contact_email = _extract_first_email(description)
        if company and title:
            jobs.append({
                "job_id": job_id,
                "company": company,
                "role": title,
                "title": title,
                "location": location_val,
                "url": link,
                "description": description,
                "mail": contact_email,
                "email": contact_email,
                "source": REMOTIVE_SOURCE_NAME,
                "source_url": link,
            })
    return jobs


def search_jobs_adzuna(
    query: str,
    timeout: int,
    api_url: str,
    app_id: str,
    api_key: str,
    country: str,
    results_per_page: int,
) -> list[dict[str, str]]:
    if not query.strip() or not app_id or not api_key:
        _debug_log(
            "[search_jobs][adzuna] skipped query=%r app_id_present=%s api_key_present=%s",
            query,
            bool(app_id),
            bool(api_key),
        )
        return []

    url = f"{api_url.rstrip('/')}/{country}/search/1"
    def _fetch(what: str) -> list[dict[str, Any]]:
        _debug_log("[search_jobs][adzuna] request what=%r url=%r", what, url)
        response = requests.get(
            url,
            params={
                "app_id": app_id,
                "app_key": api_key,
                "what": what,
                "results_per_page": max(1, results_per_page),
                "content-type": "application/json",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return list(payload.get("results", []))

    source_items = _fetch(query.strip())
    _debug_log("[search_jobs][adzuna] api_results=%s query=%r", len(source_items), query.strip())
    if not source_items:
        relaxed = _relaxed_query(query)
        if relaxed and relaxed != query.strip():
            _debug_log("[search_jobs][adzuna] fallback_relaxed_query=%r", relaxed)
            source_items = _fetch(relaxed)
            _debug_log("[search_jobs][adzuna] fallback_results=%s query=%r", len(source_items), relaxed)

    jobs: list[dict[str, str]] = []
    for item in source_items:
        job_id = _safe_str(item.get("id"))
        company = _safe_str((item.get("company") or {}).get("display_name"))
        title = _safe_str(item.get("title"))
        location = _safe_str((item.get("location") or {}).get("display_name"))
        link = _safe_str(item.get("redirect_url"))
        description = _safe_str(item.get("description"))
        contact_email = _extract_first_email(description)

        if company and title:
            jobs.append(
                {
                    "job_id": job_id,
                    "company": company,
                    "role": title,
                    "title": title,
                    "location": location,
                    "url": link,
                    "description": description,
                    "mail": contact_email,
                    "email": contact_email,
                    "source": ADZUNA_SOURCE_NAME,
                    "source_url": link,
                }
            )
    return jobs


def search_jobs_jooble(
    query: str,
    timeout: int,
    api_url: str,
    api_key: str,
    location: str,
    results_per_page: int,
) -> list[dict[str, str]]:
    if not query.strip() or not api_key:
        _debug_log(
            "[search_jobs][jooble] skipped query=%r api_key_present=%s",
            query,
            bool(api_key),
        )
        return []

    url = f"{api_url.rstrip('/')}/{api_key}"
    def _fetch(keywords: str, location_value: str) -> list[dict[str, Any]]:
        _debug_log(
            "[search_jobs][jooble] request keywords=%r location=%r",
            keywords,
            location_value,
        )
        response = requests.post(
            url,
            json={
                "keywords": keywords,
                "location": location_value,
                "page": 1,
            },
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        return list(data.get("jobs", []))

    source_items = _fetch(query.strip(), location.strip())
    _debug_log("[search_jobs][jooble] api_results=%s query=%r", len(source_items), query.strip())
    if not source_items:
        source_items = _fetch(_relaxed_query(query), location.strip())
        _debug_log(
            "[search_jobs][jooble] fallback_relaxed_results=%s query=%r location=%r",
            len(source_items),
            _relaxed_query(query),
            location.strip(),
        )
    if not source_items and location.strip():
        source_items = _fetch(_relaxed_query(query), "")
        _debug_log(
            "[search_jobs][jooble] fallback_no_location_results=%s query=%r",
            len(source_items),
            _relaxed_query(query),
        )

    jobs: list[dict[str, str]] = []
    for item in source_items[: max(1, results_per_page)]:
        job_id = _safe_str(item.get("id") or item.get("link"))
        company = _safe_str(item.get("company"))
        title = _safe_str(item.get("title"))
        location_value = _safe_str(item.get("location"))
        link = _safe_str(item.get("link"))
        description = _safe_str(item.get("snippet") or item.get("description"))
        contact_email = _extract_first_email(description)

        if company and title:
            jobs.append(
                {
                    "job_id": job_id,
                    "company": company,
                    "role": title,
                    "title": title,
                    "location": location_value,
                    "url": link,
                    "description": description,
                    "mail": contact_email,
                    "email": contact_email,
                    "source": JOOBLE_SOURCE_NAME,
                    "source_url": link,
                }
            )
    return jobs


def _search_all_sources_for_query(
    query: str,
    timeout: int,
    remotive_api_url: str,
    remotive_user_agent: str,
    location: str,
    job_type: str,
    adzuna_api_url: str,
    adzuna_app_id: str,
    adzuna_api_key: str,
    adzuna_country: str,
    adzuna_results_per_page: int,
    jooble_api_url: str,
    jooble_api_key: str,
    jooble_location: str,
    jooble_results_per_page: int,
) -> list[dict[str, str]]:
    futures = []
    merged: list[dict[str, str]] = []
    seen = set()
    future_to_source: dict[Any, str] = {}

    _debug_log("[search_jobs][query] sending=%r", query)

    with ThreadPoolExecutor(max_workers=3) as executor:
        remotive_future = executor.submit(
            search_jobs,
            query,
            timeout,
            remotive_api_url,
            remotive_user_agent,
            location,
            job_type,
        )
        futures.append(remotive_future)
        future_to_source[remotive_future] = REMOTIVE_SOURCE_NAME

        if adzuna_app_id and adzuna_api_key:
            adzuna_future = executor.submit(
                search_jobs_adzuna,
                query,
                timeout,
                adzuna_api_url,
                adzuna_app_id,
                adzuna_api_key,
                adzuna_country,
                adzuna_results_per_page,
            )
            futures.append(adzuna_future)
            future_to_source[adzuna_future] = ADZUNA_SOURCE_NAME
        else:
            _debug_log("[search_jobs][%s] skipped due to missing credentials", ADZUNA_SOURCE_NAME)

        if jooble_api_key:
            jooble_future = executor.submit(
                search_jobs_jooble,
                query,
                timeout,
                jooble_api_url,
                jooble_api_key,
                jooble_location or location,
                jooble_results_per_page,
            )
            futures.append(jooble_future)
            future_to_source[jooble_future] = JOOBLE_SOURCE_NAME
        else:
            _debug_log("[search_jobs][%s] skipped due to missing API key", JOOBLE_SOURCE_NAME)

        for future in as_completed(futures):
            source_name = future_to_source.get(future, "unknown")
            try:
                results = future.result()
            except Exception as exc:
                _debug_log("[search_jobs][%s] error query=%r error=%s", source_name, query, exc)
                continue

            _debug_log("[search_jobs][%s] returned=%s query=%r", source_name, len(results), query)
            if not results:
                _debug_log("[search_jobs][%s] empty response for query=%r", source_name, query)

            for job in results:
                key = (
                    job.get("source", ""),
                    job.get("company", "").lower(),
                    job.get("title", "").lower(),
                    job.get("url", ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(job)

    _debug_log("[search_jobs][query] merged_total=%s query=%r", len(merged), query)
    return merged


async def search_jobs_async(
    queries: list[str],
    timeout: int = 20,
    max_workers: int = 6,
    api_url: str = REMOTIVE_API,
    user_agent: str = "ai-job-hunter-cold-mailer/1.0 (+https://remotive.com)",
    max_requests: int = 4,
    location: str = "",
    job_type: str = "",
    adzuna_api_url: str = "https://api.adzuna.com/v1/api/jobs",
    adzuna_app_id: str = "",
    adzuna_api_key: str = "",
    adzuna_country: str = "in",
    adzuna_results_per_page: int = 20,
    jooble_api_url: str = "https://jooble.org/api",
    jooble_api_key: str = "",
    jooble_location: str = "India",
    jooble_results_per_page: int = 20,
) -> list[dict[str, str]]:
    normalized_queries = _normalize_queries(queries, max_requests)
    if not normalized_queries:
        _debug_log("[search_jobs] no valid queries after normalization")
        return []

    _debug_log("[search_jobs] normalized_queries=%s", normalized_queries)

    sem = asyncio.Semaphore(max_workers)

    async def _run_one(query: str) -> list[dict[str, str]]:
        async with sem:
            return await asyncio.to_thread(
                _search_all_sources_for_query,
                query,
                timeout,
                api_url,
                user_agent,
                location,
                job_type,
                adzuna_api_url,
                adzuna_app_id,
                adzuna_api_key,
                adzuna_country,
                adzuna_results_per_page,
                jooble_api_url,
                jooble_api_key,
                jooble_location,
                jooble_results_per_page,
            )

    tasks = [_run_one(query) for query in normalized_queries]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: list[dict[str, str]] = []
    seen = set()

    for result in raw_results:
        if isinstance(result, Exception):
            _debug_log("[search_jobs] worker_error=%s", result)
            continue
        for job in result:
            key = (job.get("company", ""), job.get("title", ""), job.get("url", ""))
            if key not in seen:
                seen.add(key)
                merged.append(job)

    return merged


def search_jobs_multi(
    queries: list[str],
    timeout: int = 20,
    max_workers: int = 6,
    api_url: str = REMOTIVE_API,
    user_agent: str = "ai-job-hunter-cold-mailer/1.0 (+https://remotive.com)",
    max_requests: int = 4,
    location: str = "",
    job_type: str = "",
    adzuna_api_url: str = "https://api.adzuna.com/v1/api/jobs",
    adzuna_app_id: str = "",
    adzuna_api_key: str = "",
    adzuna_country: str = "in",
    adzuna_results_per_page: int = 20,
    jooble_api_url: str = "https://jooble.org/api",
    jooble_api_key: str = "",
    jooble_location: str = "India",
    jooble_results_per_page: int = 20,
) -> list[dict[str, str]]:
    """Search across multiple queries concurrently with async + threaded fallback."""
    normalized_queries = _normalize_queries(queries, max_requests)
    if not normalized_queries:
        _debug_log("[search_jobs_multi] no queries to send")
        return []

    _debug_log(
        "[search_jobs_multi] sending_queries=%s location=%r job_type=%r timeout=%s max_workers=%s",
        normalized_queries,
        location,
        job_type,
        timeout,
        max_workers,
    )

    try:
        return asyncio.run(
            search_jobs_async(
                normalized_queries,
                timeout=timeout,
                max_workers=max_workers,
                api_url=api_url,
                user_agent=user_agent,
                max_requests=max_requests,
                location=location,
                job_type=job_type,
                adzuna_api_url=adzuna_api_url,
                adzuna_app_id=adzuna_app_id,
                adzuna_api_key=adzuna_api_key,
                adzuna_country=adzuna_country,
                adzuna_results_per_page=adzuna_results_per_page,
                jooble_api_url=jooble_api_url,
                jooble_api_key=jooble_api_key,
                jooble_location=jooble_location,
                jooble_results_per_page=jooble_results_per_page,
            )
        )
    except RuntimeError:
        # Fallback for environments where an event loop is already running.
        _debug_log("[search_jobs_multi] using threaded fallback mode")
        merged: list[dict[str, str]] = []
        seen = set()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _search_all_sources_for_query,
                    query,
                    timeout,
                    api_url,
                    user_agent,
                    location,
                    job_type,
                    adzuna_api_url,
                    adzuna_app_id,
                    adzuna_api_key,
                    adzuna_country,
                    adzuna_results_per_page,
                    jooble_api_url,
                    jooble_api_key,
                    jooble_location,
                    jooble_results_per_page,
                )
                for query in normalized_queries
            ]
            for future in as_completed(futures):
                try:
                    results = future.result()
                except Exception:
                    continue
                for job in results:
                    key = (job.get("company", ""), job.get("title", ""), job.get("url", ""))
                    if key not in seen:
                        seen.add(key)
                        merged.append(job)
        return merged
