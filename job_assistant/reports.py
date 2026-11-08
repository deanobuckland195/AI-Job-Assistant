"""Shared presentation and atomic, single-process text report storage."""

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .catalogue import LEARNING_ROADMAPS

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent.parent / "job_analysis.txt"
REPORT_TITLE = "AI Job Assistant - Job Analysis Report"


def learning_plan(analysis):
    if not analysis.detected:
        return "No recognised skills were found; learning gaps cannot be inferred."
    if not analysis.missing:
        return "You already have all the detected skills for this job!"
    lines = []
    for skill in analysis.missing:
        lines.append(f"\n{skill.upper()} Learning Plan:")
        steps = LEARNING_ROADMAPS.get(skill, ["Research beginner tutorials for this skill"])
        lines.extend(f"- {step}" for step in steps)
    return "\n".join(lines)


def recommendation(analysis):
    if analysis.score is None:
        return "No recognised skills detected - unable to calculate a meaningful match score."
    if analysis.score >= 80:
        return "Excellent recognised-skill match - consider applying after reviewing all requirements."
    if analysis.score >= 60:
        return "Good recognised-skill match - consider applying."
    if analysis.score >= 40:
        return "Possible match - review the missing skills."
    return "Low recognised-skill match - review the requirements and your evidence."


def format_analysis(analysis):
    score = "N/A" if analysis.score is None else f"{analysis.score:.0f}%"
    lines = ["=== Your Match Against This Job ===", "\nSkills Detected in Job Description:"]
    lines.extend(f"- {skill}" for skill in analysis.detected)
    if not analysis.detected:
        lines.append("No recognised skills found.")
    lines.append("\nMatching Skills:")
    lines.extend(f"- {skill}" for skill in analysis.matching)
    lines.append("\nMissing Skills:")
    lines.extend(f"- {skill}" for skill in analysis.missing)
    if analysis.detected and not analysis.missing:
        lines.append("No missing recognised skills!")
    elif not analysis.detected:
        lines.append("Unknown - no recognised requirements detected.")
    lines.extend([
        f"\nJob Match Score: {score}",
        "This measures recognised-skill coverage, not hiring probability or overall suitability.",
        "Unrecognised requirements, context and proficiency are not assessed.",
        f"Recommendation: {recommendation(analysis)}",
        "\n=== Personalised Learning Roadmap ===", learning_plan(analysis),
    ])
    return "\n".join(lines)


def save_analysis(analysis, path=DEFAULT_REPORT_PATH, analysis_time=None):
    """Preserve old content and replace atomically only after a complete write.

    OSError and UnicodeError are handled by the CLI. This is not a multi-user
    store: simultaneous writers are unsupported. Never silently replace a
    file that cannot be read or decoded.
    """
    path = Path(path)
    try:
        previous = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        previous = ""
    numbers = [int(n) for n in re.findall(re.escape(REPORT_TITLE) + r" #(\d+)", previous)]
    number = max([previous.count(REPORT_TITLE), *numbers], default=0) + 1
    when = analysis_time or datetime.now()
    report = (f"\n{'=' * 50}\n{REPORT_TITLE} #{number}\n"
              f"Date: {when.strftime('%d %B %Y')}\nTime: {when.strftime('%H:%M')}\n"
              f"{format_analysis(analysis)}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(previous + report)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return number
