from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pathlib import Path
from automatic.resume_scrape_pipeline import extract_resume_text, extract_resume_skills, build_resume_search_terms
import shutil
import os

app = FastAPI(title="Resume Skills Extractor API")

UPLOAD_DIR = Path("uploads/resumes/api")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/`extract-skills`/")
async def extract_skills_from_resume(file: UploadFile = File(...)):
    # Save uploaded file
    file_location = UPLOAD_DIR / file.filename
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        resume_text = extract_resume_text(str(file_location))
        skills = extract_resume_skills(resume_text)
        search_terms = build_resume_search_terms(skills)
        return JSONResponse({
            "skills": skills,
            "search_terms": search_terms
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        # Optionally, remove the uploaded file after processing
        if os.path.exists(file_location):
            os.remove(file_location)

@app.get("/")
def root():
    return {"message": "Resume Skills Extractor API is running."}
