import tempfile
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from auth import authenticate_user, register_user
from config import (
    DEFAULT_SKILLS,
    DEFAULT_HR_CSV_NAME,
    GENERATED_DIR,
    UPLOADS_DIR,
)
from db import create_campaign, init_db, log_resume_upload, replace_user_leads
from email_sender import send_bulk_emails
from job_search import build_query
from logging_config import setup_logging
from pipeline import run_resume_to_leads_pipeline
from settings import load_settings
from target_companies import get_target_companies
settings = load_settings()

setup_logging(Path(__file__).resolve().parent / "generated" / "logs")
logger = logging.getLogger(__name__)

sender_email = settings.smtp_user_default
smtp_password = settings.smtp_password_default
smtp_server = settings.smtp_host
smtp_port = settings.smtp_port
allow_signup = settings.allow_signup

db_init_error: str | None = None
try:
    init_db()
except Exception as exc:
    logger.exception("Database initialization failed")
    db_init_error = str(exc)

st.set_page_config(page_title="Pathwise AI", layout="wide")
st.title("Pathwise AI")

if db_init_error:
    st.error(f"Database initialization failed: {db_init_error}")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "hunter_run_status" not in st.session_state:
    st.session_state.hunter_run_status = "Idle"
if "hunter_run_detail" not in st.session_state:
    st.session_state.hunter_run_detail = "No run yet"
if "skill_parser_status" not in st.session_state:
    st.session_state.skill_parser_status = "Unknown"

if not st.session_state.authenticated:
    st.subheader("Account Access")
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submit = st.form_submit_button("Login")

        if login_submit:
            ok_login, user_id = authenticate_user(login_email, login_password)
            if ok_login:
                st.session_state.authenticated = True
                st.session_state.user_email = login_email.strip().lower()
                st.session_state.user_id = user_id
                logger.info("User logged in: %s", st.session_state.user_email)
                st.rerun()
            else:
                st.error("Invalid email or password")

    with signup_tab:
        if not allow_signup:
            st.info("New account registration is currently disabled.")
        else:
            with st.form("signup_form"):
                signup_email = st.text_input("Email", key="signup_email")
                signup_password = st.text_input("Password", type="password", key="signup_password")
                signup_confirm = st.text_input("Confirm Password", type="password", key="signup_confirm")
                signup_submit = st.form_submit_button("Create Account")

            if signup_submit:
                if signup_password != signup_confirm:
                    st.error("Password and confirm password do not match")
                else:
                    ok, message = register_user(signup_email, signup_password)
                    if ok:
                        logger.info("New user account registered: %s", signup_email.strip().lower())
                        st.success(f"{message}. Please login.")
                    else:
                        st.error(message)

    st.stop()

with st.sidebar:
    st.success(f"Logged in as {st.session_state.user_email}")
    st.markdown("### Job Hunter Status")
    st.write(f"State: {st.session_state.hunter_run_status}")
    st.caption(st.session_state.hunter_run_detail)
    st.markdown("### Skill Parser")
    st.caption(st.session_state.skill_parser_status)
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.user_email = ""
        st.session_state.user_id = None
        logger.info("User logged out")
        st.rerun()

tab_hunter, tab_sender = st.tabs(["AI Job Hunter", "Cold Email Sender"])

user_id = int(st.session_state.user_id)
user_generated_dir = GENERATED_DIR / f"user_{user_id}"
user_generated_dir.mkdir(parents=True, exist_ok=True)
generated_csv_path = user_generated_dir / DEFAULT_HR_CSV_NAME


def _safe_user_folder(email: str) -> str:
    return email.replace("@", "_at_").replace(".", "_").replace("/", "_").lower()

