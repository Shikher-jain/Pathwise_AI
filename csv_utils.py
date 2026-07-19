"""CSV handling: validate recruiter contact list."""
import pandas as pd
from email_validator import validate_email, EmailNotValidError

REQUIRED_COLUMNS = ["Name", "Title", "Company", "Category", "Email"]


def load_and_validate(file_obj):
    """
    Reads a CSV file-like object and returns:
        valid_df: DataFrame of clean, deduped, valid rows
        invalid_df: DataFrame of rejected rows with a Reason column
        summary: dict of counts
    """
    df = pd.read_csv(file_obj, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(missing_cols)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}"
        )

    df = df[REQUIRED_COLUMNS].copy()

    # Drop fully empty rows
    df = df.dropna(how="all")
    df = df[~(df.apply(lambda r: all((str(v).strip() == "" or pd.isna(v)) for v in r), axis=1))]

    invalid_rows = []
    valid_rows = []
    seen_emails = set()

    for _, row in df.iterrows():
        name = str(row["Name"]).strip() if pd.notna(row["Name"]) else ""
        title = str(row["Title"]).strip() if pd.notna(row["Title"]) else ""
        company = str(row["Company"]).strip() if pd.notna(row["Company"]) else ""
        category = str(row["Category"]).strip() if pd.notna(row["Category"]) else ""
        email_raw = str(row["Email"]).strip() if pd.notna(row["Email"]) else ""

        reasons = []
        if not name:
            reasons.append("Missing Name")
        if not company:
            reasons.append("Missing Company")
        if not email_raw:
            reasons.append("Missing Email")
        else:
            try:
                validate_email(email_raw, check_deliverability=False)
            except EmailNotValidError:
                reasons.append("Invalid email format")

        if not reasons and email_raw.lower() in seen_emails:
            reasons.append("Duplicate email (removed)")

        record = {
            "Name": name,
            "Title": title,
            "Company": company,
            "Category": category,
            "Email": email_raw,
        }

        if reasons:
            record["Reason"] = "; ".join(reasons)
            invalid_rows.append(record)
        else:
            seen_emails.add(email_raw.lower())
            valid_rows.append(record)

    valid_df = pd.DataFrame(valid_rows, columns=REQUIRED_COLUMNS)
    invalid_df = pd.DataFrame(invalid_rows, columns=REQUIRED_COLUMNS + ["Reason"])

    summary = {
        "total_rows": len(df),
        "valid": len(valid_df),
        "invalid": len(invalid_df),
    }
    return valid_df, invalid_df, summary


def first_name_of(full_name: str) -> str:
    full_name = (full_name or "").strip()
    if not full_name:
        return "there"
    return full_name.split()[0]
