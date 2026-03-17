from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st
from psycopg import connect
from psycopg.rows import dict_row


_DB_SECRET_SECTIONS = ("database", "db", "secrets", "app", "settings")


def get_database_url() -> str:
    db_url = ""
    try:
        for candidate in ("DATABASE_URL", "database_url", "url"):
            value = st.secrets.get(candidate)
            if value:
                db_url = str(value).strip()
                break
    except Exception:
        db_url = ""

    if not db_url:
        try:
            for section_name in _DB_SECRET_SECTIONS:
                section = st.secrets.get(section_name)
                if section is None or not hasattr(section, "get"):
                    continue
                for candidate in ("DATABASE_URL", "database_url", "url"):
                    value = section.get(candidate)
                    if value:
                        db_url = str(value).strip()
                        break
                if db_url:
                    break
        except Exception:
            db_url = ""

    if not db_url:
        db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing in Streamlit secrets/environment")
    return db_url


def get_conn():
    return connect(get_database_url(), row_factory=dict_row)


def init_db() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS resumes (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        file_path TEXT NOT NULL,
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT,
        email TEXT,
        company TEXT NOT NULL,
        position TEXT,
        job_id TEXT,
        custom_line TEXT,
        priority TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        campaign_name TEXT NOT NULL,
        template TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS email_logs (
        id SERIAL PRIMARY KEY,
        campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        receiver_email TEXT NOT NULL,
        company TEXT,
        status TEXT NOT NULL,
        sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def create_user(email: str, password_hash: str, name: str | None = None, role: str = "user") -> tuple[bool, str, int | None]:
    sql = """
    INSERT INTO users (name, email, password_hash, role)
    VALUES (%s, %s, %s, %s)
    RETURNING id
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (name, email, password_hash, role))
                row = cur.fetchone()
            conn.commit()
        return True, "Account created", int(row["id"]) if row else None
    except Exception as exc:
        message = str(exc).lower()
        if "duplicate" in message or "unique" in message:
            return False, "Account already exists for this email", None
        return False, f"User creation failed: {exc}", None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    sql = "SELECT id, email, password_hash, role FROM users WHERE email = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
    return dict(row) if row else None


def log_resume_upload(user_id: int, file_path: str) -> None:
    sql = "INSERT INTO resumes (user_id, file_path) VALUES (%s, %s)"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, file_path))
        conn.commit()


def replace_user_leads(user_id: int, rows: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM leads WHERE user_id = %s", (user_id,))
            insert_sql = """
            INSERT INTO leads (user_id, name, email, company, position, job_id, custom_line, priority)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            for row in rows:
                cur.execute(
                    insert_sql,
                    (
                        user_id,
                        row.get("name") or "",
                        row.get("email") or "",
                        row.get("company") or "",
                        row.get("position") or "Recruiter",
                        row.get("job_id") or "",
                        row.get("custom_line") or "",
                        row.get("priority") or "medium",
                    ),
                )
        conn.commit()


def create_campaign(user_id: int, campaign_name: str, template: str) -> int:
    sql = """
    INSERT INTO campaigns (user_id, campaign_name, template)
    VALUES (%s, %s, %s)
    RETURNING id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, campaign_name, template))
            row = cur.fetchone()
        conn.commit()
    return int(row["id"])


def log_email_event(user_id: int, receiver_email: str, company: str, status: str, campaign_id: int | None = None) -> None:
    sql = """
    INSERT INTO email_logs (campaign_id, user_id, receiver_email, company, status)
    VALUES (%s, %s, %s, %s, %s)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (campaign_id, user_id, receiver_email, company, status))
        conn.commit()


def get_email_send_counts(user_id: int) -> tuple[int, int]:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    hour_start = datetime.now(timezone.utc) - timedelta(hours=1)

    sql_day = """
    SELECT COUNT(*) AS cnt
    FROM email_logs
    WHERE user_id = %s
      AND status = 'sent'
      AND sent_at >= %s
    """

    sql_hour = """
    SELECT COUNT(*) AS cnt
    FROM email_logs
    WHERE user_id = %s
      AND status = 'sent'
      AND sent_at >= %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_day, (user_id, day_start))
            day_row = cur.fetchone()
            cur.execute(sql_hour, (user_id, hour_start))
            hour_row = cur.fetchone()

    return int(day_row["cnt"]), int(hour_row["cnt"])
