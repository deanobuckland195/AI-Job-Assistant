"""Offline comparisons of requirement wording against approved reviewed CV claims."""

from dataclasses import dataclass, field
import re

from .cv_analysis import INSTRUCTION, Evidence, analyse_cv, evidence_for, source_lines
from .job_requirements import Requirement, clauses, extract_requirements, term_mentions

WEAK = re.compile(r"\b(?:learning|beginner|basic|familiar|interested|want|aspir\w*|hope|seeking|would like|exposure|limited|not (?:an? )?expert)\b", re.I)
THIRD_PARTY = re.compile(r"\b(?:colleague|required|requirements|employer requires|job requires|my team|our team|(?:team|company) (?:uses|used)|client (?:requires|requested))\b", re.I)
RELATED = {"postgresql": {"sql"}, "sql": {"postgresql"}, "rest apis": {"apis"},
           "ci/cd": {"continuous integration", "continuous delivery"}}
PRACTICAL = re.compile(r"\b(?:built|developed|implemented|used|maintained|created|delivered|designed|analysed|analyzed)\b", re.I)


@dataclass
class CVClaim:
    state: str
    evidence: Evidence
    practical: bool


@dataclass
class Match:
    requirement: Requirement
    status: str
    reason: str
    cv_evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Comparison:
    cv_id: int
    cv_title: str
    cv_reviewed_at: str
    cv_digest: str
    job_source: str
    job_digest: str
    matches: list[Match]
    notes: list[str]
    ai_attempted: bool = False
    ai_model: str = ""
    ai_results: list = field(default_factory=list)
    ai_notes: list[str] = field(default_factory=list)


def claim_state(text, start, end):
    if len(text) > 300:
        return "uncertain"
    clean = re.sub(r"\b(?:machine[\s‐‑–-]+learning|deep[\s‐‑–-]+learning|not only)\b", "", text, flags=re.I)
    if (THIRD_PARTY.search(clean) or WEAK.search(clean) or
            re.search(r"\b(?:coffee|snake|millilitres|milliliters)\b", clean, re.I) or
            re.search(r"\b(?:not without|no lack|not unnecessary|not lacking)\b", clean, re.I)):
        return "uncertain"
    prefix, suffix = text[:start], text[end:]
    prefix = re.sub(r"\bnot only\b", "", prefix, flags=re.I).replace("’", "'")
    negatives = list(re.finditer(r"\b(?:no|not|never|without|lack|lacking|cannot|can't|don't|haven't|hasn't|hadn't|didn't|doesn't|couldn't|unable to)\b", prefix, re.I))
    if negatives:
        return "uncertain" if "," in prefix[negatives[-1].end():] else "negative"
    if re.match(r"\s*(?:experience\s*)?(?:(?:is|was|were|are)\s+)?(?:not|never|none)\b", suffix, re.I):
        return "negative"
    return "positive"


def cv_claim_index(cv):
    """Scan all reviewed text, avoiding Phase 1C's display-only finding cap."""
    index = {}
    for segment, line_start, line in source_lines(cv):
        for relative, text in clauses(line):
            if INSTRUCTION.search(text):
                continue
            practical = len(text) <= 300 and bool(PRACTICAL.search(text))
            for start, end, canonical in term_mentions(text):
                state = claim_state(text, start, end)
                excerpt_start = 0 if len(text) <= 300 else max(0, start - 80)
                excerpt_end = len(text) if len(text) <= 300 else min(len(text), end + 100)
                evidence = evidence_for(segment, line_start + relative + excerpt_start,
                                        line_start + relative + excerpt_end)
                claim = CVClaim(state, evidence, practical)
                bucket = index.setdefault(canonical, [])
                # Keep at most two examples per state/practical combination. All
                # states are still scanned; contradictory claims are not lost.
                if sum(c.state == state and c.practical == claim.practical for c in bucket) < 2:
                    bucket.append(claim)
    return index


def match_requirement(requirement, index):
    if requirement.excluded:
        return Match(requirement, "excluded", "Negated/prohibited skill or employer-provided context; not counted as a positive applicant requirement.")
    if not requirement.terms:
        return Match(requirement, "unsupported", "Unrecognised criteria or context: this rule set cannot assess it. Review the full excerpt manually.")
    claims = [c for term in requirement.terms for c in index.get(term, [])]
    positive_terms, negative_terms, uncertain_terms = set(), set(), set()
    for term in requirement.terms:
        for claim in index.get(term, []):
            {"positive": positive_terms, "negative": negative_terms, "uncertain": uncertain_terms}[claim.state].add(term)
    # Include all states in the evidence display, not just the earliest positives.
    evidence = []
    for state in ("positive", "negative", "uncertain"):
        examples = [c.evidence for c in sorted(claims, key=lambda c: not c.practical) if c.state == state]
        evidence.extend(examples[:2])
    strict_qualifiers = [q for q in requirement.qualifiers if q != "practical experience"]
    if strict_qualifiers:
        return Match(requirement, "uncertain", "; ".join(strict_qualifiers) + ". A skill mention alone cannot establish the complete requirement.", evidence)
    if positive_terms & negative_terms:
        return Match(requirement, "uncertain", "The CV contains conflicting positive and negative wording; resolve the contradiction.", evidence)
    if positive_terms:
        if "practical experience" in requirement.qualifiers:
            practical = any(c.state == "positive" and c.practical for c in claims)
            if not practical:
                return Match(requirement, "uncertain", "A skill is mentioned, but a practical activity supporting the experience requirement is not explicit.", evidence)
        return Match(requirement, "matched", "Positive reviewed CV wording supports this skill mention" +
                     (" (one listed alternative is sufficient)." if requirement.alternative else ".") +
                     " This is a self-reported claim, not verified proficiency.", evidence)
    if uncertain_terms:
        return Match(requirement, "uncertain", "CV wording is tentative, aspirational, third-party, ambiguous or too long to resolve safely.", evidence)
    related = [c.evidence for term in requirement.terms for broader in RELATED.get(term, set()) for c in index.get(broader, [])]
    if related:
        return Match(requirement, "uncertain", "Related technology is mentioned, but it does not establish the requested specific skill.", related[:2])
    if negative_terms:
        return Match(requirement, "missing", "The CV explicitly denies relevant experience/skill; no positive supporting claim was found.", evidence)
    return Match(requirement, "missing", "Not evidenced in the reviewed CV. This does not mean the person lacks the skill.")


def compare_job(cv, job, warnings=()):
    analysis = analyse_cv(cv)  # Enforces approval and carries provenance/limitations.
    requirements = extract_requirements(job)
    index = cv_claim_index(cv)
    # A REST API mention also supports a generic API mention, but not vice versa.
    if "rest apis" in index:
        index.setdefault("apis", []).extend(index["rest apis"])
    if "ci/cd" in index:
        index.setdefault("continuous integration", []).extend(index["ci/cd"])
    matches = [match_requirement(requirement, index) for requirement in requirements]
    notes = list(dict.fromkeys([*analysis.notes, *warnings,
        "Missing means not evidenced, not confirmed absence. Unsupported criteria remain visible and are not treated as matches.",
        "No suitability score or hiring probability is calculated. Counts are descriptive only.",
        "Rules cannot verify qualifications, infer experience duration, or fully resolve all negation and grammar.",
        "Skill matching scans all approved reviewed text; it is not limited to the Phase 1C report's displayed findings.",
    ]))
    return Comparison(analysis.cv_id, analysis.title, analysis.reviewed_at, analysis.source_digest,
                      job.source, job.digest, matches, notes)
