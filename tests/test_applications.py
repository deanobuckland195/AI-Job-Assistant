from datetime import date, datetime
import sqlite3

import pytest

from job_assistant import applications as apps, storage

TODAY = date(2026, 11, 8)


def create(connection, **changes):
    return apps.create_application(connection, company="Synthetic Company", role="Apprentice", today=TODAY, **changes)


def test_records_and_initial_history_survive_connection_restart(tmp_path):
    path = tmp_path / "apps.sqlite3"
    with storage.database(path) as connection:
        app_id = create(connection, job_url="https://example.invalid/jobs/1", notes="Synthetic notes", next_action="Prepare application", deadline="2026-11-30")
    with storage.database(path) as connection:
        item = apps.get_application(connection, app_id)
        assert item["status"] == "saved" and item["application_date"] is None
        assert item["notes"] == "Synthetic notes"
        assert item["job_url"] == "https://example.invalid/jobs/1"
        assert len(item["history"]) == 1
        event = item["history"][0]
        assert event["from_status"] is None and event["to_status"] == "saved"
        assert event["changed_at"] == item["created_at"]
        assert datetime.fromisoformat(event["changed_at"]).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("before", apps.STATUSES)
@pytest.mark.parametrize("after", apps.STATUSES)
def test_all_known_status_changes_are_audited_and_same_status_is_noop(tmp_path, before, after):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection, status=before)
        changed = apps.update_application(connection, app_id, {"status": after}, today=TODAY)
        item = apps.get_application(connection, app_id)
        assert item["status"] == after
        assert changed == (before != after)
        assert len(item["history"]) == (2 if before != after else 1)
        if before != after:
            assert item["history"][-1]["from_status"] == before
            assert item["history"][-1]["to_status"] == after


def test_partial_update_and_empty_values_preserve_other_fields(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection, notes="Keep this", deadline="2026-12-01", job_url="https://example.invalid")
        current = apps.get_application(connection, app_id)
        apps.update_application(connection, app_id, {"next_action": "Follow up", "deadline": "", "job_url": ""}, expected_revision=1, today=TODAY)
        changed = apps.get_application(connection, app_id)
        assert changed["notes"] == "Keep this" and changed["deadline"] is None and changed["job_url"] is None
        assert changed["company"] == current["company"] and changed["created_at"] == current["created_at"]
        assert changed["revision"] == 2 and len(changed["history"]) == 1


@pytest.mark.parametrize("field, value", [
    ("company", ""), ("company", "x" * 201), ("role", " \n"), ("notes", "x" * 10001),
    ("next_action", "x" * 1001), ("status", "accepted"), ("company", "Control\x1b[2J"),
    ("application_date", "2026-02-30"), ("application_date", "20261108"), ("deadline", "08/11/2026"),
    ("application_date", "2026-11-09"), ("deadline", "2026-13-01"),
    ("job_url", "javascript:alert(1)"), ("job_url", "file:///private/path"), ("job_url", "https://user:secret@example.invalid"),
    ("job_url", "https://example.invalid:bad"), ("job_url", "https://example.invalid/white space"),
])
def test_invalid_updates_are_rejected_without_partial_changes(tmp_path, field, value):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection)
        before = apps.get_application(connection, app_id)
        with pytest.raises(apps.ApplicationError):
            apps.update_application(connection, app_id, {field: value}, today=TODAY)
        assert apps.get_application(connection, app_id) == before


def test_unknown_update_column_cannot_be_injected(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection)
        with pytest.raises(apps.ApplicationError):
            apps.update_application(connection, app_id, {"status = 'rejected' WHERE 1=1 --": "x"})
        assert apps.get_application(connection, app_id)["status"] == "saved"


def test_dates_allow_unknown_leap_days_and_late_historical_records(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection, status="applied", application_date="2024-02-29", deadline="2024-02-28")
        item = apps.get_application(connection, app_id)
        assert item["application_date"] == "2024-02-29"
        assert any("after the stated deadline" in note for note in apps.date_notes(item, TODAY))
        apps.update_application(connection, app_id, {"application_date": ""}, today=TODAY)
        assert apps.get_application(connection, app_id)["application_date"] is None
        assert any("not recorded" in note for note in apps.date_notes(apps.get_application(connection, app_id), TODAY))


