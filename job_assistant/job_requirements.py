"""Bounded job input and conservative, evidence-preserving requirement rules."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .cv_analysis import INSTRUCTION, TERMS as CV_TERMS, normal_heading
from .documents import extract_document

MAX_JOB_CHARS = 20_000
MAX_JOB_UNITS = 300
MAX_LINE_CHARS = 1000
MAX_REQUIREMENTS = 100
VERSION = "1.0"

# Specific technologies stay specific: PostgreSQL is not interchangeable with SQL,
# nor REST APIs with all APIs. Longer matches win to avoid nested duplicates.
TERMS = dict(CV_TERMS)
TERMS.update({"postgresql": "postgresql", "postgres": "postgresql", "rest api": "rest apis",
              "rest apis": "rest apis", "restful api": "rest apis", "restful apis": "rest apis",
              "api": "apis", "apis": "apis", "amazon web services": "aws",
              "artificial intelligence": "artificial intelligence", "ai": "artificial intelligence",
              "natural language processing": "natural language processing", "nlp": "natural language processing",
              "typescript": "typescript", "ts": "typescript", "java": "java",
              "continuous integration": "continuous integration", "ci": "continuous integration",
              "continuous delivery": "continuous delivery", "ci/cd": "ci/cd"})
ESSENTIAL = re.compile(r"\b(?:essential|required|requirements?|must|mandatory|need(?:ed)?|minimum)\b", re.I)
DESIRABLE = re.compile(r"\b(?:desirable|preferred|preferably|bonus|optional|nice.to.have|advantage)\b", re.I)
HEADINGS = {"essential": {"essential", "essential requirements", "required skills", "requirements", "must have", "minimum qualifications"},
            "desirable": {"desirable", "desirable requirements", "preferred skills", "nice to have", "bonus skills"}}
BREAKS = {"about us", "benefits", "salary", "how to apply", "responsibilities", "about the role", "what we offer"}
SPLIT = re.compile(r";|(?<=[.!?])\s+|\bbut\b", re.I)
CONTACT = re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+\.\w+", re.I)
STOPWORDS = set("""a an the and or also with of in on at for to from by as is are be have has
must should will you your we our need needed require requires required requirement requirements
essential desirable preferred preferably mandatory optional bonus nice advantage minimum
skill skills knowledge experience experienced expertise proficient proficiency ability strong
good excellent advanced basic expert level working practical familiarity understanding
use using used not no only necessary prior previous necessary plus have hands
""".split())


class JobError(ValueError):
    """Safe user-facing input error."""


@dataclass
class JobEvidence:
    position: int
    reference: str
    start: int
    end: int
    quote: str


@dataclass
class JobDocument:
    source: str
    units: list[dict]

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.units, ensure_ascii=True).encode()).hexdigest()


@dataclass
class Requirement:
    number: int
    label: str
    terms: tuple[str, ...]
    priority: str
    evidence: JobEvidence
    qualifiers: tuple[str, ...] = ()
    excluded: bool = False
    alternative: bool = False


def validate_job(job):
    if not job.units or not any(u["text"].strip() for u in job.units):
        raise JobError("Enter a non-empty job description.")
    if len(job.units) > MAX_JOB_UNITS or sum(len(u["text"]) for u in job.units) > MAX_JOB_CHARS:
        raise JobError("Job description exceeds 20,000 characters or 300 source units.")
    if any(len(line) > MAX_LINE_CHARS for u in job.units for line in u["text"].splitlines()):
        raise JobError("A job-description line exceeds 1,000 characters. Split it into shorter lines.")
    if any(ord(c) < 32 and c not in "\n\r\t\f" for u in job.units for c in u["text"]):
        raise JobError("Job description contains unsupported control characters.")


def job_from_text(text):
    job = JobDocument("entered text", [{"position": n, "reference": f"line {n}", "text": line}
                                       for n, line in enumerate(text.splitlines(keepends=True), 1)])
    validate_job(job)
    return job


def import_job(path):
    document = extract_document(path)
    job = JobDocument(Path(path).name, [{"position": n, "reference": s.reference, "text": s.source_text}
                                       for n, s in enumerate(document.segments, 1)])
    validate_job(job)
    return job, document.warnings


def read_job_entry(read=input, write=print):
    write("Enter the job description; blank lines are allowed. Finish with /done on its own line.")
    lines, length = [], 0
    while True:
        line = read("")
        if line == "/done":
            return job_from_text("\n".join(lines))
        if len(line) > MAX_LINE_CHARS:
            raise JobError("A job-description line exceeds 1,000 characters.")
        length += len(line) + (1 if lines else 0)
        if length > MAX_JOB_CHARS or len(lines) >= MAX_JOB_UNITS:
            raise JobError("Job description exceeds 20,000 characters or 300 source units.")
        lines.append(line)


def term_mentions(text):
    found = []
    for term, canonical in TERMS.items():
        pattern = re.escape(term).replace(r"\ ", r"[\s‐‑–-]+")
        for match in re.finditer(r"(?<!\w)" + pattern + r"(?!\w)", text, re.I):
            if term in {"ml", "ai"} and re.search(r"\d\s*$", text[max(0, match.start() - 30):match.start()]):
                continue
            found.append((match.start(), match.end(), canonical))
    accepted = []
    contacts = list(CONTACT.finditer(text))
    contact_index = 0
    for start, end, canonical in sorted(found, key=lambda x: (x[0], -(x[1] - x[0]))):
        while contact_index < len(contacts) and contacts[contact_index].end() <= start:
            contact_index += 1
        if contact_index < len(contacts) and contacts[contact_index].start() < end:
            continue
        if not accepted or start >= accepted[-1][1]:
            accepted.append((start, end, canonical))
    return accepted


def clauses(text):
    """Preserve offsets; split contrasting priorities without breaking simple lists."""
    boundaries = list(SPLIT.finditer(text))
    markers = [*ESSENTIAL.finditer(text), *DESIRABLE.finditer(text)]
    if len(markers) > 1:
        first_end, last_start = min(m.end() for m in markers), max(m.start() for m in markers)
        for comma in re.finditer(r",|\band\b", text, re.I):
            if first_end <= comma.start() and last_start >= comma.end():
                boundaries.append(comma)
    start = 0
    for match in sorted(boundaries, key=lambda m: m.start()):
        if match.start() < start:
            continue
        raw = text[start:match.start()]
        clean = raw.strip()
        if clean:
            yield start + len(raw) - len(raw.lstrip()), clean
        start = match.end()
    raw = text[start:]
    if raw.strip():
        yield start + len(raw) - len(raw.lstrip()), raw.strip()


def negated_requirement(text):
    # Do not turn double negatives or 'not only' into exclusions.
    if re.search(r"\b(?:not without|no lack|not unnecessary|not lacking|not only)\b", text, re.I):
        return False
    return bool(re.search(r"\b(?:not required|not necessary|need not|must not|do not need|don't need)\b|"
                          r"\bno\b.{0,100}\b(?:required|necessary|needed)\b", text, re.I))


def requirement_qualifiers(text):
    result = []
    if re.search(r"\b(?:\d+(?:\+|\s*[-–]\s*\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|several)\s*(?:years?|months?)\b", text, re.I):
        result.append("duration cannot be inferred from skill mentions")
    if re.search(r"\b(?:advanced|expert|strong|proficient|proficiency|commercial|professional|production|certified|certification|degree|bsc|msc|phd|bachelor|master|equivalent|familiar|basic|interest)\b", text, re.I):
        result.append("level, context or equivalence requires human review")
    if re.search(r"\bexperience\b", text, re.I):
        result.append("practical experience")
    if re.search(r"\b(?:not without|no lack|not unnecessary|not lacking|not essential|and/or)\b", text, re.I):
        result.append("ambiguous qualification or negation scope")
    return tuple(result)


def extract_requirements(job):
    validate_job(job)
    requirements = []
    section = "unclear"

    def add(label, terms, priority, evidence, qualifiers=(), excluded=False, alternative=False):
        if len(requirements) >= MAX_REQUIREMENTS:
            raise JobError("More than 100 requirement items were detected. Use a shorter, focused description.")
        requirements.append(Requirement(len(requirements) + 1, label, terms, priority, evidence,
                                        qualifiers, excluded, alternative))

    for unit in job.units:
        offset = 0
        for raw in unit["text"].splitlines(keepends=True):
            line = raw.strip()
            start = offset + len(raw) - len(raw.lstrip())
            offset += len(raw)
            if not line:
                continue
            heading, colon, inline = line.partition(":")
            normal = normal_heading(heading if colon else line)
            new_section = next((key for key, headings in HEADINGS.items() if normal in headings), None)
            if new_section:
                section = new_section
                if not colon or not inline.strip():
                    continue
                start += len(heading) + 1 + len(inline) - len(inline.lstrip())
                line = inline.strip()
            elif normal in BREAKS:
                section = "unclear"
                continue
            elif colon and not term_mentions(heading) and not ESSENTIAL.search(heading) and not DESIRABLE.search(heading):
                # An unknown heading must not inherit a preceding priority.
                section = "unclear"
            for relative, text in clauses(line):
                position = start + relative
                evidence = JobEvidence(unit["position"], unit["reference"], position, position + len(text), text)
                if INSTRUCTION.search(text):
                    add("Instruction-like text (not evaluated)", (), "unclear", evidence)
                    continue
                essential, desirable = bool(ESSENTIAL.search(text)), bool(DESIRABLE.search(text))
                priority = "unclear" if essential and desirable else "essential" if essential else "desirable" if desirable else section
                if re.search(r"\bnot optional\b", text, re.I):
                    priority = "essential"
                elif re.search(r"\bnot essential\b", text, re.I):
                    priority = "unclear"
                excluded = negated_requirement(text)
                mentions = term_mentions(text)
                terms = tuple(dict.fromkeys(m[2] for m in mentions))
                qualifiers = requirement_qualifiers(text)
                if essential and desirable and not re.search(r"\bnot optional\b", text, re.I):
                    qualifiers += ("conflicting priority markers",)
                if excluded and len(terms) > 1 and not re.search(r"^\W*no\b.+\b(?:required|necessary|needed)\W*$", text, re.I):
                    excluded = False
                    qualifiers += ("ambiguous qualification or negation scope",)
                if re.search(r"\b(?:training provided|we (?:provide|teach)|you will learn|opportunity to learn)\b", text, re.I):
                    excluded = True
                    qualifiers += ("employer training/benefit is not a candidate requirement",)
                if re.search(r"\b(?:may|might|possibly|potentially)\b", text, re.I):
                    priority = "unclear"
                    qualifiers += ("conditional requirement",)
                alternative = bool(re.search(r"\bor\b", text, re.I)) and len(terms) > 1
                if alternative and re.search(r"\band\b", text, re.I):
                    qualifiers += ("mixed AND/OR grouping requires review",)
                # Retain unrecognised content instead of silently dropping it.
                remainder = list(text)
                for a, b, _ in mentions:
                    remainder[a:b] = " " * (b - a)
                residue = [w for w in re.findall(r"[\w+#]+", "".join(remainder).casefold()) if w not in STOPWORDS]
                if re.search(r"\bor\b", text, re.I) and residue:
                    qualifiers += ("unresolved alternative or additional context",)
                if terms:
                    if alternative:
                        add(" OR ".join(terms), terms, priority, evidence, qualifiers, excluded, True)
                    else:
                        for term in terms:
                            add(term, (term,), priority, evidence, qualifiers, excluded)
                    if residue:
                        add("Additional unrecognised criteria/context", (), priority, evidence, excluded=excluded)
                else:
                    add("Unrecognised requirement or context", (), priority, evidence, excluded=excluded)
    if not requirements:
        raise JobError("No requirement text found. Enter more than section headings.")
    return requirements
