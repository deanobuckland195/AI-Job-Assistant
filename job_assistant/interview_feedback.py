"""Deterministic coaching cues, with exact answer/CV evidence and no scoring."""

import re

from .cv_analysis import INSTRUCTION, source_lines, validate_cv
from .interview_questions import COACHING, STAR

FEEDBACK_VERSION = "1.0"
MAX_ANSWER_CHARS = 8000
MAX_LINES = 100
MAX_LINE_CHARS = 2000
MAX_CLAIMS = 12
LABEL = re.compile(r"(?im)^[ \t#*•-]*(situation|task|action|result|s|t|a|r)[ \t]*:[ \t]*")
SHORT_LABELS = {"s": "situation", "t": "task", "a": "action", "r": "result"}
OUTCOME = re.compile(r"\b(?:built|developed|implemented|reduced?|increased?|improved?|saved?|delivered|completed|won|achieved|learned)\b", re.I)
TENTATIVE = re.compile(r"\b(?:no|not|never|cannot|unable to|failed to|(?:did|does|do|was|were|is|are|have|has|had|could|would)n['’]t|can['’]t|would|could|might|will|plan(?:ned|ning)?|hop(?:e|ed|ing)|want(?:ed)?|goal|aim(?:ed|ing)?|intend(?:ed)?|hypothetical|fictional|example|target(?:ed)?)\b", re.I)
INSTRUCTION_LIKE = re.compile(INSTRUCTION.pattern + r"|(?:give|output|return).{0,35}(?:perfect|score|hired|pass me)", re.I)
HEURISTICS = {
    "situation": re.compile(r"\b(?:during|when|while|at my|in my|on a project)\b", re.I),
    "task": re.compile(r"\b(?:my task|my goal|i needed to|i had to|i was responsible|assigned)\b", re.I),
    "action": re.compile(r"\bi (?:built|developed|tested|checked|implemented|analysed|analyzed|changed|created|explained)\b", re.I),
    "result": re.compile(r"\b(?:as a result|resulted|reduced|increased|improved|saved|achieved|learned)\b", re.I),
}
STOP = set("i we my our the a an to in on at by of for with and was were is are did do had have it this that from as me us".split())
STEMS = dict(zip(("built", "developed", "implemented", "reduced", "increased", "improved", "saved", "delivered", "completed", "achieved", "learned"),
                 ("build", "develop", "implement", "reduce", "increase", "improve", "save", "deliver", "complete", "achieve", "learn")))


class InterviewError(ValueError):
    """Safe local practice validation error."""


