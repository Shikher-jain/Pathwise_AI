"""Job search across 4 APIs: Remotive, Adzuna, Jooble, TheMuse."""
import hashlib
import time
import requests

TIMEOUT = 12  # seconds per API call


# ─────────────────────────── REMOTIVE ─────────────────────────────────────────
def search_remotive(query: str, max_results: int = 25) -> list[dict]:
    """Free API, no key needed. Remote jobs only."""
    try:
        url = "https://remotive.com/api/remote-jobs"
        params = {"search": query, "limit": max_results}
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        results = []
        for j in jobs:
            salary = j.get("salary", "") or ""
            results.append({
                "job_id":     str(j.get("id", "")),
                "job_title":  j.get("title", ""),
                "company":    j.get("company_name", ""),
                "location":   j.get("candidate_required_location", "Remote"),
                "salary":     salary if salary.strip() else "-1",
                "source":     "Remotive",
                "url":        j.get("url", ""),
                "date_posted": j.get("publication_date", "")[:10],
            })
        return results
    except Exception as e:
        return [{"_error": f"Remotive: {e}"}]


# ─────────────────────────── ADZUNA ───────────────────────────────────────────
def search_adzuna(query: str, location: str, app_id: str, app_key: str,
                   country: str = "in", max_results: int = 25) -> list[dict]:
    """Adzuna API — requires app_id + app_key from developer.adzuna.com"""
    if not app_id or not app_key:
        return [{"_error": "Adzuna: app_id/app_key not configured in secrets.toml"}]
    try:
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": query,
            "where": location or "india",
            "results_per_page": max_results,
            "content-type": "application/json",
        }
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("results", [])
        results = []
        for j in jobs:
            sal_min = j.get("salary_min")
            sal_max = j.get("salary_max")
            if sal_min and sal_max:
                salary = f"{sal_min:.0f} - {sal_max:.0f}"
            elif sal_min:
                salary = f"{sal_min:.0f}"
            else:
                salary = "-1"
            results.append({
                "job_id":     j.get("id", ""),
                "job_title":  j.get("title", ""),
                "company":    j.get("company", {}).get("display_name", ""),
                "location":   j.get("location", {}).get("display_name", ""),
                "salary":     salary,
                "source":     "Adzuna",
                "url":        j.get("redirect_url", ""),
                "date_posted": j.get("created", "")[:10],
            })
        return results
    except Exception as e:
        return [{"_error": f"Adzuna: {e}"}]


# ─────────────────────────── JOOBLE ───────────────────────────────────────────
def search_jooble(query: str, location: str, api_key: str,
                   max_results: int = 25) -> list[dict]:
    """Jooble API — requires api_key from jooble.org/api/about"""
    if not api_key:
        return [{"_error": "Jooble: api_key not configured in secrets.toml"}]
    try:
        url = f"https://jooble.org/api/{api_key}"
        payload = {
            "keywords": query,
            "location": location or "India",
            "resultonpage": max_results,
        }
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
        results = []
        for j in jobs:
            salary = j.get("salary", "") or ""
            results.append({
                "job_id":     str(j.get("id", "")),
                "job_title":  j.get("title", ""),
                "company":    j.get("company", ""),
                "location":   j.get("location", ""),
                "salary":     salary.strip() if salary.strip() else "-1",
                "source":     "Jooble",
                "url":        j.get("link", ""),
                "date_posted": j.get("updated", "")[:10],
            })
        return results
    except Exception as e:
        return [{"_error": f"Jooble: {e}"}]


# ─────────────────────────── THE MUSE ─────────────────────────────────────────
def search_themuse(query: str, max_results: int = 25) -> list[dict]:
    """TheMuse API — free, no key needed."""
    try:
        url = "https://www.themuse.com/api/public/jobs"
        params = {"descending": "true", "page": 0}
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        jobs = r.json().get("results", [])
        query_lower = query.lower()
        results = []
        for j in jobs:
            title = j.get("name", "")
            # Filter by query relevance (TheMuse has no keyword search param)
            if not any(kw in title.lower() for kw in query_lower.split()):
                continue
            company = j.get("company", {}).get("name", "")
            locations = j.get("locations", [])
            loc = locations[0].get("name", "") if locations else ""
            results.append({
                "job_id":     str(j.get("id", "")),
                "job_title":  title,
                "company":    company,
                "location":   loc,
                "salary":     "-1",
                "source":     "TheMuse",
                "url":        j.get("refs", {}).get("landing_page", ""),
                "date_posted": j.get("publication_date", "")[:10],
            })
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        return [{"_error": f"TheMuse: {e}"}]


# ─────────────────────────── AGGREGATOR ───────────────────────────────────────
COLUMNS = ["job_id", "job_title", "company", "location",
           "salary", "source", "url", "date_posted"]


def search_all(query: str, location: str, secrets: dict,
               max_per_source: int = 25) -> tuple[list[dict], list[str]]:
    """
    Run all 4 APIs, merge, deduplicate, return (jobs, errors).
    Dedup key: normalized title + company string.
    """
    adzuna_cfg = secrets.get("adzuna", {})
    jooble_cfg = secrets.get("jooble", {})

    raw = []
    errors = []

    sources = [
        ("Remotive",  search_remotive(query, max_per_source)),
        ("Adzuna",    search_adzuna(query, location,
                                    adzuna_cfg.get("app_id", ""),
                                    adzuna_cfg.get("app_key", ""),
                                    max_results=max_per_source)),
        ("Jooble",    search_jooble(query, location,
                                    jooble_cfg.get("api_key", ""),
                                    max_results=max_per_source)),
        ("TheMuse",   search_themuse(query, max_per_source)),
    ]

    for source_name, results in sources:
        for item in results:
            if "_error" in item:
                errors.append(item["_error"])
            else:
                raw.append(item)

    # Deduplicate by (normalized title + company)
    seen = set()
    deduped = []
    for job in raw:
        key = _dedup_key(job["job_title"], job["company"])
        if key not in seen:
            seen.add(key)
            deduped.append({col: job.get(col, "") for col in COLUMNS})

    return deduped, errors


def _dedup_key(title: str, company: str) -> str:
    normalized = f"{title.lower().strip()}|{company.lower().strip()}"
    return hashlib.md5(normalized.encode()).hexdigest()