with tab_hunter:
    st.subheader("Resume -> Skills -> Jobs -> HR CSV")

    hunter_resume = st.file_uploader("Upload Resume (PDF)", type=["pdf"], key="hunter_resume")

    # --- New Filters ---
    location = st.text_input("Location (optional, e.g. USA, Europe, Worldwide)", value="India")
    job_type = st.selectbox(
        "Job Type",
        ["full_time", "internship", "part_time", "contract", "freelance", ""],
        index=0,
        help="Filter jobs by type. Default: Full Time."
    )
    experience_level = st.selectbox(
        "Experience Level",
        ["fresher", "intern", "junior", "mid", "senior", ""],
        index=0,
        help="Filter by experience keywords in job title/description. Default: Fresher."
    )
    # --- End Filters ---

    if not hunter_resume:
        st.info("Upload a resume to start generating a targeted HR outreach CSV.")
    else:
        from resume_parser import extract_text
        from skill_extractor import extract_skills, get_last_skill_extraction_status

        user_folder = _safe_user_folder(st.session_state.user_email)
        preview_resume_dir = UPLOADS_DIR / user_folder
        preview_resume_dir.mkdir(parents=True, exist_ok=True)
        preview_resume_path = preview_resume_dir / "resume.pdf"
        with open(preview_resume_path, "wb") as file_handle:
            file_handle.write(hunter_resume.getbuffer())

        resume_text = extract_text(str(preview_resume_path))
        skills = extract_skills(resume_text)
        skill_status = get_last_skill_extraction_status()

        st.write("Detected Skills:", skills if skills else "No explicit skill matches found.")
        st.caption(
            f"Skill parser status: {skill_status.get('message')} | "
            f"LLM configured: {skill_status.get('llm_configured')} | "
            f"LLM attempted: {skill_status.get('llm_attempted')} | "
            f"Fallback used: {skill_status.get('fallback_used')}"
        )
        st.session_state.skill_parser_status = (
            f"{skill_status.get('message')} | "
            f"LLM configured: {skill_status.get('llm_configured')} | "
            f"LLM attempted: {skill_status.get('llm_attempted')} | "
            f"Fallback used: {skill_status.get('fallback_used')}"
        )

        all_skills = sorted({item.strip().lower() for item in DEFAULT_SKILLS if item.strip()})

        add_all_skills = st.checkbox(
            "Add all known skills manually",
            value=False,
            help="Adds every configured skill from the skills database.",
        )

        detected_skills: list[str] = []
        seen_detected = set()
        for item in skills:
            normalized = item.strip().lower()
            if normalized and normalized not in seen_detected:
                detected_skills.append(normalized)
                seen_detected.add(normalized)

        manual_add_skills = st.multiselect(
            "Add skills (from all known skills)",
            options=all_skills,
            default=all_skills if add_all_skills else [],
            help="Dropdown contains all known skills. Select any to add manually.",
            key="manual_add_skills_dropdown",
        )

        combined_skills: list[str] = []
        seen_combined = set()
        for item in detected_skills + manual_add_skills:
            if item and item not in seen_combined:
                combined_skills.append(item)
                seen_combined.add(item)

        manual_remove_skills = st.multiselect(
            "Remove skills (from current selected list)",
            options=combined_skills,
            default=[],
            help="Dropdown only shows skills already present in the current list.",
            key="manual_remove_skills_dropdown",
        )

        remove_set = set(manual_remove_skills)

        final_skills: list[str] = []
        for item in combined_skills:
            if item not in remove_set:
                final_skills.append(item)

        st.write("Final Skills Used:", final_skills if final_skills else "No skills selected")

        default_query = build_query(
            final_skills,
            job_type=job_type,
            experience_level=experience_level,
            location=location,
        )

        current_query_signature = "||".join(
            [
                ",".join(final_skills),
                job_type,
                experience_level,
                location.strip().lower(),
            ]
        )
        if (
            "search_query_signature" not in st.session_state
            or st.session_state.search_query_signature != current_query_signature
        ):
            st.session_state.search_query_input = default_query
            st.session_state.search_query_signature = current_query_signature

        if st.button("Rewrite Search Query from Final Skills", key="rewrite_query"):
            st.session_state.search_query_input = default_query

        query = st.text_input("Search Query", key="search_query_input")

        company_options = get_target_companies()
        selected_companies = st.multiselect(
            "Target companies (optional)",
            options=company_options,
            default=[],
            help="Select companies to bias job search queries toward your preferred employers.",
        )

        top_n = st.slider("Top jobs to keep", min_value=5, max_value=100, value=20, step=5)
        search_workers = st.slider(
            "Search concurrency (faster with higher value)",
            min_value=1,
            max_value=12,
            value=settings.search_max_workers,
            step=1,
        )

        if st.button("Find Matching Jobs", key="find_jobs"):
            st.session_state.hunter_run_status = "Running"
            st.session_state.hunter_run_detail = "Searching and ranking jobs..."
            with st.spinner("Searching and ranking jobs..."):
                try:
                    result = run_resume_to_leads_pipeline(
                        user_email=st.session_state.user_email,
                        user_id=user_id,
                        resume_bytes=hunter_resume.getbuffer(),
                        top_n=top_n,
                        query_override=query,
                        skills_override=final_skills,
                        target_companies=selected_companies,
                        max_workers=search_workers,
                        max_requests=settings.remotive_max_requests_per_run,
                        location=location,
                        job_type=job_type,
                        experience_level=experience_level,
                    )
                    log_resume_upload(user_id, str(result.resume_path))
                    df = pd.read_csv(result.csv_path)
                    replace_user_leads(user_id, df.to_dict(orient="records"))

                    st.success(f"Generated {len(df)} leads at {result.csv_path}")
                    st.session_state.hunter_run_status = "Success"
                    st.session_state.hunter_run_detail = f"Generated {len(df)} leads"
                    logger.info("Generated %s leads for user_id=%s", len(df), user_id)
                    # Show all possible results with confidence level as last column
                    df_jobs = pd.DataFrame(result.ranked_jobs)
                    if 'score' in df_jobs.columns:
                        df_jobs['confidence'] = df_jobs['score']
                    else:
                        df_jobs['confidence'] = None
                    st.dataframe(df_jobs, use_container_width=True)

                    mail_ready_df = df[
                        df["mail"].fillna("").astype(str).str.strip() != ""
                    ].copy()
                    mail_ready_csv_path = result.csv_path.with_name("hr_mail_ready.csv")
                    mail_ready_df.to_csv(mail_ready_csv_path, index=False)

                    st.download_button(
                        "Download Generated HR CSV",
                        data=df.to_csv(index=False),
                        file_name="hr.csv",
                        mime="text/csv",
                        key="download_generated_csv",
                    )

                    st.download_button(
                        "Download Mail-Ready CSV",
                        data=mail_ready_df.to_csv(index=False),
                        file_name="hr_mail_ready.csv",
                        mime="text/csv",
                        key="download_mail_ready_csv",
                    )
                    st.caption(
                        f"Mail-ready rows: {len(mail_ready_df)} | Saved at {mail_ready_csv_path}"
                    )
                except Exception as exc:
                    st.error(f"Job hunter pipeline failed: {exc}")
                    st.session_state.hunter_run_status = "Error"
                    st.session_state.hunter_run_detail = str(exc)

