from __future__ import annotations

import csv
import json
import os
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from db import get_email_send_counts, log_email_event
from settings import load_settings


_SETTINGS = load_settings()


def _generate_llm_cold_mail(
    name: str,
    company: str,
    jd_text: str,
    profile_summary: str,
    github: str,
    linkedin: str,
    portfolio: str,
) -> str:
    if not _SETTINGS.groq_api_key:
        raise ValueError("LLM credentials are not configured")

    system_prompt = (
        "You are an expert career assistant. Write concise, professional cold outreach emails "
        "for job applications tailored to the provided job description."
    )
    user_prompt = (
        f"Candidate name: {name}\n"
        f"Target company: {company}\n"
        f"Candidate profile summary: {profile_summary}\n"
        f"Job description (or role context): {jd_text}\n"
        f"Candidate links:\nGitHub: {github}\nLinkedIn: {linkedin}\nPortfolio: {portfolio}\n\n"
        "Write one final email body only (no subject line), 120-180 words, "
        "specific to the JD, professional and friendly, with a clear CTA."
    )

    payload = {
        "model": _SETTINGS.groq_model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    response = requests.post(
        _SETTINGS.groq_api_url,
        headers={
            "Authorization": f"Bearer {_SETTINGS.groq_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=_SETTINGS.groq_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Empty LLM response")

    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("text"):
            cleaned = cleaned[4:].strip()
    return cleaned


def send_bulk_emails(
    contacts_csv_path: str,
    sender_email: str,
    password: str,
    smtp_server: str,
    smtp_port: int,
    subject_template: str,
    body_template: str,
    github: str,
    linkedin: str,
    portfolio: str,
    resume_path: str | None = None,
    campaign_id: int | None = None,
    actor_user_id: int | None = None,
    send_delay_seconds: int = 5,
    daily_limit: int = 200,
    hourly_limit: int = 50,
    use_llm_writer: bool = False,
    llm_profile_summary: str = "",
) -> tuple[int, list[str]]:
    errors: list[str] = []
    sent_count = 0

    if actor_user_id is None:
        return 0, ["Missing authenticated user id"]

    today_sent, hour_sent = get_email_send_counts(actor_user_id)
    if today_sent >= daily_limit:
        return 0, [f"Daily limit reached ({daily_limit}). Try again tomorrow."]
    if hour_sent >= hourly_limit:
        return 0, [f"Hourly limit reached ({hourly_limit}). Try again later."]

    with open(contacts_csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, password)

        try:
            for row in reader:
                try:
                    if sent_count + today_sent >= daily_limit:
                        errors.append(f"Stopped: daily limit reached ({daily_limit}).")
                        break
                    if sent_count + hour_sent >= hourly_limit:
                        errors.append(f"Stopped: hourly limit reached ({hourly_limit}).")
                        break

                    name = row.get("name", "there") or "there"
                    receiver_email = (row.get("email") or row.get("mail") or "").strip()
                    if not receiver_email:
                        raise ValueError("Missing receiver email/mail")
                    company = row.get("company", "your company")
                    jd_text = (
                        row.get("jd")
                        or row.get("description")
                        or row.get("job_description")
                        or row.get("role")
                        or row.get("title")
                        or ""
                    )

                    subject = subject_template.format(company=company)
                    if use_llm_writer and jd_text:
                        try:
                            body = _generate_llm_cold_mail(
                                name=name,
                                company=company,
                                jd_text=jd_text,
                                profile_summary=llm_profile_summary,
                                github=github,
                                linkedin=linkedin,
                                portfolio=portfolio,
                            )
                        except Exception as llm_exc:
                            errors.append(
                                f"LLM fallback for {receiver_email}: {llm_exc}"
                            )
                            body = body_template.format(name=name, company=company)
                            body += (
                                f"\n\nGitHub: {github}\nLinkedIn: {linkedin}\nPortfolio: {portfolio}\n"
                            )
                    else:
                        body = body_template.format(name=name, company=company)
                        body += (
                            f"\n\nGitHub: {github}\nLinkedIn: {linkedin}\nPortfolio: {portfolio}\n"
                        )

                    msg = MIMEMultipart()
                    msg["From"] = sender_email
                    msg["To"] = receiver_email
                    msg["Subject"] = subject
                    msg.attach(MIMEText(body, "plain"))

                    if resume_path and os.path.exists(resume_path):
                        with open(resume_path, "rb") as attachment:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(attachment.read())

                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={os.path.basename(resume_path)}",
                        )
                        msg.attach(part)

                    server.sendmail(sender_email, receiver_email, msg.as_string())
                    sent_count += 1
                    log_email_event(
                        user_id=actor_user_id,
                        receiver_email=receiver_email,
                        company=company,
                        status="sent",
                        campaign_id=campaign_id,
                    )

                    time.sleep(max(0, send_delay_seconds))
                except Exception as exc:
                    errors.append(f"Failed for {row}: {exc}")
                    log_email_event(
                        user_id=actor_user_id,
                        receiver_email=row.get("email", ""),
                        company=row.get("company", ""),
                        status=f"failed:{exc}",
                        campaign_id=campaign_id,
                    )
        finally:
            server.quit()

    return sent_count, errors
