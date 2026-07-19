"""Runs the mail-merge send loop in a background thread so the Streamlit UI
stays responsive and Pause/Resume/Cancel actually work mid-campaign."""
import random
import time
from datetime import datetime

from csv_utils import first_name_of
from email_utils import build_values_from, fill_template, build_message, send_via_smtp
import quota


def run_campaign(contacts, profile, templates_pool, smtp_config,
                  delay_seconds, daily_limit, status, pause_event, cancel_event,
                  quota_path, history_path, rotate_randomly=False):
    """
    contacts: list of dicts — already filtered (sent_history skipped upstream).
    templates_pool: list of dicts, each with name/subject/body/resume_bytes/resume_filename.
    rotate_randomly: pick a random template per contact if True.
    status: shared dict mutated in-place to report progress to the UI thread.
    """
    status["total"] = len(contacts)
    status["pending"] = len(contacts)
    status["running"] = True

    for contact in contacts:
        if cancel_event.is_set():
            status["logs"].append(f"[{_now()}] Campaign cancelled by user.")
            break

        pause_event.wait()  # blocks while paused

        if cancel_event.is_set():
            status["logs"].append(f"[{_now()}] Campaign cancelled by user.")
            break

        remaining_today = quota.get_remaining_today(daily_limit, quota_path)
        if remaining_today <= 0:
            status["logs"].append(
                f"[{_now()}] Daily limit of {daily_limit} reached. "
                f"Stopping - resume tomorrow."
            )
            break

        chosen = (
            random.choice(templates_pool)
            if (rotate_randomly and len(templates_pool) > 1)
            else templates_pool[0]
        )

        first_name = first_name_of(contact.get("Name", ""))
        values = build_values_from(profile, contact, first_name)
        subject = fill_template(chosen["subject"], values)
        body = fill_template(chosen["body"], values)

        msg = build_message(
            from_addr=smtp_config["username"],
            from_name=profile.get("full_name", ""),
            to_addr=contact["Email"],
            reply_to=smtp_config.get("reply_to") or smtp_config["username"],
            subject=subject,
            body=body,
            resume_bytes=chosen.get("resume_bytes"),
            resume_filename=chosen.get("resume_filename"),
        )

        success, error = send_via_smtp(smtp_config, msg)

        record = {
            "Name": contact.get("Name", ""),
            "Company": contact.get("Company", ""),
            "Email": contact.get("Email", ""),
            "Template": chosen.get("name", ""),
            "Status": "Sent" if success else "Failed",
            "Error": "" if success else error,
            "Timestamp": _now(),
        }
        status["results"].append(record)

        if success:
            status["sent"] += 1
            quota.increment(quota_path)
            # Permanent history — this is what prevents re-sending tomorrow
            quota.append_sent(
                email=contact["Email"],
                name=contact.get("Name", ""),
                company=contact.get("Company", ""),
                template=chosen.get("name", ""),
                history_path=history_path,
            )
            status["logs"].append(
                f"[{_now()}] Sent → {contact['Email']} "
                f"({contact.get('Company', '')}) [{chosen.get('name', '')}]"
            )
        else:
            status["failed"] += 1
            status["logs"].append(f"[{_now()}] FAILED {contact['Email']}: {error}")

        status["pending"] = status["total"] - status["sent"] - status["failed"]

        if contact is not contacts[-1] and not cancel_event.is_set():
            time.sleep(delay_seconds)

    status["running"] = False


def _now():
    return datetime.now().strftime("%H:%M:%S")
