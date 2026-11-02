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


def calculate_cv_match_score(requirements):
    """Return a transparent heuristic score from structured CV evidence.

    Requirements marked not_mentioned are excluded because absence of CV text
    is not evidence of a genuine gap. Required items count three times as much
    as preferred items.
    """
    assessed = [
        requirement for requirement in requirements
        if requirement.get("status") in {"matched", "gap"}
    ]
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
