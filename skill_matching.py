SKILL_ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "py": "python",
    "python": "python",
    "ml": "machine learning",
    "machine learning": "machine learning"
}


def expand_skill_terms(skill):
    """Return explicit skills evidenced by a short extracted phrase.

    CV extraction can return a project phrase instead of one item per skill.
    Only terms that are explicitly present are added; this is not inference.
    """
    text = " ".join(str(skill).strip().lower().split())
    terms = []
    known_terms = (
        ("openai api", ("openai api", "openai apis", "openai application programming interface")),
        ("prompt engineering", ("prompt engineering",)),
        ("machine learning", ("machine learning", "ml")),
        ("streamlit", ("streamlit",)),
        ("python", ("python",)),
        ("git", ("git",)),
        ("sql", ("sql",)),
    )
    for canonical, phrases in known_terms:
        if any(phrase in text for phrase in phrases):
            terms.append(canonical)
    return terms or [SKILL_ALIASES.get(text, text)]

def normalise_skill(skill):
    skill = " ".join(skill.strip().lower().split())
    return SKILL_ALIASES.get(skill, skill)


def normalise_skills(skills):
    """Canonicalise and expand an extracted skill list without inventing terms."""
    return list(dict.fromkeys(
        term
        for skill in skills
        if isinstance(skill, str) and skill.strip()
        for term in expand_skill_terms(skill)
    ))

def calculate_weighted_match(detected_skills, job_matching_skills, skill_weights):
    detected_skills = set(
        normalise_skill(skill) for skill in detected_skills
    )

    job_matching_skills = set(
        normalise_skill(skill) for skill in job_matching_skills
    )

    skill_weights = {
        normalise_skill(skill): weight
        for skill, weight in skill_weights.items()
    }

    total_weight = sum(
        skill_weights.get(skill, 1)
        for skill in detected_skills
    )

    matched_weight = sum(
        skill_weights.get(skill, 1)
        for skill in job_matching_skills
        if skill in detected_skills
    )

    if total_weight == 0:
        return 0

    return (matched_weight / total_weight) * 100


def deduplicate_requirements(requirements):
    """Return one entry per explicitly extracted requirement.

    AI output can repeat a requirement with different wording or evidence
    states. Exact semantic equivalence is intentionally limited to normalized
    text here: this prevents double-counting without inferring that two
    different requirements are the same.
    """
    status_priority = {"not_mentioned": 0, "gap": 1, "matched": 2}
    unique = {}

    for requirement in requirements or []:
        if not isinstance(requirement, dict):
            continue
        label = requirement.get("requirement")
        if not isinstance(label, str) or not label.strip():
            continue
        key = " ".join(label.casefold().split())
        existing = unique.get(key)
        if existing is None:
            unique[key] = requirement
            continue

        current_status = status_priority.get(existing.get("status"), -1)
        new_status = status_priority.get(requirement.get("status"), -1)
        if new_status > current_status:
            unique[key] = requirement
        if requirement.get("importance") == "required":
            unique[key] = {**unique[key], "importance": "required"}

    return list(unique.values())


def calculate_cv_match_score(requirements):
    """Return CV requirement coverage from all unique extracted requirements.

    Every requirement contributes to the denominator, including
    ``not_mentioned`` items. That status means the CV provides no evidence
    either way; it is not treated as proof that the candidate lacks the skill.
    Required items count three times as much as preferred items.
    """
    assessed = deduplicate_requirements(requirements)
    if not assessed:
        return None

    total_weight = sum(
        3 if requirement.get("importance") == "required" else 1
        for requirement in assessed
    )
    matched_weight = sum(
        3 if requirement.get("importance") == "required" else 1
        for requirement in assessed
        if requirement.get("status") == "matched"
    )
    return (matched_weight / total_weight) * 100
