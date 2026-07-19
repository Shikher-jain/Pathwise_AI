"""Pathwise AI — Job Search & Aggregation Tool
Run with: streamlit run app.py
"""
import io
import os
from datetime import datetime
import threading

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from core.resume_parser import parse_resume
from core.skill_extractor import extract_skills, extract_keywords, build_search_query
from core.job_search import search_all, COLUMNS

import csv_utils
import email_utils
import quota
from campaign_runner import run_campaign

st.set_page_config(page_title="Pathwise AI", page_icon="🎯", layout="wide")

os.makedirs("generated", exist_ok=True)

# ─────────────────────── session state defaults ───────────────────────────────
defaults = {
    "resume_text": "",
    "extracted_skills": [],
    "manual_skills": "",
    "search_results": [],
    "search_errors": [],
    "last_query": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────── load secrets ─────────────────────────────────────────
def _load_secrets() -> dict:
    try:
        return {
            "adzuna": dict(st.secrets.get("adzuna", {})),
            "jooble": dict(st.secrets.get("jooble", {})),
        }
    except Exception:
        return {"adzuna": {}, "jooble": {}}

secrets = _load_secrets()

# ─────────────────────── UI ───────────────────────────────────────────────────
st.title("Pathwise AI — Job Search Engine")
st.caption("Resume → Skills → Jobs from 4 APIs (Remotive, Adzuna, Jooble, TheMuse) → CSV")

tab1, tab2, tab3, tab4, tab5= st.tabs(
    ["1 Resume & Skills", "2 Job Preferences", "3 Search Results", "4 Export CSV","5 COLDMAIL Outreach"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Resume Upload or Manual Skills
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Step 1 — Tell us about your skills")

    input_mode = st.radio(
        "How do you want to enter your skills?",
        ["📄 Upload Resume (auto-extract)", "✍️ Enter skills manually"],
        horizontal=True,
    )

    if input_mode.startswith("📄"):
        resume_file = st.file_uploader("Upload your resume", type=["pdf", "docx"])
        if resume_file is not None:
            with st.spinner("Parsing resume..."):
                try:
                    text = parse_resume(resume_file.read(), resume_file.name)
                    st.session_state.resume_text = text
                    skills = extract_skills(text)
                    st.session_state.extracted_skills = skills
                    st.success(f"Resume parsed — {len(skills)} skills found.")
                except Exception as e:
                    st.error(str(e))

        if st.session_state.extracted_skills:
            st.markdown("**Extracted skills** (uncheck any you want to remove):")
            kept = []
            cols = st.columns(3)
            for i, skill in enumerate(st.session_state.extracted_skills):
                col = cols[i % 3]
                if col.checkbox(skill, value=True, key=f"skill_{skill}"):
                    kept.append(skill)
            st.session_state.extracted_skills = kept
            st.caption(f"{len(kept)} skills selected for job search.")

    else:
        st.session_state.manual_skills = st.text_area(
            "Enter your skills (comma-separated)",
            value=st.session_state.manual_skills,
            placeholder="python, fastapi, machine learning, qdrant, docker, postgresql",
            height=100,
        )
        if st.session_state.manual_skills.strip():
            parsed = [s.strip().lower() for s in st.session_state.manual_skills.split(",") if s.strip()]
            st.session_state.extracted_skills = parsed
            st.caption(f"{len(parsed)} skills entered.")

    if st.session_state.extracted_skills:
        st.divider()
        st.markdown("**Skills going into job search:**")
        st.write(", ".join(st.session_state.extracted_skills))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Job Preferences
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Step 2 — What kind of job are you looking for?")

    col1, col2 = st.columns(2)
    with col1:
        role = st.text_input(
            "Target Role *",
            placeholder="e.g. AI Engineer, Backend Developer, ML Engineer",
            help="Most important field — drives the search query."
        )
        location = st.text_input(
            "Preferred Location",
            value="India",
            placeholder="e.g. Bangalore, Mumbai, Remote, India"
        )
        experience = st.selectbox(
            "Experience Level",
            ["Fresher / Entry Level", "1-2 years", "2-5 years", "5+ years"],
        )
    with col2:
        department = st.text_input(
            "Department / Domain",
            placeholder="e.g. AI/ML, Backend, Data Science, Full Stack"
        )
        job_type = st.multiselect(
            "Job Type",
            ["Full-time", "Part-time", "Remote", "Internship", "Contract"],
            default=["Full-time"],
        )
        max_results = st.slider(
            "Max results per source", min_value=5, max_value=50, value=20,
            help="Each of the 4 APIs will return up to this many results."
        )

    # Build and show the search query
    if st.session_state.extracted_skills or role:
        skills_for_query = st.session_state.extracted_skills[:5]
        query_auto = build_search_query(skills_for_query, role)
        st.divider()
        st.markdown("**Search query that will be sent to all APIs:**")
        custom_query = st.text_input(
            "Query (auto-generated, edit if needed)",
            value=query_auto,
            help="This exact string is sent to all 4 job APIs."
        )
    else:
        custom_query = ""
        st.info("Fill in your skills in Tab 1 and Target Role above to generate a search query.")

    st.session_state["search_params"] = {
        "role": role,
        "location": location,
        "experience": experience,
        "department": department,
        "job_type": job_type,
        "max_results": max_results,
        "query": custom_query,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Search & Results
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Step 3 — Search Jobs")

    params = st.session_state.get("search_params", {})
    query = params.get("query", "").strip()
    location = params.get("location", "India")
    max_results = params.get("max_results", 20)

    if not query:
        st.info("Complete Tab 1 (skills) and Tab 2 (role/preferences) first.")
    else:
        st.markdown(f"**Query:** `{query}` | **Location:** `{location}` | **Max per source:** `{max_results}`")

        if st.button("🔍 Search All Job Portals", type="primary"):
            with st.spinner("Searching Remotive, Adzuna, Jooble, TheMuse..."):
                jobs, errors = search_all(
                    query=query,
                    location=location,
                    secrets=secrets,
                    max_per_source=max_results,
                )
                st.session_state.search_results = jobs
                st.session_state.search_errors = errors
                st.session_state.last_query = query

        if st.session_state.search_errors:
            with st.expander(f"⚠️ {len(st.session_state.search_errors)} API warning(s)"):
                for err in st.session_state.search_errors:
                    st.warning(err)

        if st.session_state.search_results:
            jobs = st.session_state.search_results
            df = pd.DataFrame(jobs, columns=COLUMNS)

            # Source breakdown
            source_counts = df["source"].value_counts()
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Jobs", len(df))
            m2.metric("Remotive", source_counts.get("Remotive", 0))
            m3.metric("Adzuna", source_counts.get("Adzuna", 0))
            m4.metric("Jooble", source_counts.get("Jooble", 0))
            m5.metric("TheMuse", source_counts.get("TheMuse", 0))

            # Filters
            st.divider()
            fc1, fc2 = st.columns(2)
            with fc1:
                source_filter = st.multiselect(
                    "Filter by source",
                    options=df["source"].unique().tolist(),
                    default=df["source"].unique().tolist(),
                )
            with fc2:
                salary_only = st.checkbox("Show only jobs with salary info", value=False)

            filtered = df[df["source"].isin(source_filter)]
            if salary_only:
                filtered = filtered[filtered["salary"] != "-1"]

            st.dataframe(
                filtered,
                width='stretch'   ,
                height=400,
                column_config={
                    "url": st.column_config.LinkColumn("URL"),
                }
            )
            st.caption(f"Showing {len(filtered)} of {len(df)} jobs.")

        elif st.session_state.last_query:
            st.warning("No results found. Try a broader query or different role keywords.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Export CSV
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Step 4 — Export Results")

    if not st.session_state.search_results:
        st.info("Run a search in Tab 3 first.")
    else:
        df = pd.DataFrame(st.session_state.search_results, columns=COLUMNS)
        params = st.session_state.get("search_params", {})

        st.markdown(f"**{len(df)} jobs ready to export**")
        st.dataframe(df, width='stretch', height=300)

        st.divider()
        st.markdown("**Download options**")

        c1, c2 = st.columns(2)

        # Full results CSV
        with c1:
            st.markdown("**Full results** — all columns")
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            fname = f"pathwise_jobs_{timestamp}.csv"
            st.download_button(
                "⬇ Download Full CSV",
                data=buf.getvalue(),
                file_name=fname,
                mime="text/csv",
                type="primary",
            )

        # Coldmail-compatible CSV
        with c2:
            st.markdown("**Coldmail Outreach CSV** — for use with `coldmail_outreach` tool")
            st.caption(
                "Exports company names + job roles for you to find recruiter emails "
                "and feed into the coldmail_outreach campaign tool."
            )
            coldmail_df = pd.DataFrame({
                "Name": [""] * len(df),
                "Title": df["job_title"],
                "Company": df["company"],
                "Category": df["source"],
                "Email": [""] * len(df),
            })
            buf2 = io.StringIO()
            coldmail_df.to_csv(buf2, index=False)
            st.download_button(
                "⬇ Download Coldmail CSV",
                data=buf2.getvalue(),
                file_name=f"coldmail_contacts_{timestamp}.csv",
                mime="text/csv",
            )
            st.caption(
                "⚠️ Email column is blank — fill recruiter emails manually (LinkedIn/Hunter.io) "
                "before uploading to coldmail_outreach."
            )

        # Auto-save to generated/ folder
        save_path = f"generated/pathwise_jobs_{timestamp}.csv"
        df.to_csv(save_path, index=False)
        st.success(f"Auto-saved to `{save_path}`")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Coldmail Outreach
# ══════════════════════════════════════════════════════════════════════════════
with tab5:

    TEMPLATE_NAMES = list(email_utils.TEMPLATE_PRESETS.keys())


    # ---------------------------------------------------------------- secrets loader
    def _load_secrets():
        """Read st.secrets once and return (profile_dict, smtp_dict).
        Falls back to empty dicts if secrets.toml is missing or incomplete."""
        profile, smtp = {}, {}
        try:
            s = st.secrets
            if "profile" in s:
                p = s["profile"]
                profile = {
                    "full_name":          p.get("full_name", ""),
                    "target_role":        p.get("target", ""),
                    "industry":           p.get("industry", ""),
                    "internship_role":    p.get("internship_role", ""),
                    "linkedin":           p.get("linkedin", ""),
                    "github":             p.get("github", ""),
                    "portfolio":          p.get("portfolio", ""),
                }
            if "smtp" in s:
                sm = s["smtp"]
                smtp = {
                    "host":     sm.get("host", "smtp.gmail.com"),
                    "port":     int(sm.get("port", 587)),
                    "username": sm.get("user_email", sm.get("username", "")),
                    "password": sm.get("app_password", ""),
                    "reply_to": "",
                    "use_tls":  True,
                }
        except Exception:
            pass
        return profile, smtp

    _secrets_profile, _secrets_smtp = _load_secrets()

    # ---------------------------------------------------------------- session state defaults
    defaults = {
        "profile": _secrets_profile,   # pre-filled from secrets.toml on first load
        "resume_ai_bytes": None, "resume_ai_filename": None,
        "resume_backend_bytes": None, "resume_backend_filename": None,
        "smtp_config": _secrets_smtp,  # pre-filled from secrets.toml on first load
        "valid_contacts": None,
        "invalid_contacts": None,
        "templates": {
            name: {"subject": preset["subject"], "body": preset["body"], "resume_key": preset["resume_key"]}
            for name, preset in email_utils.TEMPLATE_PRESETS.items()
        },
        "selected_emails": set(),
        "campaign_status": {
            "running": False, "sent": 0, "failed": 0, "pending": 0, "total": 0,
            "logs": [], "results": [],
        },
        "pause_event": None,
        "cancel_event": None,
        "campaign_thread": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.pause_event is None:
        st.session_state.pause_event = threading.Event()
        st.session_state.pause_event.set()  # not paused
    if st.session_state.cancel_event is None:
        st.session_state.cancel_event = threading.Event()

    QUOTA_PATH = "daily_quota.json"
    HISTORY_PATH = "sent_history.csv"


    def resume_for(resume_key):
        if resume_key == "backend":
            return st.session_state.resume_backend_bytes, st.session_state.resume_backend_filename
        return st.session_state.resume_ai_bytes, st.session_state.resume_ai_filename


    st.title("📧 Cold Outreach Tool — for Job-Seeking Freshers")
    st.caption(
        "Personal use tool. Sends one-by-one (never CC/BCC). "
        "Response rates on cold recruiter emails are low even when personalized well — "
        "use this alongside applications and networking, not instead of them."
    )

    tab1, tab2, tab3, tab4 = st.tabs(
        ["1 Setup", "2 Contacts (CSV)", "3 Templates & Preview", "4 Send & Dashboard"]
    )

    # =========================================================== TAB 1: SETUP
    with tab1:
        st.subheader("Your profile (filled once, reused for every email)")
        if _secrets_profile:
            st.success("✅ Profile fields pre-filled from secrets.toml — edit anything you want to change.")
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name", value=st.session_state.profile.get("full_name", ""))
            status_choice = st.selectbox("Current Status", ["Student", "Fresher"],
                                        index=["Student", "Fresher"].index(st.session_state.profile.get("status", "Fresher")))
            internship_company = st.text_input("Internship Company", value=st.session_state.profile.get("internship_company", "Dynamix Networks"))
            internship_role = st.text_input(
                "Internship Role", value=st.session_state.profile.get("internship_role", ""),
                help="Your designation/title during the internship, e.g. 'Backend Developer Intern' or 'Data Science Intern'."
            )
            industry = st.text_input(
                "Industry / Domain", value=st.session_state.profile.get("industry", ""),
                help="The field/domain you worked in, e.g. 'AI/ML' or 'Backend Systems'."
            )
            target_role = st.text_input(
                "Target Role", value=st.session_state.profile.get("target_role", ""),
                help="Used only by the generic fallback template. Each of the 3 templates in Tab 3 already has its own role baked into the subject/body."
            )
        with col2:
            phone = st.text_input("Phone Number", value=st.session_state.profile.get("phone", "+917452017544"))
            linkedin = st.text_input("LinkedIn Profile URL", value=st.session_state.profile.get("linkedin", ""))
            github = st.text_input("GitHub (optional)", value=st.session_state.profile.get("github", ""))
            portfolio = st.text_input("Portfolio Website (optional)", value=st.session_state.profile.get("portfolio", ""))
            st.caption(
                "'Internship Duration' and per-template Achievements are deliberately not separate "
                "fields here. The 3 templates in Tab 3 already have short, resume-matched achievement "
                "bullets baked straight into the body so the email stays short — edit them there directly "
                "if you want different wording."
            )

        st.session_state.profile = {
            "full_name": full_name, "status": status_choice,
            "internship_company": internship_company, "internship_role": internship_role,
            "industry": industry, "target_role": target_role,
            "phone": phone, "linkedin": linkedin, "github": github, "portfolio": portfolio,
        }

        st.divider()
        st.subheader("Resumes")
        st.caption(
            "Upload both. 'AI + Backend (Combined)' and 'AI/ML & GenAI Heavy' templates attach your AI resume; "
            "'Backend Heavy' attaches your Backend resume."
        )
        rcol1, rcol2 = st.columns(2)
        with rcol1:
            ai_resume_file = st.file_uploader("AI / GenAI Resume (PDF or DOCX)", type=["pdf", "docx"], key="ai_resume_uploader")
            if ai_resume_file is not None:
                st.session_state.resume_ai_bytes = ai_resume_file.read()
                st.session_state.resume_ai_filename = ai_resume_file.name
                st.success(f"Loaded: {ai_resume_file.name}")
            elif st.session_state.resume_ai_filename:
                st.info(f"Using: {st.session_state.resume_ai_filename}")
        with rcol2:
            backend_resume_file = st.file_uploader("Backend Resume (PDF or DOCX)", type=["pdf", "docx"], key="backend_resume_uploader")
            if backend_resume_file is not None:
                st.session_state.resume_backend_bytes = backend_resume_file.read()
                st.session_state.resume_backend_filename = backend_resume_file.name
                st.success(f"Loaded: {backend_resume_file.name}")
            elif st.session_state.resume_backend_filename:
                st.info(f"Using: {st.session_state.resume_backend_filename}")


        st.divider()
        st.subheader("SMTP Configuration")
        st.caption(
            "Credentials are kept only in this browser session's memory — never written to disk. "
            "For Gmail/Outlook you need an **App Password** (not your normal login password) "
            "since both block plain password SMTP login for security."
        )

        _smtp_loaded = bool(st.session_state.smtp_config.get("password"))
        if _smtp_loaded:
            st.success("✅ SMTP credentials loaded from secrets.toml — password pre-filled.")

        provider = st.selectbox("Provider", list(email_utils.PROVIDER_PRESETS.keys()))
        preset = email_utils.PROVIDER_PRESETS[provider]
        c1, c2 = st.columns(2)
        with c1:
            smtp_host = st.text_input(
                "SMTP Host",
                value=st.session_state.smtp_config.get("host") or preset["host"]
            )
            smtp_username = st.text_input(
                "Email / Username",
                value=st.session_state.smtp_config.get("username", "")
            )
            reply_to = st.text_input(
                "Reply-To (optional)", value=st.session_state.smtp_config.get("reply_to", ""),
                help="Only fill this if replies should land in a DIFFERENT inbox than the one you're sending from. "
                    "Leave blank and replies go to your sending address — that's the normal case."
            )
        with c2:
            smtp_port = st.number_input(
                "SMTP Port",
                value=int(st.session_state.smtp_config.get("port") or preset["port"])
            )
            smtp_password = st.text_input(
                "App Password",
                type="password",
                value=st.session_state.smtp_config.get("password", ""),
                help="Pre-filled from secrets.toml if present. You can still override it here."
            )
            use_tls = st.checkbox("Use TLS (STARTTLS)", value=True)

        st.session_state.smtp_config = {
            "host": smtp_host, "port": smtp_port, "username": smtp_username,
            "password": smtp_password or st.session_state.smtp_config.get("password", ""),
            "reply_to": reply_to, "use_tls": use_tls,
        }

        colA, colB = st.columns(2)
        with colA:
            if st.button("🔌 Test SMTP Connection"):
                ok, msg = email_utils.test_connection(st.session_state.smtp_config)
                (st.success if ok else st.error)(msg)
        with colB:
            test_to = st.text_input("Send test email to:", placeholder="you@example.com")
            if st.button("📨 Send Test Email") and test_to:
                r_bytes, r_name = resume_for("ai")
                msg = email_utils.build_message(
                    from_addr=st.session_state.smtp_config.get("username", ""),
                    from_name=st.session_state.profile.get("full_name", ""),
                    to_addr=test_to,
                    reply_to=st.session_state.smtp_config.get("reply_to"),
                    subject="Test email from Cold Outreach Tool",
                    body="This is a test email to confirm your SMTP setup works correctly.",
                    resume_bytes=r_bytes,
                    resume_filename=r_name,
                )
                ok, err = email_utils.send_via_smtp(st.session_state.smtp_config, msg)
                (st.success("Test email sent!") if ok else st.error(f"Failed: {err}"))

    # =========================================================== TAB 2: CONTACTS
    with tab2:
        st.subheader("Upload recruiter contact list")
        st.caption(
            "Required columns: Name, Title, Company, Category, Email. "
            "Note: 'Title' is the **recruiter's own designation** (e.g. 'Head HR'), not a job opening's role — "
            "the CSV has no column that tells you whether a company is hiring for AI or Backend, "
            "which is exactly why random template rotation (Tab 4) makes sense here."
        )
        csv_file = st.file_uploader("Upload CSV", type=["csv"])
        if csv_file is not None:
            try:
                valid_df, invalid_df, summary = csv_utils.load_and_validate(csv_file)
                st.session_state.valid_contacts = valid_df
                st.session_state.invalid_contacts = invalid_df
                st.session_state.selected_emails = set(valid_df["Email"].tolist())
                st.success(
                    f"Loaded {summary['total_rows']} rows → "
                    f"{summary['valid']} valid, {summary['invalid']} rejected (invalid/duplicate/missing)."
                )
            except ValueError as e:
                st.error(str(e))

        if st.session_state.valid_contacts is not None and len(st.session_state.valid_contacts) > 0:
            st.markdown("**✅ Valid contacts**")
            st.dataframe(st.session_state.valid_contacts, width="stretch", height=250)

        if st.session_state.invalid_contacts is not None and len(st.session_state.invalid_contacts) > 0:
            with st.expander(f"⚠️ {len(st.session_state.invalid_contacts)} rejected rows (click to view reasons)"):
                st.dataframe(st.session_state.invalid_contacts, width="stretch")

    # =========================================================== TAB 3: TEMPLATES & PREVIEW
    with tab3:
        st.subheader("Email templates (3 ready-made, all editable)")
        st.caption("Use {{Token}} placeholders. Available: " + ", ".join("{{" + k + "}}" for k in email_utils.TOKEN_KEYS))

        chosen_template_name = st.selectbox("Edit template", TEMPLATE_NAMES, key="template_editor_select")
        t = st.session_state.templates[chosen_template_name]
        new_subject = st.text_input("Subject", value=t["subject"], key=f"subj_{chosen_template_name}")
        new_body = st.text_area("Body", value=t["body"], height=320, key=f"body_{chosen_template_name}")
        new_resume_key = st.radio(
            "Resume to attach for this template", ["ai", "backend"],
            index=0 if t["resume_key"] == "ai" else 1,
            format_func=lambda k: "AI / GenAI Resume" if k == "ai" else "Backend Resume",
            horizontal=True, key=f"reskey_{chosen_template_name}",
        )
        st.session_state.templates[chosen_template_name] = {
            "subject": new_subject, "body": new_body, "resume_key": new_resume_key,
        }
        word_count = len(new_body.split())
        (st.caption if word_count <= 130 else st.warning)(f"Body word count: {word_count} {'(good, scan-friendly)' if word_count <= 130 else '(getting long for a cold email)'}")

        st.divider()
        st.subheader("Preview")
        if st.session_state.valid_contacts is None or len(st.session_state.valid_contacts) == 0:
            st.info("Upload a contact CSV in Tab 2 first to preview personalized emails.")
        else:
            contacts_df = st.session_state.valid_contacts
            names = (contacts_df["Name"] + "  —  " + contacts_df["Company"]).tolist()
            idx = st.selectbox("Preview recipient", range(len(names)), format_func=lambda i: names[i])
            preview_template_name = st.selectbox("Preview using template", TEMPLATE_NAMES, key="preview_template_select")
            contact = contacts_df.iloc[idx].to_dict()
            first_name = csv_utils.first_name_of(contact.get("Name", ""))
            values = email_utils.build_values_from(st.session_state.profile, contact, first_name)
            pt = st.session_state.templates[preview_template_name]
            subject_preview = email_utils.fill_template(pt["subject"], values)
            body_preview = email_utils.fill_template(pt["body"], values)

            st.markdown(f"**To:** {contact['Email']}  \n**Company:** {contact['Company']}  \n**Subject:** {subject_preview}")
            st.text_area("Body preview", value=body_preview, height=300, disabled=True, key="body_preview_area")
            r_bytes, r_name = resume_for(pt["resume_key"])
            if r_name:
                st.caption(f"📎 Attached: {r_name}")
            else:
                st.warning(f"No '{pt['resume_key']}' resume uploaded yet in Tab 1 — this email would go without an attachment.")

    # =========================================================== TAB 4: SEND & DASHBOARD
    with tab4:
        st.subheader("Campaign settings")

        if st.session_state.valid_contacts is None or len(st.session_state.valid_contacts) == 0:
            st.info("Upload contacts in Tab 2 first.")
        elif not st.session_state.smtp_config.get("password"):
            st.warning("Set up and test your SMTP connection in Tab 1 first.")
        else:
            contacts_df = st.session_state.valid_contacts

            # ── History stats banner ──────────────────────────────────────────────
            stats = quota.get_history_stats(HISTORY_PATH)
            sent_emails = quota.load_sent_emails(HISTORY_PATH)

            hs1, hs2, hs3 = st.columns(3)
            hs1.metric("Total sent (all time)", stats["total"])
            hs2.metric("Sent today (history)", stats["today"])
            hs3.metric("Unique companies reached", stats["companies"])

            # Filter out already-sent contacts from CSV
            all_contacts = contacts_df.to_dict("records")
            unsent_contacts = [
                c for c in all_contacts
                if c["Email"].strip().lower() not in sent_emails
            ]
            already_sent_count = len(all_contacts) - len(unsent_contacts)

            if already_sent_count > 0:
                st.info(
                    f"**{already_sent_count} contacts skipped** — already emailed in a previous run. "
                    f"**{len(unsent_contacts)} remaining** out of {len(all_contacts)} in CSV."
                )
            if len(unsent_contacts) == 0:
                st.success("All contacts in this CSV have already been emailed! Upload a new CSV or reset history below.")

            st.divider()

            # ── Template mode ─────────────────────────────────────────────────────
            st.markdown("**Which template(s) to send**")
            rotate_mode = st.radio(
                "Mode",
                ["Random rotate across all 3 templates", "Use one fixed template"],
                horizontal=True,
            )
            rotate_randomly = rotate_mode.startswith("Random")
            if not rotate_randomly:
                fixed_template_name = st.selectbox("Fixed template to use for everyone", TEMPLATE_NAMES, key="fixed_template_select")
            else:
                st.caption("Each recruiter gets a randomly picked template (Combined / AI-GenAI / Backend) with the matching resume attached. The campaign report logs which template each contact received.")

            st.divider()

            # ── Pacing & limits ───────────────────────────────────────────────────
            st.markdown("**Pacing & limits**")
            col1, col2, col3 = st.columns(3)
            with col1:
                daily_limit = st.number_input(
                    "Max emails PER DAY", min_value=1, max_value=200, value=20,
                    help="Hard cap per calendar day. Resets at midnight automatically."
                )
            with col2:
                delay_seconds = st.slider(
                    "Delay BETWEEN each email (seconds)", min_value=15, max_value=120, value=30,
                )
            with col3:
                remaining_today = quota.get_remaining_today(daily_limit, QUOTA_PATH)
                st.metric("Remaining quota today", remaining_today)

            # ── Batch size ────────────────────────────────────────────────────────
            send_mode = st.radio("Send to", ["All unsent contacts", "Selected contacts only"], horizontal=True)
            if send_mode == "Selected contacts only":
                chosen_emails = st.multiselect(
                    "Choose recipients",
                    options=[c["Email"] for c in unsent_contacts],
                    default=[c["Email"] for c in unsent_contacts],
                )
                candidate_contacts = [c for c in unsent_contacts if c["Email"] in chosen_emails]
            else:
                candidate_contacts = unsent_contacts

            max_this_run = min(len(candidate_contacts), remaining_today) if remaining_today > 0 else 0
            batch_size = st.number_input(
                "How many to send THIS RUN", min_value=0, max_value=max(max_this_run, 0),
                value=max_this_run,
                help="Capped at today's remaining quota and available unsent contacts."
            )
            target_contacts = candidate_contacts[:batch_size]
            st.caption(
                f"**{len(target_contacts)}** will be sent now — "
                f"{len(candidate_contacts)} unsent candidates, "
                f"{remaining_today} quota remaining today."
            )

            # ── Campaign controls ─────────────────────────────────────────────────
            status = st.session_state.campaign_status

            b1, b2, b3, b4 = st.columns(4)
            with b1:
                start_disabled = status["running"] or len(target_contacts) == 0
                if st.button("▶️ Start Campaign", disabled=start_disabled, type="primary"):
                    if rotate_randomly:
                        pool = []
                        for name in TEMPLATE_NAMES:
                            t = st.session_state.templates[name]
                            r_bytes, r_name = resume_for(t["resume_key"])
                            pool.append({"name": name, "subject": t["subject"], "body": t["body"],
                                        "resume_bytes": r_bytes, "resume_filename": r_name})
                    else:
                        t = st.session_state.templates[fixed_template_name]
                        r_bytes, r_name = resume_for(t["resume_key"])
                        pool = [{"name": fixed_template_name, "subject": t["subject"], "body": t["body"],
                                "resume_bytes": r_bytes, "resume_filename": r_name}]

                    status.update({"running": True, "sent": 0, "failed": 0,
                                "pending": len(target_contacts), "total": len(target_contacts),
                                "logs": [], "results": []})
                    st.session_state.pause_event.set()
                    st.session_state.cancel_event.clear()
                    thread = threading.Thread(
                        target=run_campaign,
                        args=(target_contacts, st.session_state.profile, pool,
                            st.session_state.smtp_config, delay_seconds, daily_limit,
                            status, st.session_state.pause_event, st.session_state.cancel_event,
                            QUOTA_PATH, HISTORY_PATH, rotate_randomly),
                        daemon=True,
                    )
                    st.session_state.campaign_thread = thread
                    thread.start()
                    st.rerun()
            with b2:
                if st.button("⏸️ Pause", disabled=not status["running"]):
                    st.session_state.pause_event.clear()
            with b3:
                if st.button("⏵️ Resume", disabled=not status["running"]):
                    st.session_state.pause_event.set()
            with b4:
                if st.button("⏹️ Cancel", disabled=not status["running"]):
                    st.session_state.cancel_event.set()
                    st.session_state.pause_event.set()

            st.divider()

            # ── Live dashboard ────────────────────────────────────────────────────
            st.subheader("Dashboard")

            if status["running"]:
                st_autorefresh(interval=1500, key="campaign_autorefresh")

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total queued", status["total"])
            m2.metric("Sent", status["sent"])
            m3.metric("Failed", status["failed"])
            m4.metric("Pending", status["pending"])
            success_rate = (status["sent"] / status["total"] * 100) if status["total"] else 0
            m5.metric("Success rate", f"{success_rate:.0f}%")

            if status["total"]:
                progress = (status["sent"] + status["failed"]) / status["total"]
                st.progress(min(progress, 1.0))
                if status["running"]:
                    remaining_count = status["total"] - status["sent"] - status["failed"]
                    est_seconds = remaining_count * delay_seconds
                    st.caption(f"Estimated time remaining: ~{est_seconds // 60} min {est_seconds % 60} sec")

            with st.expander("📜 Live log", expanded=status["running"]):
                for line in status["logs"][-100:]:
                    st.text(line)

            if status["results"]:
                report_df = pd.DataFrame(status["results"])
                st.markdown("**Campaign report (this run)**")
                st.dataframe(report_df, width="stretch", height=250)
                csv_buf = io.StringIO()
                report_df.to_csv(csv_buf, index=False)
                st.download_button(
                    "⬇️ Download this run's report CSV",
                    data=csv_buf.getvalue(),
                    file_name="campaign_report.csv",
                    mime="text/csv",
                )

            # ── Full history view + reset ─────────────────────────────────────────
            st.divider()
            st.subheader("Sent history (all time)")
            if os.path.exists(HISTORY_PATH):
                history_df = pd.read_csv(HISTORY_PATH)
                st.dataframe(history_df, width="stretch", height=250)
                hist_buf = io.StringIO()
                history_df.to_csv(hist_buf, index=False)
                st.download_button(
                    "⬇️ Download full history CSV",
                    data=hist_buf.getvalue(),
                    file_name="sent_history.csv",
                    mime="text/csv",
                )
                st.divider()
                st.markdown("**Reset history**")
                st.caption(
                    "This deletes sent_history.csv permanently. "
                    "All contacts will appear as unsent again — they WILL be emailed again on your next run."
                )
                confirm_reset = st.checkbox("Yes, I understand — delete all history")
                if st.button("🗑️ Reset sent history", disabled=not confirm_reset):
                    quota.reset_history(HISTORY_PATH)
                    st.success("History deleted. All contacts are now unsent again.")
                    st.rerun()
            else:
                st.caption("No history yet — send your first campaign to see records here.")    
