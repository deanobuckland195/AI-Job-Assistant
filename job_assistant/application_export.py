"""Privacy-minimising JSON export; never join or read CV source text."""

import json

from . import storage
from .applications import ApplicationError, get_application, list_applications

EXPORT_FIELDS = ("id", "company", "role", "job_url", "application_date", "status", "deadline", "next_action",
                 "follow_up_date", "action_completed", "action_completed_at",
                 "cv_id", "cv_original_id", "comparison_id", "comparison_original_id", "created_at", "updated_at", "revision")


def export_applications(connection, *, include_notes=False, include_history=False, **filters):
    connection.execute("BEGIN")
    try:
        text = export_snapshot(connection, include_notes=include_notes, include_history=include_history, **filters)
        connection.commit()
        return text
    except BaseException:
        connection.rollback()
        raise


def export_snapshot(connection, *, include_notes=False, include_history=False, **filters):
    rows = list_applications(connection, limit=10001, **filters)
    if len(rows) > 10000:
        raise ApplicationError("Export exceeds 10,000 applications. Narrow the filters and export separate files.")
    exported = []
    for row in rows:
        item = {field: row[field] for field in EXPORT_FIELDS}
        item["action_completed"] = bool(item["action_completed"])
        if include_notes:
            item["notes"] = row["notes"]
        if include_history:
            item["history"] = get_application(connection, row["id"])["history"]
        exported.append(item)
    return json.dumps({"format_version": 1, "exported_at": storage.timestamp(), "applications": exported},
                      ensure_ascii=True, indent=2) + "\n"
