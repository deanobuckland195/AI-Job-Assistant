"""Transparent offline study planning. Suggestions never certify proficiency."""

from .applications import ApplicationError, text_field
from .catalogue import LEARNING_ROADMAPS
from .interview_questions import ROLES
from .skills import normalise_skills

RULES_VERSION = "1.0"
ROLE_SKILLS = {
    "ai-engineering-apprentice": ("python", "git", "sql", "apis", "data analysis", "machine learning", "communication"),
    "junior-software-engineer": ("python", "git", "apis", "sql", "communication"),
    "data-analyst": ("excel", "sql", "python", "data analysis", "communication"),
    "general": ("communication", "git", "data analysis"),
}
STATES = {"supported_wording", "self_reported", "missing_evidence", "uncertain"}
NOTICE = "Learning recommendations only: not verified qualifications, proficiency or guarantees of employment. Completion evidence is self-reported."
PRACTICE = {
    "python": ("Practise variables, functions and input validation using synthetic records.", "Build a tiny CSV validator with tests for missing values."),
    "git": ("Practise commits, branches and merging in a disposable local repository.", "Track a small project and document one resolved merge conflict."),
    "machine learning": ("Compare a simple baseline with a small model on synthetic data; separate training and test data.", "Document leakage checks, an evaluation metric and a model limitation."),
    "communication": ("Explain one technical decision in plain language and ask for feedback.", "Write a short project README describing decisions, checks and limitations."),
    "excel": ("Practise formulas, sorting and a summary chart on synthetic rows.", "Create a small reproducible spreadsheet analysis and check its totals."),
}


def validate_inputs(role_id, skills, weekly_hours):
    if not isinstance(role_id, str) or role_id not in ROLE_SKILLS:
        raise ApplicationError("Choose a supported target role.")
    if type(weekly_hours) is not int or not 1 <= weekly_hours <= 20:
        raise ApplicationError("Weekly study time must be a whole number from 1 to 20 hours.")
    skills = text_field(skills, "Existing skills", 2000)
    selected = normalise_skills(skills)
    if len(selected) > 100 or any(len(skill) > 100 for skill in selected):
        raise ApplicationError("Use at most 100 skills, each no longer than 100 characters.")
    return selected


def generate_plan(role_id, skills="", weekly_hours=4, *, snapshot=None):
    selected = validate_inputs(role_id, skills, weekly_hours)
    if snapshot is not None:
        from .comparison_records import validate_skill_snapshot
        validate_skill_snapshot(snapshot)
    gaps = {skill: {"skill": skill, "state": "self_reported" if skill in selected else "missing_evidence",
                    "basis": "Curated role recommendation; not an employer requirement.", "requirements": []}
            for skill in ROLE_SKILLS[role_id]}
    reviews = []
    for item in snapshot or []:
        if item["status"] == "excluded":
            continue
        if not item["terms"]:
            reviews.append(item["number"])
            continue
        for skill in item["terms"]:
            entry = gaps.setdefault(skill, {"skill": skill, "state": "missing_evidence", "basis": "Stored comparison wording", "requirements": []})
            entry["requirements"].append(item)
    for skill, entry in gaps.items():
        sources = entry["requirements"]
        if not sources:
            continue
        statuses = {s["status"] for s in sources}
        if ("uncertain" in statuses or "unsupported" in statuses or len(statuses) > 1 or
                any(s["alternative"] or s["qualified"] or s["priority"] == "unclear" for s in sources)):
            state = "uncertain"
        elif statuses == {"matched"}:
            state = "supported_wording"
        else:
            state = "self_reported" if skill in selected else "missing_evidence"
        entry.update(state=state, basis="Historical approved CV/job comparison; source coordinates retained, not revalidated.")
    tasks = []
    # Missing evidence first, then clarify uncertainty, then consolidate existing skills.
    for state in ("missing_evidence", "uncertain", "self_reported", "supported_wording"):
        for entry in gaps.values():
            if entry["state"] != state:
                continue
            skill = entry["skill"]
            if state == "uncertain":
                objective = f"Clarify the requirement and current evidence for {skill}; do not assume a skill deficit."
                exercise = "Review the requirement context, alternatives and qualifiers locally; record what remains unknown."
                project = "Choose one relevant example or a small diagnostic exercise after clarifying the requirement."
                effort = 1
            else:
                objective = (f"Practise foundations of {skill} and collect an honest example." if state == "missing_evidence"
                             else f"Consolidate {skill} with a concrete example; existing wording does not verify proficiency.")
                steps = LEARNING_ROADMAPS.get(skill)
                exercise, project = PRACTICE.get(skill, (
                    "Practise one small concept using synthetic data and check the result.",
                    "Create a small reproducible demonstration and describe checks and limitations."))
                if steps:
                    exercise, project = "; ".join(steps[:-1]), steps[-1] + " using synthetic data or a local mock; no paid services required."
                effort = 4 if state == "missing_evidence" else 2
            # One milestone per relative week; split effort to respect the chosen budget.
            parts = (effort + weekly_hours - 1) // weekly_hours
            remaining = effort
            for part in range(parts):
                hours = min(weekly_hours, remaining)
                remaining -= hours
                tasks.append({"week": len(tasks) + 1, "skill": skill,
                    "objective": objective + (f" Part {part + 1}/{parts}: {'practise and make notes' if part < parts - 1 else 'finish the small example and review checks'}." if parts > 1 else ""),
                    "exercise": exercise, "project": project,
                    "expected_evidence": "Record a local artifact path or short description, the checks performed, outcome and one limitation. Do not include secrets.",
                    "study_hours": hours})
    if len(tasks) > 208:
        raise ApplicationError("This plan exceeds 208 weeks. Select a narrower comparison or increase the weekly budget.")
    return {"rules_version": RULES_VERSION, "role_id": role_id, "selected_skills": selected,
            "weekly_hours": weekly_hours, "gaps": list(gaps.values()), "unrecognised_requirements": reviews,
            "milestones": tasks, "notice": NOTICE,
            "rules": "Curated role foundations plus non-excluded comparison terms. Missing evidence: 4 hours; consolidate: 2 hours; clarify uncertainty: 1 hour. One task per relative week, capped by your weekly budget. Estimates are editable, not deadlines."}
