"""Validated local application records and transactional status history."""

from contextlib import contextmanager
from datetime import date
import re
from urllib.parse import urlsplit

from . import storage
from .cv_analysis import analyse_cv
from .migrations import STATUSES

FIELDS = ("company", "role", "job_url", "application_date", "status", "deadline", "notes", "next_action", "follow_up_date", "action_completed")
LINK_FIELDS = ("cv_id", "cv_original_id", "cv_reviewed_at", "cv_digest", "comparison_id", "comparison_original_id", "comparison_job_digest")


class ApplicationError(ValueError):
    """A safe validation or concurrency error without personal field values."""


@contextmanager
def write_transaction(connection):
    """Lock before reading, so updates/history/deletion share one transaction."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def text_field(value, label, maximum, required=False, multiline=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ApplicationError(f"{label} must be text.")
    value = value.strip()
    if (len(value) > maximum or (required and not value) or
            any(not c.isprintable() and not (multiline and c in "\n\r\t") for c in value)):
        raise ApplicationError(f"{label} must contain {'1' if required else '0'}–{maximum} characters without unsupported controls.")
    return value


def iso_date(value, label):
    if value is None or value == "":
        return None
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        date.fromisoformat(value)
        return value
    except ValueError:
        raise ApplicationError(f"{label} must be a real date in YYYY-MM-DD format, or omitted.") from None


def job_url(value):
    if value is None or value == "":
        return None
    value = text_field(value, "Job URL", 2048)
    try:
        url = urlsplit(value)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or
                url.password is not None or any(c.isspace() for c in value) or "\\" in value):
            raise ValueError
        _ = url.port
    except ValueError:
        raise ApplicationError("Job URL must be an HTTP(S) URL with a host, no credentials, whitespace or backslashes.") from None
    return value


def validate_fields(values, today=None):
    today = today or date.today()
    result = {
        "company": text_field(values.get("company"), "Company", 200, required=True),
        "role": text_field(values.get("role"), "Role", 200, required=True),
        "job_url": job_url(values.get("job_url")),
        "application_date": iso_date(values.get("application_date"), "Application date"),
        "deadline": iso_date(values.get("deadline"), "Deadline"),
        "notes": text_field(values.get("notes", ""), "Notes", 10000, multiline=True),
        "next_action": text_field(values.get("next_action", ""), "Next action", 1000, multiline=True),
        "status": values.get("status", "saved"),
        "follow_up_date": iso_date(values.get("follow_up_date"), "Follow-up date"),
        "action_completed": values.get("action_completed", False),
    }
    if type(result["action_completed"]) not in (bool, int) or result["action_completed"] not in (0, 1):
        raise ApplicationError("Action completion must be true or false.")
    result["action_completed"] = bool(result["action_completed"])
    if (result["follow_up_date"] or result["action_completed"]) and not result["next_action"]:
        raise ApplicationError("Add a next action before setting a follow-up date or marking it complete.")
    if result["status"] not in STATUSES:
        raise ApplicationError("Status must be saved, applied, interviewing, offered, rejected or withdrawn.")
    if result["application_date"] and result["application_date"] > today.isoformat():
        raise ApplicationError("Application date cannot be in the future. Use deadline/next action for plans.")
    return result


def date_notes(record, today=None):
    today = today or date.today()
    notes = []
    if not record.get("application_date") and record["status"] != "saved":
        notes.append("Application date is not recorded; no date has been inferred.")
    if record.get("deadline") and record["deadline"] < today.isoformat():
        notes.append("Application deadline has passed" + ("; this item is still saved." if record["status"] == "saved" else "."))
    if record.get("application_date") and record.get("deadline") and record["application_date"] > record["deadline"]:
        notes.append("Application date is after the stated deadline; historical/late records are allowed.")
    return notes


def positive_id(value, label):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ApplicationError(f"{label} must be a positive integer ID.")
    return value


def resolve_links(connection, cv_id=None, comparison_id=None):
    """A link update replaces the link set; no document text is copied."""
    result = dict.fromkeys(LINK_FIELDS)
    comparison = None
    if comparison_id is not None:
        from .comparison_records import get_comparison
        comparison = get_comparison(connection, positive_id(comparison_id, "Comparison"))
        result.update(comparison_id=comparison_id, comparison_original_id=comparison_id,
                      comparison_job_digest=comparison["job_digest"])
        if cv_id is None:
            cv_id = comparison["cv_id"]
            result.update(cv_original_id=comparison["cv_original_id"], cv_reviewed_at=comparison["cv_reviewed_at"], cv_digest=comparison["cv_digest"])
    if cv_id is not None:
        cv = storage.get_cv(connection, positive_id(cv_id, "CV"))
        analysis = analyse_cv(cv)
        if comparison and (comparison["cv_original_id"] != cv_id or comparison["cv_digest"] != analysis.source_digest or comparison["cv_reviewed_at"] != analysis.reviewed_at):
            raise ApplicationError("The comparison does not refer to this approved CV version.")
        result.update(cv_id=cv_id, cv_original_id=cv_id, cv_reviewed_at=analysis.reviewed_at, cv_digest=analysis.source_digest)
    return result


def create_application(connection, *, company, role, job_url=None, application_date=None,
                       status="saved", deadline=None, notes="", next_action="",
                       cv_id=None, comparison_id=None, today=None, expected_links=None,
                       follow_up_date=None, action_completed=False):
    values = validate_fields(dict(company=company, role=role, job_url=job_url, application_date=application_date,
                                  status=status, deadline=deadline, notes=notes, next_action=next_action,
                                  follow_up_date=follow_up_date, action_completed=action_completed), today)
    with write_transaction(connection):
        values.update(resolve_links(connection, cv_id, comparison_id))
        if expected_links is not None and any(values[key] != expected_links[key] for key in LINK_FIELDS):
            raise ApplicationError("CV/comparison links changed since review. Review again before saving.")
        when = storage.timestamp()
        values.update(created_at=when, updated_at=when, revision=1)
        values["action_completed_at"] = when if values["action_completed"] else None
        columns = list(values)  # Keys come only from validated fixed field dictionaries.
        cursor = connection.execute(f"INSERT INTO applications ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(values.values()))
        app_id = cursor.lastrowid
        connection.execute("INSERT INTO application_status_history(application_id, from_status, to_status, changed_at) VALUES (?, NULL, ?, ?)",
                           (app_id, values["status"], when))
    return app_id


def get_application(connection, app_id, include_history=True):
    positive_id(app_id, "Application")
    row = connection.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if row is None:
        raise ApplicationError("Application not found. Use application-list to find an existing ID.")
    result = dict(row)
    result["action_completed"] = bool(result["action_completed"])
    if include_history:
        result["history"] = [dict(event) for event in connection.execute(
            "SELECT id, from_status, to_status, changed_at FROM application_status_history WHERE application_id = ? ORDER BY id", (app_id,))]
    return result


def check_revision(current, expected_revision):
    if expected_revision is not None and (type(expected_revision) is not int or current["revision"] != expected_revision):
        raise ApplicationError("Application changed since review. View it again before updating or deleting.")


def prepare_update(current, changes, today=None):
    changes = dict(changes)
    if "next_action" in changes and "action_completed" not in changes:
        action = text_field(changes["next_action"], "Next action", 1000, multiline=True)
        if action != current["next_action"]:
            changes["action_completed"] = False
    return validate_fields({**current, **changes}, today)


def update_application(connection, app_id, changes, *, links=None, expected_revision=None, today=None, expected_links=None):
    if not isinstance(changes, dict) or set(changes) - set(FIELDS):
        raise ApplicationError("Unsupported application update field.")
    if links is not None and (not isinstance(links, dict) or set(links) - {"cv_id", "comparison_id"}):
        raise ApplicationError("Unsupported application link field.")
    with write_transaction(connection):
        current = get_application(connection, app_id, include_history=False)
        check_revision(current, expected_revision)
        values = prepare_update(current, changes, today)
        if links is not None:
            values.update(resolve_links(connection, **links))
            if expected_links is not None and any(values[key] != expected_links[key] for key in LINK_FIELDS):
                raise ApplicationError("CV/comparison links changed since review. Review again before saving.")
        actual = {key: value for key, value in values.items() if value != current[key]}
        if not actual:
            return False
        when = storage.timestamp()
        actual["action_completed_at"] = ((current["action_completed_at"] or when) if values["action_completed"] else None)
        actual.update(updated_at=when, revision=current["revision"] + 1)
        assignments = ",".join(f"{key} = ?" for key in actual)
        connection.execute(f"UPDATE applications SET {assignments} WHERE id = ?", (*actual.values(), app_id))
        if values["status"] != current["status"]:
            connection.execute("INSERT INTO application_status_history(application_id, from_status, to_status, changed_at) VALUES (?, ?, ?, ?)",
                               (app_id, current["status"], values["status"], when))
    return True


def delete_application(connection, app_id, *, expected_revision=None):
    with write_transaction(connection):
        current = get_application(connection, app_id, include_history=False)
        check_revision(current, expected_revision)
        connection.execute("DELETE FROM applications WHERE id = ?", (app_id,))


def list_applications(connection, *, status=None, company=None, role=None, deadline_before=None,
                      deadline_after=None, overdue=False, limit=100, offset=0, today=None):
    if type(limit) is not int or not 1 <= limit <= 10001 or type(offset) is not int or not 0 <= offset <= 9223372036854775807:
        raise ApplicationError("Use a limit from 1 to 10,001 and a non-negative offset.")
    conditions, values = [], []
    if status is not None:
        if status not in STATUSES:
            raise ApplicationError("Unknown application status filter.")
        conditions.append("status = ?")
        values.append(status)
    for column, value in (("company", company), ("role", role)):
        if value is not None:
            value = text_field(value, "Search text", 200)
            value = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(f"{column} LIKE ? ESCAPE '\\'")
            values.append(f"%{value}%")
    before, after = iso_date(deadline_before, "Deadline-before"), iso_date(deadline_after, "Deadline-after")
    if before and after and after > before:
        raise ApplicationError("Deadline-after cannot be later than deadline-before.")
    for operator, value in (("<=", before), (">=", after)):
        if value:
            conditions.append(f"deadline {operator} ?")
            values.append(value)
    if overdue:
        conditions.append("status = 'saved' AND deadline < ?")
        values.append((today or date.today()).isoformat())
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return [dict(row) for row in connection.execute("SELECT * FROM applications" + where + " ORDER BY id DESC LIMIT ? OFFSET ?", (*values, limit, offset))]