def test_sql_values_and_literal_filters(tmp_path):
    attack = "Robert'); DROP TABLE applications; --"
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = apps.create_application(connection, company=attack, role="100%_Engineer", notes=attack, today=TODAY)
        assert apps.get_application(connection, app_id)["notes"] == attack
        assert len(apps.list_applications(connection, company=attack)) == 1
        assert len(apps.list_applications(connection, role="%_")) == 1
        assert apps.list_applications(connection, company="%") == []
        assert apps.list_applications(connection, company="' OR 1=1 --") == []


def test_filters_deadlines_overdue_missing_dates_and_pagination(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        first = create(connection, deadline="2026-11-01")
        second = create(connection, status="applied", deadline="2026-11-01")
        third = create(connection, deadline="2026-11-08")
        fourth = create(connection)
        assert [r["id"] for r in apps.list_applications(connection, overdue=True, today=TODAY)] == [first]
        assert [r["id"] for r in apps.list_applications(connection, status="applied")] == [second]
        assert [r["id"] for r in apps.list_applications(connection, deadline_before="2026-11-08", deadline_after="2026-11-08")] == [third]
        assert [r["id"] for r in apps.list_applications(connection, limit=1, offset=1)] == [third]
        assert apps.list_applications(connection)[0]["id"] == fourth
        with pytest.raises(apps.ApplicationError):
            apps.list_applications(connection, deadline_before="2020-01-01", deadline_after="2030-01-01")


def test_stale_review_cannot_overwrite_or_delete_newer_record(tmp_path):
    path = tmp_path / "apps.sqlite3"
    with storage.database(path) as connection:
        app_id = create(connection)
        reviewed = apps.get_application(connection, app_id)
    with storage.database(path) as connection:
        apps.update_application(connection, app_id, {"notes": "Newer synthetic edit"}, today=TODAY)
    with storage.database(path) as connection:
        with pytest.raises(apps.ApplicationError, match="changed since review"):
            apps.update_application(connection, app_id, {"status": "rejected"}, expected_revision=reviewed["revision"], today=TODAY)
        with pytest.raises(apps.ApplicationError, match="changed since review"):
            apps.delete_application(connection, app_id, expected_revision=reviewed["revision"])
        assert apps.get_application(connection, app_id)["notes"] == "Newer synthetic edit"


def test_create_history_failure_rolls_back_application(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        connection.execute("CREATE TRIGGER fail_history BEFORE INSERT ON application_status_history BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            create(connection)
        assert apps.list_applications(connection) == []


def test_status_history_failure_rolls_back_status_and_revision(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection)
        original = apps.get_application(connection, app_id)
        connection.execute("CREATE TRIGGER fail_history BEFORE INSERT ON application_status_history BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            apps.update_application(connection, app_id, {"status": "applied"}, today=TODAY)
        assert apps.get_application(connection, app_id) == original


def test_delete_cascades_history_and_does_not_reuse_application_ids(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        first = create(connection)
        apps.update_application(connection, first, {"status": "interviewing"}, today=TODAY)
        apps.delete_application(connection, first)
        assert connection.execute("SELECT COUNT(*) FROM application_status_history").fetchone()[0] == 0
        with pytest.raises(apps.ApplicationError, match="not found"):
            apps.get_application(connection, first)
        assert create(connection) > first


def test_failed_delete_rolls_back_application_and_history(tmp_path):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        app_id = create(connection)
        connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON applications BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            apps.delete_application(connection, app_id)
        assert len(apps.get_application(connection, app_id)["history"]) == 1


@pytest.mark.parametrize("invalid", [0, -1, True, "1 OR 1=1", 10 ** 100])
def test_invalid_ids_fail_predictably(tmp_path, invalid):
    with storage.database(tmp_path / "apps.sqlite3") as connection:
        with pytest.raises(apps.ApplicationError):
            apps.get_application(connection, invalid)


def test_locked_database_does_not_partially_write(tmp_path):
    path = tmp_path / "locked.sqlite3"
    with storage.database(path) as first, storage.database(path) as second:
        second.execute("PRAGMA busy_timeout = 0")
        first.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                create(second)
            assert not second.in_transaction
            assert apps.list_applications(second) == []
        finally:
            first.rollback()
        assert create(second) > 0
