# Pathwise AI

## Overview
This repo has 2 parts:

1. `Cold_mail.py/`: Main app (resume -> keywords -> jobs -> final CSV, plus optional email sender).
2. `automatic/` + `main.py`: Selenium company-career search utility.

## Project Structure
```text
Automatic/
	main.py
	requirements.txt
	automatic/
		careers_search.py
		companies.py
		resume_scrape_pipeline.py
	Cold_mail.py/
		app.py
		pipeline.py
		job_search.py
		lead_builder.py
		resume_parser.py
		skill_extractor.py
		generated/
			user_<id_or_email>/hr.csv
	tests/
```

## Final Output
Primary final CSV is generated at:

- `Cold_mail.py/generated/user_.../hr.csv`

CSV columns are intentionally minimal:

- `job_id`
- `role`
- `company`
- `mail` (blank if unavailable)

## Setup
```powershell
cd C:\shikher_jain\Automatic
pip install -r requirements.txt
```

Set `DATABASE_URL` in root `.env` before running Streamlit.

## Run App (Recommended)
```powershell
cd C:\shikher_jain\Automatic\Cold_mail.py
streamlit run app.py
```

## Run Resume Pipeline (CLI)
```powershell
cd C:\shikher_jain\Automatic
$env:AUTOMATIC_RESUME_PATH="C:\path\to\resume.pdf"
$env:AUTOMATIC_RESUME_SKILL_LIMIT="3"
python main.py
```

Optional envs:

- `AUTOMATIC_MAX_WORKERS`
- `AUTOMATIC_COMPANY_LIMIT`
- `AUTOMATIC_WAIT_SECONDS`
- `AUTOMATIC_PAUSE_SECONDS`
- `AUTOMATIC_MAX_ATTEMPTS`

## Test
```powershell
cd C:\shikher_jain\Automatic
python -m unittest discover -s tests -p "test_*.py"
```