def validate_answer(text):
    if not isinstance(text, str):
        raise InterviewError("Practice answer must be text.")
    text = text.strip()
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise InterviewError("Practice answer must contain valid Unicode text.") from None
    if not text or len(text) > MAX_ANSWER_CHARS:
        raise InterviewError("Enter an answer containing 1–8,000 characters.")
    lines = text.splitlines()
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE_CHARS for line in lines):
        raise InterviewError("Use at most 100 lines, each no longer than 2,000 characters.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise InterviewError("Answer contains unsupported control characters.")
    if not re.search(r"\w", LABEL.sub("", text)):
        raise InterviewError("Enter answer content, not only blank STAR labels or punctuation.")
    return text


def words(text):
    return re.findall(r"\b[\w']+\b", text.casefold())


def span(text, start, end):
    clipped = min(end, start + 300)
    return {"start": start, "end": clipped, "quote": text[start:clipped], "truncated": end > clipped}


def clauses(text):
    """Yield exact offsets, excluding label prefixes and instruction-like lines."""
    offset = 0
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        if INSTRUCTION_LIKE.search(line):
            offset += len(raw)
            continue
        label = LABEL.match(line)
        base = label.end() if label else 0
        previous = base
        for delimiter in [*re.finditer(r"(?<=[.!?])\s+|;", line[base:]), None]:
            stop = base + delimiter.start() if delimiter else len(line)
            raw_piece = line[previous:stop]
            body = raw_piece.strip(" \t•-*#.!?")
            if body:
                start = offset + previous + len(raw_piece) - len(raw_piece.lstrip(" \t•-*#.!?"))
                yield start, start + len(body), body
            previous = base + delimiter.end() if delimiter else len(line)
        offset += len(raw)


def signature(text):
    return {STEMS.get(word, word) for word in words(text) if word not in STOP}


def cv_clauses(cv):
    if cv is None:
        return []
    validate_cv(cv)
    result = []
    for segment, offset, line in source_lines(cv):
        if INSTRUCTION_LIKE.search(line):
            continue
        for start, end, body in clauses(line):
            result.append((segment, offset + start, offset + end, body, signature(body)))
    return result


def corroborate(body, source):
    """Exact specific wording only; similarity never becomes positive proof."""
    anchors = signature(body)
    if len(body) > 300 or len(anchors) < 3 or TENTATIVE.search(body):
        return "uncertain", None, "Wording is tentative, negated, too long or lacks enough specific detail to corroborate."
    matches, conflict = [], False
    for segment, start, end, cv_body, cv_signature in source:
        if len(anchors & cv_signature) / len(anchors) >= 0.8 and TENTATIVE.search(cv_body):
            conflict = True
        found = re.search(r"(?<!\w)" + re.escape(body) + r"(?!\w|\.\d)", cv_body, re.I)
        if found and not TENTATIVE.search(cv_body) and len(cv_body) <= 500:
            matches.append({"position": segment["position"], "reference": segment["reference"],
                            "start": start + found.start(), "end": start + found.end(),
                            "corrected": segment["source_text"] != segment["reviewed_text"]})
    if conflict:
        return "uncertain", None, "Related CV wording is negative/tentative or conflicting; resolve the source context before relying on it."
    if matches:
        return "supported_wording", matches[0], "Specific wording is present in the linked approved CV. This is not independent verification or proof of individual ownership."
    return "answer_only", None, "No exact corroborating passage found in the available CV. This is not evidence that the claim is false."


def star_structure(text, question, safe_clauses):
    results, missing = {}, []
    labels = list(LABEL.finditer(text))
    for name, guidance in STAR.items():
        evidence = []
        labelled = []
        for i, match in enumerate(labels):
            label = SHORT_LABELS.get(match.group(1).lower(), match.group(1).lower())
            if label == name:
                end = labels[i + 1].start() if i + 1 < len(labels) else len(text)
                labelled.append((match.end(), end))
        if question["kind"] != "behavioural":
            state = "not_required"
        elif len(labelled) > 1:
            state = "ambiguous_labels"
            missing.append(f"{name.title()}: repeated labels make the structure ambiguous; consolidate them.")
        elif labelled:
            relevant = [(a, b, body) for a, b, body in safe_clauses if labelled[0][0] <= a < labelled[0][1]]
            combined = " ".join(body for _, _, body in relevant)
            state = "explicit_detail" if len(words(combined)) >= 5 and len(set(words(combined))) >= 3 else "missing_detail"
            evidence = [span(text, a, b) for a, b, _ in relevant[:1]]
            if state == "missing_detail":
                missing.append(f"{name.title()}: a label alone or a very short fragment does not supply enough detail.")
        else:
            relevant = [(a, b, body) for a, b, body in safe_clauses if HEURISTICS[name].search(body) and len(words(body)) >= 5]
            state = "possible_detail" if relevant else "missing_detail"
            evidence = [span(text, a, b) for a, b, _ in relevant[:1]]
            missing.append(f"{name.title()}: {'possible unlabelled wording; check its meaning and label it clearly' if relevant else 'no clear detail recognised' }.")
        results[name] = {"state": state, "guidance": guidance, "answer_evidence": evidence}
    return results, missing


def analyse_answer(text, question, *, role_id="general", cv=None, cv_availability=None):
    text = validate_answer(text)
    safe = list(clauses(text))
    structure, missing = star_structure(text, question, safe)
    tokens = words(text)
    suggestions = []
    if question["kind"] == "behavioural":
        suggestions.extend(STAR[name] for name, part in structure.items() if part["state"] != "explicit_detail")
    else:
        suggestions.append("STAR is optional for this question. Give a direct explanation, a truthful example where useful, and a limitation or check.")
    if len(tokens) < (30 if question["kind"] == "behavioural" else 15):
        suggestions.append("This answer is brief. If useful, add a concrete context or example; length alone does not determine quality.")
    long_sentences = [span(text, a, b) for a, b, body in safe if len(words(body)) > 35][:5]
    vague = [span(text, a, b) for a, b, body in safe if re.search(r"\b(?:stuff|things|various tasks|helped a bit|somehow)\b", body, re.I)][:5]
    repeated = len(tokens) >= 20 and len(set(tokens)) / len(tokens) < 0.35
    if long_sentences:
        suggestions.append("Consider breaking long sentences into shorter steps. This is a readability cue, not a communication-ability judgement.")
    if vague:
        suggestions.append("Replace vague wording with the real action, object and reason, without adding unsupported facts.")
    if repeated:
        suggestions.append("Some wording repeats frequently; consider removing repetition while keeping the meaning.")
    if any(re.search(r"\b(?:we|our team|my team)\b", body, re.I) for _, _, body in safe):
        missing.append("Team wording does not establish your individual contribution; distinguish your action from the team's outcome.")
    topics = question.get("topics", [])
    absent_topics = [topic for topic in topics if not re.search(r"(?<!\w)" + re.escape(topic) + r"(?!\w)", " ".join(body for _, _, body in safe), re.I)]
    if absent_topics:
        suggestions.append("If relevant, consider discussing: " + ", ".join(absent_topics) + ". Mention checks do not assess technical correctness or knowledge.")
    sources = cv_clauses(cv)
    claims = []
    total_claims = 0
    for a, b, body in safe:
        if not OUTCOME.search(body):
            continue
        total_claims += 1
        if len(claims) >= MAX_CLAIMS:
            continue
        if cv is None:
            state, evidence, reason = "answer_only", None, "Self-reported answer wording; no approved CV is available for corroboration."
            if TENTATIVE.search(body):
                state, reason = "uncertain", "Tentative or negative wording does not establish an achieved outcome."
        else:
            state, evidence, reason = corroborate(body, sources)
        claims.append({"state": state, "answer_evidence": span(text, a, b), "cv_evidence": evidence, "reason": reason})
    if any(c["state"] != "supported_wording" for c in claims):
        suggestions.append("For each claimed outcome, explain the actual baseline, result and timeframe if known. Use genuine figures only; a qualitative outcome is valid.")
    if INSTRUCTION_LIKE.search(text):
        missing.append("Instruction-like answer lines were treated as data and excluded from structural/evidence checks.")
    return {"version": FEEDBACK_VERSION, "question_kind": question["kind"], "word_count": len(tokens),
            "star": structure, "missing_detail": missing, "claims": claims,
            "clarity": {"long_sentences": long_sentences, "vague_wording": vague, "repeated_wording": repeated},
            "suggestions": list(dict.fromkeys(suggestions)), "career_practice": COACHING.get(role_id, COACHING["general"]),
            "cv_availability": cv_availability or ("Approved CV provided" if cv is not None else "No CV linked"), "claims_truncated": total_claims > MAX_CLAIMS,
            "limitations": ["Offline English-language heuristics; labels/mentions do not establish relevance, technical correctness or truth.",
                            "CV corroboration requires specific matching wording; paraphrases and new genuine experiences may be missed.",
                            "No overall score, hiring probability or invented achievement is produced."]}
