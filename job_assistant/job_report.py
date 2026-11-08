"""Readable, cited comparison report. Export reuses the non-overwriting writer."""

from datetime import datetime, timezone

from .cv_analysis_report import citation
from .cv_cli import safe_display
from .job_requirements import VERSION


def format_comparison(comparison):
    lines = ["=== Explainable Job Comparison ===", f"Rules version: {VERSION}",
             f"Generated: {datetime.now(timezone.utc).isoformat()}",
             f"CV {comparison.cv_id}: {safe_display(comparison.cv_title)}",
             f"CV approved: {safe_display(comparison.cv_reviewed_at)}",
             f"Reviewed CV digest: {comparison.cv_digest}",
             f"Job source: {safe_display(comparison.job_source)}", f"Job-text digest: {comparison.job_digest}",
             "Offline analysis of document claims. No hiring probability or overall suitability score."]
    lines.append("\nREQUIREMENT PRIORITIES")
    for priority in ("essential", "desirable", "unclear"):
        active = [m for m in comparison.matches if m.requirement.priority == priority and m.status != "excluded"]
        lines.append(f"{priority.upper()}: " + (", ".join(f"#{m.requirement.number} {m.requirement.label}" for m in active) or "None detected"))
    for status in ("matched", "missing", "uncertain", "unsupported", "excluded"):
        items = [m for m in comparison.matches if m.status == status]
        lines.append(f"\n{status.upper()} ({len(items)} {'item' if len(items) == 1 else 'items'})")
        if not items:
            lines.append("None.")
        for match in items:
            requirement = match.requirement
            evidence = requirement.evidence
            lines.extend([f"\n#{requirement.number} [{requirement.priority}] {safe_display(requirement.label)}",
                          "  Origin: offline rules.",
                          f"  Reason: {match.reason}",
                          f"  Job [unit {evidence.position}: {safe_display(evidence.reference)}, chars {evidence.start}:{evidence.end}]",
                          "    " + safe_display(evidence.quote)])
            for cv_evidence in match.cv_evidence:
                lines.append("  CV " + citation(cv_evidence))
            if not match.cv_evidence:
                lines.append("  CV evidence: none used to support this result.")
    if comparison.ai_attempted:
        lines.extend(["\nAI ASSISTANCE (supplement; offline conclusions above are unchanged)",
                      f"Requested model: {safe_display(comparison.ai_model)}",
                      "Origin: AI proposal + mandatory deterministic validation (validator version 1.0).",
                      "Verified here means source/citation/rule checks only; qualifications and competence are not independently verified."])
        for status, label in (("matched", "EVIDENCE-VALIDATED MATCHES"), ("missing", "MISSING EVIDENCE"),
                              ("uncertain", "UNCERTAIN INTERPRETATIONS"), ("unsupported", "UNSUPPORTED MODEL CLAIMS / REVIEW ITEMS")):
            items = [item for item in comparison.ai_results if item.status == status]
            lines.append(f"\nAI {label} ({len(items)})")
            for item in items:
                lines.extend([f"#{item.requirement}: {safe_display(item.skill or 'Unresolved criterion')} ({item.kind})",
                              f"  Origin: {item.origin}; proposed={item.proposed_status}; validated={item.status}",
                              "  " + item.reason,
                              f"  Job [unit {item.job_evidence.position}: {safe_display(item.job_evidence.reference)}, chars {item.job_evidence.start}:{item.job_evidence.end}]",
                              "    " + safe_display(item.job_evidence.quote)])
                if item.cv_evidence:
                    lines.append("  CV " + citation(item.cv_evidence))
                else:
                    lines.append("  CV citation: none supplied; no positive match can be established without one.")
        lines.extend("- " + safe_display(note) for note in comparison.ai_notes)
        lines.append("AI coverage is limited to selected items, not the complete job. Offline counts remain unchanged.")
    lines.append("\nLIMITATIONS AND NOTES")
    lines.extend("- " + safe_display(note) for note in comparison.notes)
    return "\n".join(lines) + "\n"
