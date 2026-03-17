from __future__ import annotations

import json
import re
from typing import Iterable

import requests

from config import DEFAULT_SKILLS
from settings import load_settings


_SETTINGS = load_settings()
_LAST_SKILL_STATUS = {
    "llm_configured": False,
    "llm_attempted": False,
    "llm_success": False,
    "fallback_used": True,
    "message": "Rule-based parsing active",
}


def _is_skill_present_in_resume(skill: str, resume_text: str) -> bool:
    """Return True only when the exact skill phrase appears as a standalone term."""
    candidate = skill.strip().lower()
    if not candidate:
        return False
    escaped = re.escape(candidate)
    escaped = escaped.replace(r"\ ", r"\s+")
    pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return re.search(pattern, resume_text.lower()) is not None


def get_last_skill_extraction_status() -> dict[str, object]:
    return dict(_LAST_SKILL_STATUS)


def _strip_code_fence(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\n?", "", cleaned)
        cleaned = cleaned.rstrip("`").strip()
    return cleaned


def _extract_skills_with_groq(resume_text: str, skills_source: list[str]) -> list[str]:
    if not _SETTINGS.groq_api_key:
        return []

    prompt = (
        "Extract technical and professional skills from the resume text. "
        "Return ONLY a JSON array of lowercase skill strings. "
        "Prefer exact skills from this allowed set when possible: "
        f"{', '.join(skills_source[:300])}."
    )

    payload = {
        "model": _SETTINGS.groq_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You extract resume skills and output strict JSON."},
            {"role": "user", "content": prompt + "\n\nResume:\n" + resume_text[:12000]},
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
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not isinstance(content, str) or not content.strip():
        return []

    cleaned = _strip_code_fence(content)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        return []

    allowed = {item.lower(): item for item in skills_source}
    result: list[str] = []
    seen = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        candidate = item.strip().lower()
        if not candidate:
            continue
        mapped = allowed.get(candidate, candidate)
        if mapped not in seen:
            result.append(mapped)
            seen.add(mapped)
    return result


def extract_skills(resume_text: str, skills_db: Iterable[str] | None = None) -> list[str]:
    """Extract only resume-present skills using strict matching plus guarded LLM suggestions."""
    skills_source = list(skills_db) if skills_db else DEFAULT_SKILLS

    # LLM-first extraction when Groq API key is configured.
    _LAST_SKILL_STATUS["llm_configured"] = bool(_SETTINGS.groq_api_key)
    _LAST_SKILL_STATUS["llm_attempted"] = False
    _LAST_SKILL_STATUS["llm_success"] = False
    _LAST_SKILL_STATUS["fallback_used"] = True
    _LAST_SKILL_STATUS["message"] = "Rule-based parsing active"

    try:
        if _SETTINGS.groq_api_key:
            _LAST_SKILL_STATUS["llm_attempted"] = True
        llm_skills = _extract_skills_with_groq(resume_text, skills_source)
        if _LAST_SKILL_STATUS["llm_attempted"]:
            _LAST_SKILL_STATUS["llm_success"] = True
            _LAST_SKILL_STATUS["message"] = "LLM parsing active (Groq)"
    except Exception:
        llm_skills = []
        if _LAST_SKILL_STATUS["llm_attempted"]:
            _LAST_SKILL_STATUS["message"] = "LLM request failed, fallback parsing used"


    # Strict exact-phrase matching from the configured skills list.
    found: list[str] = []
    seen = set()
    for skill in skills_source:
        if _is_skill_present_in_resume(skill, resume_text) and skill not in seen:
            found.append(skill)
            seen.add(skill)

    unique: list[str] = list(found)

    for skill in llm_skills:
        # Guardrail: accept LLM skill only if it is explicitly present in resume text.
        if _is_skill_present_in_resume(skill, resume_text) and skill not in seen:
            unique.append(skill)
            seen.add(skill)

    if llm_skills:
        _LAST_SKILL_STATUS["fallback_used"] = False
        _LAST_SKILL_STATUS["message"] = "LLM parsing active (Groq)"
    elif _LAST_SKILL_STATUS["llm_attempted"]:
        _LAST_SKILL_STATUS["fallback_used"] = True
        if _LAST_SKILL_STATUS["llm_success"]:
            _LAST_SKILL_STATUS["message"] = "LLM returned no skills, fallback parsing used"

    return unique
