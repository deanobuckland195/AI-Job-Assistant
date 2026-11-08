"""Deterministic analysis of reviewed CV claims, never verification of ability."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import unicodedata

from .catalogue import REQUIRED_SKILLS, SKILL_ALIASES

VERSION = "1.0"
CATEGORIES = ("skills", "experience", "education", "projects", "achievements")
MAX_FINDINGS_PER_CATEGORY = 20
MAX_QUOTE = 300
ACTIONS = {
    "quantify": "If you have evidence, add an outcome, baseline and timeframe. Use real figures only; qualitative outcomes are also useful.",
    "ownership": "Clarify your own contribution, the action you took and the result; distinguish team work from personal responsibility.",
    "wording": "Replace vague wording with a specific action, context and outcome that you can support.",
    "dates": "If applicable, add consistent start/end dates and clarify whether the role or course is ongoing.",
    "tools": "If accurate, name the tools or methods you actually used and explain their purpose.",
    "structure": "Use a clear section heading and concise bullets so this evidence is easy to find.",
}
HEADINGS = {
    "skills": {"skills", "technical skills", "core skills", "technologies", "competencies"},
    "experience": {"experience", "work experience", "employment", "employment history", "professional experience"},
    "education": {"education", "qualifications", "education and qualifications", "certifications", "training"},
    "projects": {"projects", "personal projects", "portfolio", "selected projects"},
    "achievements": {"achievements", "awards", "accomplishments"},
}
SECTION_BREAKS = {"summary", "profile", "personal profile", "interests", "references", "contact", "career objective"}
INSTRUCTION = re.compile(
    r"ignore.{0,40}(?:instructions|previous|above)|(?:system|developer|assistant)\s*(?:message|prompt|:)|"
    r"<\s*/?(?:system|assistant|developer)|you are (?:an? |the )?(?:ai|assistant)|"
    r"(?:send|upload|exfiltrate|leak).{0,60}(?:cv|data|key|secret)|"
    r"(?:output|return|respond).{0,30}(?:json|instead)|reveal.{0,30}(?:prompt|secret|key)", re.I)
AMBIGUOUS = re.compile(r"\b(?:want to|hope to|aspir\w*|interested in|planning to|would like|no|not|without|lack|limited|learning|beginner|familiar)\b", re.I)
ACTION = re.compile(r"\b(?:built|developed|created|implemented|designed|maintained|delivered|managed|led|supported|helped|worked|responsible|analysed|analyzed)\b", re.I)
OUTCOME = re.compile(r"\b(?:reduced|increased|improved|saved|achieved|awarded|won|delivered|completed)\b", re.I)
EDUCATION = re.compile(r"\b(?:university|bachelor|master|bsc|msc|phd|diploma|gcse|a.level|degree|apprenticeship|certificate)\b", re.I)
TERMS = dict(SKILL_ALIASES)
TERMS.update({s: s for s in REQUIRED_SKILLS})
TERMS.update({s: s for s in ("docker", "kubernetes", "pytorch", "tensorflow", "aws", "azure", "fastapi", "pandas", "numpy", "scikit-learn", "c++", "c#")})


class AnalysisError(ValueError):
    """Safe validation failure, without source document content."""


@dataclass
class Evidence:
    position: int
    reference: str
    start: int
    end: int
    quote: str
    corrected: bool


@dataclass
class Finding:
    category: str
    label: str
    status: str
    evidence: Evidence


@dataclass
class Suggestion:
    action: str
    message: str
    evidence: Evidence | None = None
    origin: str = "offline"


@dataclass
class CVAnalysis:
    cv_id: int
    title: str
    reviewed_at: str
    source_digest: str
    findings: list[Finding] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def validate_cv(cv):
    if not cv.get("reviewed_at"):
        raise AnalysisError("Only an approved, imported CV can be analysed. Complete cv-import review first.")
    segments = cv.get("segments", [])
    if (not segments or len(segments) > 2000 or
            sum(len(s["reviewed_text"]) for s in segments) > 200_000):
        raise AnalysisError("CV content is empty or exceeds the offline analysis limits.")
    positions = [s["position"] for s in segments]
    if len(positions) != len(set(positions)) or not any(s["reviewed_text"].strip() for s in segments):
        raise AnalysisError("CV source units are invalid or contain no reviewed text.")


def evidence_for(segment, start, end):
    end = min(end, start + MAX_QUOTE)
    return Evidence(segment["position"], segment["reference"], start, end,
                    segment["reviewed_text"][start:end],
                    segment["source_text"] != segment["reviewed_text"])


def source_lines(cv):
    for segment in cv["segments"]:
        offset = 0
        for raw in segment["reviewed_text"].splitlines(keepends=True):
            clean = raw.strip()
            if clean:
                start = offset + len(raw) - len(raw.lstrip())
                yield segment, start, clean
            offset += len(raw)


def normal_heading(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.strip(" \t#*•-–—:|_")
    return " ".join(text.split())


def analyse_cv(cv):
    validate_cv(cv)
    payload = [(s["position"], s["reference"], s["reviewed_text"]) for s in cv["segments"]]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=True).encode()).hexdigest()
    result = CVAnalysis(cv["id"], cv["title"], cv["reviewed_at"], digest)
    counts = dict.fromkeys(CATEGORIES, 0)
    section = None
    seen = set()
    capped = False

    def finding(category, label, status, evidence):
        nonlocal capped
        key = (category, label, status, evidence.position, evidence.start)
        if key in seen:
            return
        if counts[category] >= MAX_FINDINGS_PER_CATEGORY:
            capped = True
            return
        seen.add(key)
        counts[category] += 1
        result.findings.append(Finding(category, label, status, evidence))

    for segment, start, text in source_lines(cv):
        evidence = evidence_for(segment, start, start + len(text))
        if INSTRUCTION.search(text):
            if "Instruction-like CV text was treated as data and excluded from findings." not in result.notes:
                result.notes.append("Instruction-like CV text was treated as data and excluded from findings.")
            continue
        heading, separator, inline = text.partition(":")
        normal = normal_heading(heading if separator else text)
        detected_section = next((key for key, names in HEADINGS.items() if normal in names), None)
        if detected_section:
            section = detected_section
            if not separator or not inline.strip():
                continue
            start += len(heading) + 1 + len(inline) - len(inline.lstrip())
            text = inline.strip()
            evidence = evidence_for(segment, start, start + len(text))
        elif normal in SECTION_BREAKS:
            section = None
            continue
        ambiguous = bool(AMBIGUOUS.search(text))
        status = "uncertain" if ambiguous else "supported"
        # Exact mentions are evidence of wording only, not proof of competence.
        for term, canonical in TERMS.items():
            match = re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I)
            if match:
                term_start = start + match.start()
                term_evidence = evidence_for(segment, max(start, term_start - 50), start + min(len(text), match.end() + 100))
                finding("skills", f"Mention: {canonical}", status, term_evidence)
        if section and section != "skills":
            finding(section, "CV statement under this heading", status, evidence)
        elif not section:
            if EDUCATION.search(text):
                finding("education", "Possible education/training statement", "uncertain", evidence)
            if re.search(r"\bproject\b", text, re.I):
                finding("projects", "Possible project statement", "uncertain", evidence)
            if ACTION.search(text):
                finding("experience", "Activity statement; employment context not established", "uncertain", evidence)
        if OUTCOME.search(evidence.quote) and re.search(r"\d+\s*(?:%|hours?|days?|users?|customers?|seconds?|minutes?|projects?)\b|\b\d+%", evidence.quote, re.I):
            finding("achievements", "Quantified outcome claim", status, evidence)
        if len(result.suggestions) < 15:
            action = None
            if re.search(r"\b(?:helped|worked on|responsible for|various|excellent|hard.working)\b", evidence.quote, re.I):
                action = "wording"
            elif ACTION.search(evidence.quote) and not re.search(r"\d", text):
                action = "quantify"
            elif section in {"experience", "education"} and not re.search(r"\b(?:19|20)\d{2}\b", text):
                action = "dates"
            if action:
                result.suggestions.append(Suggestion(action, ACTIONS[action], evidence))
    for category in CATEGORIES:
        if not any(f.category == category for f in result.findings):
            result.unknowns.append(f"{category.title()}: no recognisable evidence found. This does not establish that it is absent.")
            result.suggestions.append(Suggestion("structure", f"If relevant, add a clearly labelled {category} section with truthful supporting details."))
    result.unknowns.extend([
        "Proficiency, accuracy of claims and total years of experience cannot be verified from wording alone.",
        "ATS compatibility, visual layout and hiring probability are not assessed from extracted text.",
    ])
    result.notes.extend(cv.get("warnings", []))
    result.notes.append("Citations refer to approved reviewed text; corrected units may differ from the original extraction.")
    if capped:
        result.notes.append("Findings limited to 20 per category; this report is not an exhaustive inventory.")
    return result
