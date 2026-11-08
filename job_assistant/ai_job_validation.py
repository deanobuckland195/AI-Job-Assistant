"""Mandatory deterministic validation of AI interpretations; no network access.

AI cannot edit requirement priorities, the offline comparison, or source documents.
Only a small local abbreviation map can add interpretations beyond Phase 2A.
"""

from dataclasses import dataclass, replace
import re

from .cv_analysis import AnalysisError, INSTRUCTION, Evidence, evidence_for, source_lines
from .job_matching import CVClaim, PRACTICAL, claim_state, cv_claim_index, match_requirement
from .job_requirements import (CONTACT, JobEvidence, clauses, extract_requirements,
                               JobError, TERMS, job_from_text, term_mentions)

ABBREVIATIONS = {"py": "python", "k8s": "kubernetes", "sklearn": "scikit-learn", "tf": "tensorflow"}
KINDS = ("abbreviation", "related_evidence", "complex_wording")
STATUSES = ("matched", "missing", "uncertain", "unsupported")


@dataclass
class ValidatedInterpretation:
    requirement: int
    kind: str
    skill: str
    proposed_status: str
    status: str
    reason: str
    job_evidence: JobEvidence
    cv_evidence: Evidence | None
    origin: str = "AI proposal + deterministic validation"


def citation_span(data, units, *, cv=False):
    if not isinstance(data, dict) or set(data) != {"position", "start", "end", "quote"}:
        raise AnalysisError("AI citation structure is invalid; offline comparison is retained.")
    position, start, end, quote = (data[k] for k in ("position", "start", "end", "quote"))
    if (any(type(v) is not int for v in (position, start, end)) or
            not isinstance(quote, str) or not quote.strip() or not 1 <= len(quote) <= 300):
        raise AnalysisError("AI citation types or limits are invalid; offline comparison is retained.")
    unit = next((u for u in units if u["position"] == position), None)
    if unit is None:
        raise AnalysisError("AI cited an unknown source unit; offline comparison is retained.")
    text = unit["reviewed_text"] if cv else unit["text"]
    if not 0 <= start < end <= len(text) or text[start:end] != quote:
        raise AnalysisError("AI citation does not match the approved source text; offline comparison is retained.")
    left, right = text.rfind("\n", 0, start) + 1, text.find("\n", end)
    context = text[left:right if right >= 0 else None]
    if INSTRUCTION.search(context):
        raise AnalysisError("AI cited instruction-bearing text; offline comparison is retained.")
    if cv:
        return evidence_for(unit, start, end)
    return JobEvidence(position, unit["reference"], start, end, quote)


def skills_in(text):
    skills = {skill for _, _, skill in term_mentions(text)}
    contacts = list(CONTACT.finditer(text))
    for alias, skill in ABBREVIATIONS.items():
        for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.I):
            if not any(match.start() < c.end() and match.end() > c.start() for c in contacts):
                skills.add(skill)
    if "rest apis" in skills:
        skills.add("apis")
    if "ci/cd" in skills:
        skills.add("continuous integration")
    return skills


def augmented_index(cv):
    index = cv_claim_index(cv)
    for segment, offset, line in source_lines(cv):
        for relative, text in clauses(line):
            if INSTRUCTION.search(text):
                continue
            contacts = list(CONTACT.finditer(text))
            for alias, canonical in ABBREVIATIONS.items():
                for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.I):
                    if any(match.start() < c.end() and match.end() > c.start() for c in contacts):
                        continue
                    state = claim_state(text, match.start(), match.end())
                    start = 0 if len(text) <= 300 else max(0, match.start() - 80)
                    end = len(text) if len(text) <= 300 else min(len(text), match.end() + 100)
                    evidence = evidence_for(segment, offset + relative + start, offset + relative + end)
                    practical = len(text) <= 300 and bool(PRACTICAL.search(text))
                    bucket = index.setdefault(canonical, [])
                    if sum(c.state == state and c.practical == practical for c in bucket) < 2:
                        bucket.append(CVClaim(state, evidence, practical))
    for specific, general in (("rest apis", "apis"), ("ci/cd", "continuous integration")):
        if specific in index:
            index.setdefault(general, []).extend(index[specific])
    return index


