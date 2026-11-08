"""Pure skill comparison functions. No input, storage or network access."""

import re
from dataclasses import dataclass

from .catalogue import REQUIRED_SKILLS, SKILL_ALIASES


def normalise_text(text):
    """Fold case, whitespace and common hyphenated skill spellings."""
    return " ".join(re.sub(r"[-‐‑–]", " ", text.casefold()).split())


def normalise_skills(text):
    """Parse comma-separated input; remove empty entries and duplicates."""
    skills = []
    for value in text.split(","):
        clean = normalise_text(value)
        skill = SKILL_ALIASES.get(clean, clean)
        if skill and skill not in skills:
            skills.append(skill)
    return skills


def check_skills(user_skills, required_skills):
    matching = [skill for skill in required_skills if skill in user_skills]
    missing = [skill for skill in required_skills if skill not in user_skills]
    return matching, missing


def calculate_match(matching_skills, required_skills):
    """Return recognised-skill coverage, with zero for an empty catalogue."""
    required = set(required_skills)
    if not required:
        return 0.0
    return len(set(matching_skills) & required) / len(required) * 100


def detect_job_skills(job_text, required_skills=REQUIRED_SKILLS,
                      skill_aliases=SKILL_ALIASES):
    text = normalise_text(job_text)
    detected = []
    terms = [(skill, skill) for skill in required_skills]
    terms.extend(skill_aliases.items())
    for term, skill in terms:
        if skill in required_skills and skill not in detected:
            if re.search(r"\b" + re.escape(normalise_text(term)) + r"\b", text):
                detected.append(skill)
    return detected


def match_job_skills(user_skills, detected_skills):
    return check_skills(user_skills, detected_skills)


@dataclass
class JobAnalysis:
    detected: list[str]
    matching: list[str]
    missing: list[str]
    score: float | None


def analyse_job(user_skills, job_description):
    if not job_description.strip():
        raise ValueError("Please enter a job description before analysing it.")
    detected = detect_job_skills(job_description)
    matching, missing = match_job_skills(user_skills, detected)
    score = calculate_match(matching, detected) if detected else None
    return JobAnalysis(detected, matching, missing, score)
