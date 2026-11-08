"""Readable CV reports; explicit saves never overwrite an existing file."""

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from .cv_analysis import CATEGORIES, VERSION
from .cv_cli import safe_display


def citation(evidence):
    corrected = "; corrected text" if evidence.corrected else ""
    return (f"[unit {evidence.position}: {safe_display(evidence.reference)}, "
            f"reviewed chars {evidence.start}:{evidence.end}{corrected}]\n"
            f"    CV excerpt: {safe_display(evidence.quote)}")


def format_cv_analysis(analysis):
    lines = ["=== Evidence-based CV Analysis ===", f"CV {analysis.cv_id}: {safe_display(analysis.title)}",
             f"Offline rules version: {VERSION}", f"Generated: {datetime.now(timezone.utc).isoformat()}",
             f"Approved at: {safe_display(analysis.reviewed_at)}", f"Reviewed-text SHA-256: {analysis.source_digest}",
             "Evidence is a CV claim, not independent verification of qualifications or skill.",
             "\nEXPLICITLY SUPPORTED WORDING"]
    for category in CATEGORIES:
        lines.append(f"\n{category.upper()}")
        findings = [f for f in analysis.findings if f.category == category and f.status == "supported"]
        for finding in findings:
            lines.extend([f"- {safe_display(finding.label)}", "  " + citation(finding.evidence)])
        if not findings:
            lines.append("No confidently classified wording found; see unknowns/uncertain interpretations.")
    lines.append("\nUNCERTAIN INTERPRETATIONS (review required)")
    for finding in analysis.findings:
        if finding.status == "uncertain":
            lines.extend([f"- {finding.category}: {safe_display(finding.label)}", "  " + citation(finding.evidence)])
    lines.append("\nIMPROVEMENT SUGGESTIONS (not CV facts)")
    for suggestion in analysis.suggestions:
        lines.append(f"- [{suggestion.origin}] {suggestion.message}")
        if suggestion.evidence:
            lines.append("  " + citation(suggestion.evidence))
    lines.append("\nCANNOT BE DETERMINED")
    lines.extend("- " + safe_display(item) for item in analysis.unknowns)
    lines.append("\nLIMITATIONS AND NOTES")
    lines.extend("- " + safe_display(item) for item in analysis.notes)
    return "\n".join(lines) + "\n"


def save_cv_report(text, path):
    """Publish a complete owner-only report atomically, without replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".cv-analysis-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