def interpreted_requirement(requirement, kind, skill, job_quote):
    if requirement.terms:
        return requirement if skill in requirement.terms else None
    if kind != "abbreviation" or not skill or requirement.excluded:
        return None
    text = requirement.evidence.quote
    replaced = False
    for alias, canonical in ABBREVIATIONS.items():
        if canonical == skill and re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", job_quote, re.I):
            text, count = re.subn(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", canonical, text, flags=re.I)
            replaced = replaced or bool(count)
    if not replaced:
        return None
    try:
        parsed = extract_requirements(job_from_text(text))
    except JobError:
        return None
    # Do not equate an entire unknown compound/qualification with one known skill.
    if any(not r.terms or r.terms != (skill,) for r in parsed):
        return None
    candidate = parsed[0]
    return replace(candidate, number=requirement.number, evidence=requirement.evidence,
                   priority=requirement.priority, excluded=requirement.excluded or candidate.excluded)


def positive_citation(cv, evidence, skill, practical=False):
    """Check the cited clause itself, not a different positive mention elsewhere."""
    if evidence is None:
        return False
    aliases = {term: canonical for term, canonical in {**TERMS, **ABBREVIATIONS}.items() if canonical == skill}
    for segment, offset, line in source_lines(cv):
        if segment["position"] != evidence.position:
            continue
        for relative, text in clauses(line):
            base = offset + relative
            if not base <= evidence.start < evidence.end <= base + len(text) or INSTRUCTION.search(text):
                continue
            if practical and not PRACTICAL.search(text):
                continue
            for alias in aliases:
                pattern = re.escape(alias).replace(r"\ ", r"[\s‐‑–-]+")
                for match in re.finditer(r"(?<!\w)" + pattern + r"(?!\w)", text, re.I):
                    if any(match.start() < c.end() and match.end() > c.start() for c in CONTACT.finditer(text)):
                        continue
                    if evidence.start <= base + match.start() < base + match.end() <= evidence.end:
                        if claim_state(text, match.start(), match.end()) == "positive":
                            return True
    return False


def validate_interpretations(payload, cv, job, comparison, allowed_skills):
    if not isinstance(payload, dict) or set(payload) != {"interpretations"}:
        raise AnalysisError("AI matching response structure is invalid; offline comparison is retained.")
    items = payload["interpretations"]
    if not isinstance(items, list) or len(items) > 12:
        raise AnalysisError("AI interpretation count is invalid; offline comparison is retained.")
    requirements = {m.requirement.number: m.requirement for m in comparison.matches}
    index = augmented_index(cv)
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"requirement", "kind", "skill", "claim", "job_evidence", "cv_evidence"}:
            raise AnalysisError("AI matching response fields are invalid; offline comparison is retained.")
        number, kind, skill, proposed = (item[k] for k in ("requirement", "kind", "skill", "claim"))
        if (type(number) is not int or number not in requirements or number in seen or
                not isinstance(kind, str) or kind not in KINDS or not isinstance(skill, str) or skill not in allowed_skills or
                not isinstance(proposed, str) or proposed not in STATUSES):
            raise AnalysisError("AI matching response values are invalid; offline comparison is retained.")
        seen.add(number)
        requirement = requirements[number]
        job_evidence = citation_span(item["job_evidence"], job.units)
        original = requirement.evidence
        if (job_evidence.position != original.position or job_evidence.start < original.start or job_evidence.end > original.end):
            raise AnalysisError("AI job citation is outside its requirement; offline comparison is retained.")
        cv_evidence = citation_span(item["cv_evidence"], cv["segments"], cv=True) if item["cv_evidence"] is not None else None
        candidate = interpreted_requirement(requirement, kind, skill, job_evidence.quote)
        local = match_requirement(candidate, index) if candidate else None
        job_skill = bool(skill and skill in skills_in(job_evidence.quote))
        exact_skill = bool(job_skill and cv_evidence and skill in skills_in(cv_evidence.quote))
        positive = positive_citation(cv, cv_evidence, skill, bool(candidate and "practical experience" in candidate.qualifiers))
        if proposed == "matched" and local and local.status == "matched" and exact_skill and positive:
            status = "matched"
            reason = "Skill interpretation and both citations passed local rules. This validates document evidence, not real-world competence or qualifications."
        elif (proposed == "missing" and local and local.status == "missing" and job_skill and
              (cv_evidence is None or skill in skills_in(cv_evidence.quote))):
            status = "missing"
            reason = "Full reviewed-CV scan found no positive support for the interpreted skill. Missing evidence is not proof of absence."
        elif proposed in {"uncertain", "unsupported"}:
            status = proposed
            reason = "Retained only for manual review; no positive match or qualification is established by this model interpretation."
        else:
            status = "unsupported"
            reason = "Model conclusion was not upheld by mandatory local validation; offline results remain authoritative."
        result.append(ValidatedInterpretation(number, kind, skill, proposed, status, reason, job_evidence, cv_evidence))
    return result
