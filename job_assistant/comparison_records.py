"""Comparison provenance only: never persist CV/job excerpts in these records."""

from collections import Counter
import json
import re

from . import storage
from .applications import ApplicationError, positive_id, write_transaction
from .cv_analysis import analyse_cv
from .job_requirements import VERSION


def save_comparison(connection, comparison):
    with write_transaction(connection):
        cv = storage.get_cv(connection, comparison.cv_id)
        analysis = analyse_cv(cv)
        if analysis.source_digest != comparison.cv_digest or analysis.reviewed_at != comparison.cv_reviewed_at:
            raise ApplicationError("The approved CV changed since comparison. Re-run comparison before storing metadata.")
        counts = Counter(match.status for match in comparison.matches)
        if (set(counts) - {"matched", "missing", "uncertain", "unsupported", "excluded"} or
                not 1 <= sum(counts.values()) <= 100 or not re.fullmatch(r"[0-9a-f]{64}", comparison.job_digest)):
            raise ApplicationError("Invalid comparison summary.")
        model = comparison.ai_model if re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", comparison.ai_model or "") else None
        cursor = connection.execute("""INSERT INTO job_comparisons
            (cv_id, cv_original_id, cv_reviewed_at, cv_digest, job_digest, rules_version,
             counts_json, ai_attempted, ai_model, ai_item_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (comparison.cv_id, comparison.cv_id, comparison.cv_reviewed_at, comparison.cv_digest,
             comparison.job_digest, VERSION, json.dumps(counts, sort_keys=True), int(comparison.ai_attempted),
             model, len(comparison.ai_results), storage.timestamp()))
        connection.execute("INSERT INTO comparison_skill_snapshots(comparison_id,snapshot_json) VALUES (?,?)",
                           (cursor.lastrowid, json.dumps(validate_skill_snapshot(skill_snapshot(comparison)), sort_keys=True)))
    return cursor.lastrowid


def get_comparison(connection, comparison_id):
    positive_id(comparison_id, "Comparison")
    row = connection.execute("SELECT * FROM job_comparisons WHERE id = ?", (comparison_id,)).fetchone()
    if row is None:
        raise ApplicationError("Stored comparison not found. Run job-compare --store to create one.")
    result = dict(row)
    result["counts"] = storage.decode_json(result.pop("counts_json"))
    return result


def list_comparisons(connection, limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 9223372036854775807:
        raise ApplicationError("Use a comparison limit from 1 to 1,000 and a non-negative offset.")
    return [dict(row) for row in connection.execute("SELECT id, cv_id, cv_original_id, created_at FROM job_comparisons ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))]


def delete_comparison(connection, comparison_id):
    with write_transaction(connection):
        get_comparison(connection, comparison_id)
        connection.execute("DELETE FROM job_comparisons WHERE id = ?", (comparison_id,))


def skill_snapshot(comparison):
    """Only recognised terms, statuses and source coordinates; never source excerpts."""
    return [{"number": m.requirement.number, "terms": list(m.requirement.terms),
             "status": m.status, "priority": m.requirement.priority,
             "alternative": m.requirement.alternative, "qualified": bool(m.requirement.qualifiers),
             "job_position": m.requirement.evidence.position,
             "job_start": m.requirement.evidence.start, "job_end": m.requirement.evidence.end,
             "cv_spans": [{"position": e.position, "start": e.start, "end": e.end} for e in m.cv_evidence]}
            for m in comparison.matches]


def get_skill_snapshot(connection, comparison_id):
    comparison = get_comparison(connection, comparison_id)
    row = connection.execute("SELECT snapshot_json FROM comparison_skill_snapshots WHERE comparison_id = ?", (comparison_id,)).fetchone()
    return comparison, validate_skill_snapshot(storage.decode_json(row[0])) if row else None


def validate_skill_snapshot(snapshot):
    """Reject corrupt metadata rather than promote counts or unknown text to skills."""
    from .job_requirements import TERMS
    fields = {"number", "terms", "status", "priority", "alternative", "qualified", "job_position", "job_start", "job_end", "cv_spans"}
    valid_terms = set(TERMS.values())
    if not isinstance(snapshot, list) or len(snapshot) > 100:
        raise storage.StorageError("Stored comparison skill metadata is invalid.")
    for item in snapshot:
        if (not isinstance(item, dict) or set(item) != fields or
                not isinstance(item["terms"], list) or len(item["terms"]) > 100 or
                any(not isinstance(t, str) or t not in valid_terms for t in item["terms"]) or
                not isinstance(item["status"], str) or item["status"] not in {"matched", "missing", "uncertain", "unsupported", "excluded"} or
                not isinstance(item["priority"], str) or item["priority"] not in {"essential", "desirable", "unclear"} or
                type(item["alternative"]) is not bool or type(item["qualified"]) is not bool or
                any(type(item[k]) is not int or item[k] < (0 if k == "job_start" else 1) for k in ("number", "job_position", "job_start", "job_end")) or
                item["job_start"] >= item["job_end"] or not isinstance(item["cv_spans"], list)):
            raise storage.StorageError("Stored comparison skill metadata is invalid.")
        for span in item["cv_spans"]:
            if (not isinstance(span, dict) or set(span) != {"position", "start", "end"} or
                    any(type(span[k]) is not int or span[k] < (0 if k == "start" else 1) for k in span) or span["start"] >= span["end"]):
                raise storage.StorageError("Stored comparison skill metadata is invalid.")
    return snapshot
