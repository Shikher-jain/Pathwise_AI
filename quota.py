"""Daily send-quota tracking + permanent sent-history tracking."""
import csv
import json
import os
from datetime import date, datetime

QUOTA_FILE_DEFAULT = "daily_quota.json"
HISTORY_FILE_DEFAULT = "sent_history.csv"
HISTORY_COLUMNS = ["Email", "Name", "Company", "Template", "Date", "Time"]


# ─────────────────────────────── DAILY QUOTA ──────────────────────────────────

def _load(path):
    if not os.path.exists(path):
        return {"date": str(date.today()), "count": 0}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"date": str(date.today()), "count": 0}
    if data.get("date") != str(date.today()):
        return {"date": str(date.today()), "count": 0}
    return data


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def get_sent_today(path=QUOTA_FILE_DEFAULT) -> int:
    return _load(path)["count"]


def get_remaining_today(daily_limit: int, path=QUOTA_FILE_DEFAULT) -> int:
    return max(0, daily_limit - get_sent_today(path))


def increment(path=QUOTA_FILE_DEFAULT, by: int = 1):
    data = _load(path)
    data["count"] += by
    _save(path, data)
    return data["count"]


# ─────────────────────────────── SENT HISTORY ─────────────────────────────────

def load_sent_emails(history_path=HISTORY_FILE_DEFAULT) -> set:
    """Return a set of already-sent email addresses (lowercase) from history file."""
    if not os.path.exists(history_path):
        return set()
    sent = set()
    try:
        with open(history_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = row.get("Email", "").strip().lower()
                if email:
                    sent.add(email)
    except OSError:
        pass
    return sent


def append_sent(email, name, company, template,
                history_path=HISTORY_FILE_DEFAULT):
    """Append one successful send record to the permanent history CSV."""
    file_exists = os.path.exists(history_path)
    now = datetime.now()
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "Email": email,
            "Name": name,
            "Company": company,
            "Template": template,
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S"),
        })


def get_history_stats(history_path=HISTORY_FILE_DEFAULT) -> dict:
    """Return total sent count, unique companies, and today's count from history."""
    if not os.path.exists(history_path):
        return {"total": 0, "today": 0, "companies": 0}
    total, today_count, companies = 0, 0, set()
    today_str = str(date.today())
    try:
        with open(history_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                companies.add(row.get("Company", "").strip())
                if row.get("Date", "") == today_str:
                    today_count += 1
    except OSError:
        pass
    return {"total": total, "today": today_count, "companies": len(companies)}


def reset_history(history_path=HISTORY_FILE_DEFAULT):
    """Delete the history file entirely (UI exposes this as a manual reset button)."""
    if os.path.exists(history_path):
        os.remove(history_path)
