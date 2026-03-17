from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
    """Runtime configuration loaded from environment variables."""

    smtp_host: str
    smtp_port: int
    smtp_user_default: str
    smtp_password_default: str
    allow_signup: bool
    daily_email_limit: int
    hourly_email_limit: int
    send_delay_seconds: int
    search_max_workers: int
    remotive_api_url: str
    remotive_max_requests_per_run: int
    remotive_timeout_seconds: int
    remotive_user_agent: str
    adzuna_api_url: str
    adzuna_app_id: str
    adzuna_api_key: str
    adzuna_country: str
    adzuna_results_per_page: int
    jooble_api_url: str
    jooble_api_key: str
    jooble_location: str
    jooble_results_per_page: int
    groq_api_key: str
    groq_model: str
    groq_api_url: str
    groq_timeout_seconds: int



def _to_bool(value: str, default: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default



def _to_int(value: str, default: int, min_value: int = 1) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed >= min_value else default



def load_settings() -> AppSettings:
    return AppSettings(
        smtp_host=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=_to_int(os.getenv("SMTP_PORT", "587"), default=587, min_value=1),
        smtp_user_default=os.getenv("EMAIL", ""),
        smtp_password_default=os.getenv("PASSWORD", ""),
        allow_signup=_to_bool(os.getenv("ALLOW_SIGNUP", "true"), default=True),
        daily_email_limit=_to_int(os.getenv("MAX_EMAILS_PER_DAY", "200"), default=200, min_value=1),
        hourly_email_limit=_to_int(os.getenv("MAX_EMAILS_PER_HOUR", "50"), default=50, min_value=1),
        send_delay_seconds=_to_int(os.getenv("EMAIL_DELAY_SECONDS", "5"), default=5, min_value=0),
        search_max_workers=_to_int(os.getenv("SEARCH_MAX_WORKERS", "6"), default=6, min_value=1),
        remotive_api_url=os.getenv("REMOTIVE_API_URL", "https://remotive.com/api/remote-jobs").strip(),
        remotive_max_requests_per_run=_to_int(
            os.getenv("REMOTIVE_MAX_REQUESTS_PER_RUN", "4"),
            default=4,
            min_value=1,
        ),
        remotive_timeout_seconds=_to_int(
            os.getenv("REMOTIVE_TIMEOUT_SECONDS", "20"),
            default=20,
            min_value=1,
        ),
        remotive_user_agent=os.getenv(
            "REMOTIVE_USER_AGENT",
            "ai-job-hunter-cold-mailer/1.0 (+https://remotive.com)",
        ).strip(),
        adzuna_api_url=os.getenv(
            "ADZUNA_API_URL",
            "https://api.adzuna.com/v1/api/jobs",
        ).strip(),
        adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
        adzuna_api_key=os.getenv("ADZUNA_API_KEY", "").strip(),
        adzuna_country=os.getenv("ADZUNA_COUNTRY", "in").strip().lower(),
        adzuna_results_per_page=_to_int(
            os.getenv("ADZUNA_RESULTS_PER_PAGE", "20"),
            default=20,
            min_value=1,
        ),
        jooble_api_url=os.getenv("JOOBLE_API_URL", "https://jooble.org/api").strip(),
        jooble_api_key=os.getenv("JOOBLE_API_KEY", "").strip(),
        jooble_location=os.getenv("JOOBLE_LOCATION", "India").strip(),
        jooble_results_per_page=_to_int(
            os.getenv("JOOBLE_RESULTS_PER_PAGE", "20"),
            default=20,
            min_value=1,
        ),
        groq_api_key=(os.getenv("GROQ_API_KEY") or os.getenv("API_KEY") or "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        groq_api_url=os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip(),
        groq_timeout_seconds=_to_int(
            os.getenv("GROQ_TIMEOUT_SECONDS", "30"),
            default=30,
            min_value=1,
        ),
    )
