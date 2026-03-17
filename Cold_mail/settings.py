from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st


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


def _get_setting(key: str, default: str = "") -> str:
    try:
        value = st.secrets.get(key)
        if value is not None:
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()



def load_settings() -> AppSettings:
    return AppSettings(
        smtp_host=_get_setting("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=_to_int(_get_setting("SMTP_PORT", "587"), default=587, min_value=1),
        smtp_user_default=_get_setting("EMAIL", ""),
        smtp_password_default=_get_setting("PASSWORD", ""),
        allow_signup=_to_bool(_get_setting("ALLOW_SIGNUP", "true"), default=True),
        daily_email_limit=_to_int(_get_setting("MAX_EMAILS_PER_DAY", "200"), default=200, min_value=1),
        hourly_email_limit=_to_int(_get_setting("MAX_EMAILS_PER_HOUR", "50"), default=50, min_value=1),
        send_delay_seconds=_to_int(_get_setting("EMAIL_DELAY_SECONDS", "5"), default=5, min_value=0),
        search_max_workers=_to_int(_get_setting("SEARCH_MAX_WORKERS", "6"), default=6, min_value=1),
        remotive_api_url=_get_setting("REMOTIVE_API_URL", "https://remotive.com/api/remote-jobs"),
        remotive_max_requests_per_run=_to_int(
            _get_setting("REMOTIVE_MAX_REQUESTS_PER_RUN", "4"),
            default=4,
            min_value=1,
        ),
        remotive_timeout_seconds=_to_int(
            _get_setting("REMOTIVE_TIMEOUT_SECONDS", "20"),
            default=20,
            min_value=1,
        ),
        remotive_user_agent=_get_setting(
            "REMOTIVE_USER_AGENT",
            "ai-job-hunter-cold-mailer/1.0 (+https://remotive.com)",
        ),
        adzuna_api_url=_get_setting(
            "ADZUNA_API_URL",
            "https://api.adzuna.com/v1/api/jobs",
        ),
        adzuna_app_id=_get_setting("ADZUNA_APP_ID", ""),
        adzuna_api_key=_get_setting("ADZUNA_API_KEY", ""),
        adzuna_country=_get_setting("ADZUNA_COUNTRY", "in").lower(),
        adzuna_results_per_page=_to_int(
            _get_setting("ADZUNA_RESULTS_PER_PAGE", "20"),
            default=20,
            min_value=1,
        ),
        jooble_api_url=_get_setting("JOOBLE_API_URL", "https://jooble.org/api"),
        jooble_api_key=_get_setting("JOOBLE_API_KEY", ""),
        jooble_location=_get_setting("JOOBLE_LOCATION", "India"),
        jooble_results_per_page=_to_int(
            _get_setting("JOOBLE_RESULTS_PER_PAGE", "20"),
            default=20,
            min_value=1,
        ),
        groq_api_key=_get_setting("GROQ_API_KEY", _get_setting("API_KEY", "")),
        groq_model=_get_setting("GROQ_MODEL", "llama-3.3-70b-versatile"),
        groq_api_url=_get_setting("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"),
        groq_timeout_seconds=_to_int(
            _get_setting("GROQ_TIMEOUT_SECONDS", "30"),
            default=30,
            min_value=1,
        ),
    )