with tab_sender:
    st.subheader("Send Personalized Emails")

    st.header("SMTP Credentials")
    smtp_user_input = st.text_input("SMTP Email", value=sender_email)
    smtp_pass_input = st.text_input("SMTP Password", value=smtp_password, type="password")
    smtp_host_input = st.text_input("SMTP Host", value=smtp_server)
    smtp_port_input = st.number_input("SMTP Port", min_value=1, max_value=65535, value=smtp_port, step=1)

    st.header("Email Template")
    subject_template = st.text_input("Subject Template", "Quick question about {company}")

    body_template = st.text_area(
        "Email Body Template",
        """
Hi {name},

I came across {company} while exploring teams building AI and backend systems.

I am a final-year Computer Science student experienced in Python, FastAPI, and ML systems. Recently I built a multimodal RAG assistant using PyTorch and vector databases.

If your team is open to interns or junior engineers, I would love to connect.

Best regards,
Shikher Jain
""",
        height=250,
    )

    st.header("AI Email Writer")
    use_llm_writer = st.checkbox(
        "Use Groq to write cold mail as per JD",
        value=True,
        help="Uses JD/description columns from contacts CSV. Falls back to template if unavailable.",
    )
    llm_profile_summary = st.text_area(
        "Candidate Profile Summary",
        value=(
            "Final-year CS student with hands-on Python, FastAPI, ML systems, and applied LLM/RAG work. "
            "Strong backend fundamentals and production mindset."
        ),
        height=90,
    )

    st.header("Social Media Links")
    github = st.text_input("GitHub", "https://github.com/Shikher-jain")
    linkedin = st.text_input("LinkedIn", "https://www.linkedin.com/in/shikher-jain-0bb8a8259")
    portfolio = st.text_input("Portfolio", "https://shikher-jain-09.streamlit.app/")

    st.header("Resume Attachment")
    sender_resume = st.file_uploader("Upload Resume (PDF)", type=["pdf"], key="sender_resume")
    sender_resume_path = None

    if sender_resume:
        user_folder = _safe_user_folder(st.session_state.user_email)
        resume_dir = UPLOADS_DIR / user_folder
        resume_dir.mkdir(parents=True, exist_ok=True)
        sender_resume_path = resume_dir / sender_resume.name
        with open(sender_resume_path, "wb") as file_handle:
            file_handle.write(sender_resume.getbuffer())
        st.success("Resume uploaded for sender")

    st.header("Contacts Source")
    st.write(
        "Expected columns: `company` and `email` or `mail`. "
        "For AI writer, include one of: `jd`, `description`, `job_description`, `role`, `title`."
    )

    contacts_file = st.file_uploader("Upload contacts.csv", type=["csv"], key="sender_contacts")
    use_generated = st.checkbox(
        "Use generated AI Job Hunter CSV if available",
        value=generated_csv_path.exists(),
    )

    if st.button("Send Emails", key="send_emails"):
        if not smtp_user_input or not smtp_pass_input or not smtp_host_input:
            st.error("Provide SMTP Email, SMTP Password, and SMTP Host.")
        else:
            contacts_path: str | None = None
            temp_contacts_path: str | None = None

            if contacts_file is not None:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
                    temp_file.write(contacts_file.getbuffer())
                    contacts_path = temp_file.name
                    temp_contacts_path = temp_file.name
            elif use_generated and generated_csv_path.exists():
                contacts_path = str(generated_csv_path)

            if contacts_path is None:
                st.error("Upload contacts.csv or generate hr.csv from AI Job Hunter first.")
            else:
                sent_count, errors = send_bulk_emails(
                    contacts_csv_path=contacts_path,
                    sender_email=smtp_user_input,
                    password=smtp_pass_input,
                    smtp_server=smtp_host_input,
                    smtp_port=int(smtp_port_input),
                    subject_template=subject_template,
                    body_template=body_template,
                    github=github,
                    linkedin=linkedin,
                    portfolio=portfolio,
                    resume_path=str(sender_resume_path) if sender_resume_path else None,
                    campaign_id=create_campaign(
                        user_id=user_id,
                        campaign_name=f"Campaign - {st.session_state.user_email}",
                        template=body_template,
                    ),
                    actor_user_id=user_id,
                    send_delay_seconds=settings.send_delay_seconds,
                    daily_limit=settings.daily_email_limit,
                    hourly_limit=settings.hourly_email_limit,
                    use_llm_writer=use_llm_writer,
                    llm_profile_summary=llm_profile_summary,
                )

                st.success(f"{sent_count} emails sent")
                logger.info("Email campaign completed: sent=%s user_id=%s", sent_count, user_id)
                for error in errors:
                    st.error(error)

                if temp_contacts_path and Path(temp_contacts_path).exists():
                    Path(temp_contacts_path).unlink(missing_ok=True)