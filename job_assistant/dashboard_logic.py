"""Small presentation helpers; persistence/validation stay in applications.py."""

from datetime import date, timedelta
import os
from pathlib import Path

from . import applications as apps, storage
from .migrations import STATUSES

MAX_ROWS = 10000
ACTIVE = ("applied", "interviewing", "offered")
CLOSED = ("rejected", "withdrawn")


def database_path():
    return Path(os.environ.get("AI_JOB_ASSISTANT_DATABASE", str(storage.DEFAULT_DATABASE))).expanduser()


def overview(connection):
    counts = dict.fromkeys(STATUSES, 0)
    for status, count in connection.execute("SELECT status, COUNT(*) FROM applications GROUP BY status"):
        counts[status] = count
    return {"Total applications": sum(counts.values()), "Saved jobs": counts["saved"],
            "Active applications": sum(counts[s] for s in ACTIVE), "Interviews": counts["interviewing"], "Offers": counts["offered"]}


def action_timing(record, today=None):
    today = today or date.today()
    if record.get("action_completed"):
        return "Completed"
    if record["status"] in CLOSED:
        return "Closed"
    if not record.get("next_action"):
        return "No action"
    due = record.get("follow_up_date")
    if not due:
        return "Unscheduled"
    if due < today.isoformat():
        return "Overdue"
    if due == today.isoformat():
        return "Due today"
    if due <= (today + timedelta(days=7)).isoformat():
        return "Upcoming (7 days)"
    return "Later"


def deadline_timing(record, today=None):
    today = today or date.today()
    if record["status"] in CLOSED:
        return "Closed"
    if record["status"] != "saved":
        return "Submitted"
    deadline = record.get("deadline")
    if not deadline:
        return "No deadline"
    if deadline < today.isoformat():
        return "Overdue"
    if deadline == today.isoformat():
        return "Due today"
    if deadline <= (today + timedelta(days=7)).isoformat():
        return "Upcoming (7 days)"
    return "Later"


def filter_records(rows, search="", statuses=(), timing="All actions", today=None):
    search = search.strip().casefold()
    return [row for row in rows if (not statuses or row["status"] in statuses)
            and (not search or search in " ".join(str(row.get(k) or "") for k in ("company", "role", "next_action")).casefold())
            and (timing == "All actions" or action_timing(row, today) == timing)]


def table_records(rows, today=None):
    return [{"ID": row["id"], "Company": row["company"], "Role": row["role"], "Status": row["status"].title(),
             "Deadline": row["deadline"] or "—", "Deadline state": deadline_timing(row, today),
             "Next action": row["next_action"] or "—", "Follow-up": row.get("follow_up_date") or "—",
             "Action state": action_timing(row, today)} for row in rows]


def load_rows(connection):
    rows = apps.list_applications(connection, limit=MAX_ROWS + 1)
    return rows[:MAX_ROWS], len(rows) > MAX_ROWS


def link_options(connection):
    # Metadata only. Never read CV paragraphs, original extraction or full reports.
    cvs = [dict(row) for row in connection.execute("SELECT id, reviewed_at FROM cvs WHERE reviewed_at != '' ORDER BY id DESC")]
    comparisons = [dict(row) for row in connection.execute("SELECT id, cv_original_id FROM job_comparisons ORDER BY id DESC")]
    return cvs, comparisons
