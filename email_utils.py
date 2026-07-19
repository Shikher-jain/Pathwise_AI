"""SMTP sending and MIME message construction."""
import smtplib
import mimetypes
from email.message import EmailMessage

PROVIDER_PRESETS = {
    "Gmail": {"host": "smtp.gmail.com", "port": 587},
    "Outlook": {"host": "smtp.office365.com", "port": 587},
    "Custom": {"host": "", "port": 587},
}

TOKEN_KEYS = [
    "First Name", "Full Name", "Company Name",
    "Internship Company", "Internship Role", "Industry/Domain",
    "Target Role", "Achievement1", "Achievement2", "Achievement3",
    "Phone", "LinkedIn", "GitHub", "Portfolio",
]

DEFAULT_TEMPLATE_SUBJECT = "Application for {{Target Role}}"

DEFAULT_TEMPLATE_BODY = """
Hi {{First Name}},

I'm a final-year CS student actively looking for {{Target Role}} opportunities at {{Company Name}}.

Quick snapshot:
- {{Achievement1}}
- {{Achievement2}}
- {{Achievement3}}

During my internship at {{Internship Company}}, I worked as {{Internship Role}} in {{Industry/Domain}}.

Resume attached - would appreciate you keeping me in mind for any relevant openings.

Best regards,
{{Full Name}}
Phone: {{Phone}}
LinkedIn: {{LinkedIn}}
GitHub: {{GitHub}}
Portfolio: {{Portfolio}}
"""

# Three ready-made template presets, short and resume-matched.
# "resume_key" tells the app which uploaded resume file to attach for that template.
TEMPLATE_PRESETS = {
"AI + Backend (Combined)": {
        "subject": "Application for AI/Backend Engineer Role",
        "resume_key": "ai",
        "body": """Hi {{First Name}},

Quick one — I'm Shikher, a CS graduate (June 2026) actively looking for AI/Backend Engineer roles at {{Company Name}}.

- Sahayak AI - multimodal RAG platform (FastAPI + LangChain + Qdrant)
- Pathwise AI - LLM job matching engine, +30% match relevance
- Rank 1040, TCS CodeVita Season 12 (top 0.2%, 537K+ participants)

At Novas Arc Consulting, I built NLP pipelines processing 10,000+ FAQ records and a semantic search system improving retrieval relevance by 20-30%. Earlier at Dynamix Networks, I deployed a real-time inference API for a production fake news detection system.

Resume attached - would be great to connect if there's a relevant opening, even a short call would help.

Best,
{{Full Name}}
{{Phone}} | {{LinkedIn}} | {{GitHub}} | {{Portfolio}}
""",
    },
"AI/ML & GenAI Heavy": {
        "subject": "Application for AI/ML Engineer Role",
        "resume_key": "ai",
        "body": """Hi {{First Name}},

Quick one — I'm Shikher, a CS graduate (June 2026) actively looking for AI/ML Engineer roles at {{Company Name}}.

- Sahayak AI - multimodal RAG platform (FastAPI + LangChain + Qdrant)
- Pathwise AI - LLM-based job matching engine, +30% match relevance
- Rank 1040, TCS CodeVita Season 12 (top 0.2%, 537K+ participants)

At Novas Arc Consulting, I built NLP pipelines processing 10,000+ FAQ records, multi-label text classifiers (intent, persona, domain), and semantic search improving retrieval relevance by 20-30%. Earlier at Dynamix Networks, I built ML pipelines for automated credibility scoring with real-time inference.

Resume attached - would be great to connect if there's a relevant opening, even a short call would help.

Best,
{{Full Name}}
{{Phone}} | {{LinkedIn}} | {{GitHub}} | {{Portfolio}}
""",
    },
"Backend Heavy": {
        "subject": "Application for Backend Engineer Role",
        "resume_key": "backend",
        "body": """Hi {{First Name}},

Quick one — I'm Shikher, a CS graduate (June 2026) actively looking for Backend Engineer roles at {{Company Name}}.

- Sahayak AI - FastAPI backend, 25+ REST endpoints, JWT auth, Docker
- DataVista - 12+ microservices, unified REST APIs, CI/CD deployment
- Rank 1040, TCS CodeVita Season 12 (top 0.2%, 537K+ participants)

At Novas Arc Consulting, I engineered backend data pipelines processing 10,000+ records with embedding-based feature extraction, reducing manual effort by 75-80%. Earlier at Dynamix Networks, I designed PostgreSQL schemas and deployed a real-time inference API for production use.

Resume attached - would be great to connect if there's a relevant opening, even a short call would help.

Best,
{{Full Name}}
{{Phone}} | {{LinkedIn}} | {{GitHub}} | {{Portfolio}}
""",
    },
}


def fill_template(template: str, values: dict) -> str:
    """Replace {{Token}} placeholders with values. Unfilled optional tokens become blank lines removed."""
    text = template
    for key in TOKEN_KEYS:
        token = "{{" + key + "}}"
        text = text.replace(token, values.get(key, "") or "")
    # Clean up lines that are now just a bare label with nothing after it (optional fields like GitHub/Portfolio)
    cleaned_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.endswith(":") and len(stripped) < 20:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def build_values_from(profile: dict, contact: dict, first_name: str) -> dict:
    return {
        "First Name": first_name,
        "Full Name": profile.get("full_name", ""),
        "Company Name": contact.get("Company", ""),
        "Internship Company": profile.get("internship_company", ""),
        "Internship Role": profile.get("internship_role", ""),
        "Industry/Domain": profile.get("industry", ""),
        "Target Role": profile.get("target_role", ""),
        "Achievement1": profile.get("achievement1", ""),
        "Achievement2": profile.get("achievement2", ""),
        "Achievement3": profile.get("achievement3", ""),
        "Phone": profile.get("phone", ""),
        "LinkedIn": profile.get("linkedin", ""),
        "GitHub": profile.get("github", ""),
        "Portfolio": profile.get("portfolio", ""),
    }


def build_message(from_addr, from_name, to_addr, reply_to, subject, body,
                   resume_bytes, resume_filename) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content(body)

    if resume_bytes and resume_filename:
        ctype, encoding = mimetypes.guess_type(resume_filename)
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(
            resume_bytes,
            maintype=maintype,
            subtype=subtype,
            filename=resume_filename,
        )
    return msg


def send_via_smtp(smtp_config: dict, msg: EmailMessage):
    """
    smtp_config keys: host, port, username, password, use_tls (bool)
    Returns (success: bool, error_message: str or None)
    """
    try:
        host = smtp_config["host"]
        port = int(smtp_config["port"])
        username = smtp_config["username"]
        password = smtp_config["password"]

        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if smtp_config.get("use_tls", True):
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.send_message(msg)
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Authentication failed: {e}"
    except smtplib.SMTPConnectError as e:
        return False, f"Could not connect to SMTP server: {e}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def test_connection(smtp_config: dict):
    """Just login, don't send anything."""
    try:
        host = smtp_config["host"]
        port = int(smtp_config["port"])
        username = smtp_config["username"]
        password = smtp_config["password"]

        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if smtp_config.get("use_tls", True):
                server.starttls()
                server.ehlo()
            server.login(username, password)
        return True, "Connection and login successful."
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Authentication failed: {e}"
    except Exception as e:
        return False, f"Failed: {e}"