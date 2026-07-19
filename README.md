# Cold Outreach Tool for Job-Seeking Freshers

A minimal, personal-use Streamlit app to send personalized cold emails (with
resume attached) to a list of recruiters from a CSV — one email at a time,
never CC/BCC.

## What this does
- CSV upload + validation (required cols: Name, Title, Company, Category, Email)
- Removes duplicates, flags invalid/missing rows before sending
- One-time profile form
- Resume upload (PDF/DOCX), auto-attached to every email
- Editable email template with `{{Token}}` personalization
- Live preview per recipient before sending
- SMTP send via Gmail / Outlook / custom server
- **Daily send cap** (default 20/day) that persists across restarts
- Configurable delay between sends (default 30s)
- Working Pause / Resume / Cancel mid-campaign (runs in a background thread)
- Live dashboard: sent / failed / pending / success rate / progress / ETA
- Downloadable CSV report (per-contact status + error reason)

## What this deliberately skips (and why)
AI-generated subject lines, campaign scheduling, follow-up sequences,
multiple templates, rich-text editor, dark mode, analytics dashboard —
none of these move the needle on actually getting interviews, and they're
real engineering time you could instead spend applying / networking / prepping.
Add them later only if you find you genuinely need them.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Gmail setup
Gmail blocks plain-password SMTP login. You need an **App Password**:
1. Turn on 2-Step Verification on your Google account.
2. Go to Google Account -> Security -> App passwords.
3. Generate one for "Mail", use that 16-character password in the app
   (not your normal Gmail password).

## Outlook setup
Similarly needs an App Password if 2FA is on, generated from
Microsoft Account -> Security -> Advanced security options.

## Important honesty notes
- **Credentials are never written to disk** - they live only in the
  Streamlit session's memory and disappear when you close the app.
  This is appropriate for personal local use; it is not a secrets vault.
- **20/day is a sane default.** Sending 50-100+/day from a personal Gmail
  account with a near-identical template is a strong spam-filter trigger
  and risks account flags. Don't raise the daily limit casually.
- **Response rates on cold recruiter emails are low** regardless of
  personalization quality - most HR/TA inboxes get flooded with these.
  Use this as one channel alongside direct applications, referrals, and
  networking, not as a replacement for them.
- The daily quota file (daily_quota.json) is local and per-machine -
  if you run this on a different machine, the count resets.

## CSV format
See sample_contacts.csv for the expected format. Required columns:
Name, Title, Company, Category, Email. S.No is ignored if present.

## Template tokens
{{First Name}}, {{Full Name}}, {{Company Name}},
{{Internship Company}}, {{Internship Role}}, {{Industry/Domain}},
{{Target Role}}, {{Achievement1}}, {{Achievement2}}, {{Achievement3}},
{{Phone}}, {{LinkedIn}}, {{GitHub}}, {{Portfolio}}
