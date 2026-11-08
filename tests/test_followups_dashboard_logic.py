from datetime import date
import json
import sqlite3

import pytest

from job_assistant import applications as apps, dashboard_logic as logic, migrations, storage
from job_assistant.application_export import export_applications

TODAY = date(2026, 11, 8)


def record(**changes):
    return {"id": 1, "company": "Synthetic", "role": "Apprentice", "status": "saved", "deadline": None,
            "next_action": "Prepare application", "follow_up_date": None, "action_completed": False, **changes}


@pytest.mark.parametrize("changes, expected", [
    ({}, "Unscheduled"), ({"next_action": ""}, "No action"),
    ({"follow_up_date": "2026-11-07"}, "Overdue"), ({"follow_up_date": "2026-11-08"}, "Due today"),
    ({"follow_up_date": "2026-11-15"}, "Upcoming (7 days)"), ({"follow_up_date": "2026-11-16"}, "Later"),
    ({"follow_up_date": "2026-11-01", "action_completed": True}, "Completed"),
    ({"status": "rejected", "follow_up_date": "2026-11-01"}, "Closed"),
    ({"status": "offered", "follow_up_date": "2026-11-01"}, "Overdue"),
])
def test_action_timing(changes, expected):
    assert logic.action_timing(record(**changes), TODAY) == expected


@pytest.mark.parametrize("status, expected", [("saved", "Overdue"), ("applied", "Submitted"),
                                                ("interviewing", "Submitted"), ("offered", "Submitted"),
                                                ("rejected", "Closed"), ("withdrawn", "Closed")])
def test_application_deadline_not_confused_with_followup(status, expected):
    assert logic.deadline_timing(record(status=status, deadline="2026-01-01"), TODAY) == expected


def test_filters_casefold_search_and_table_privacy():
    rows = [record(company="Straße GmbH", notes="PRIVATE_NOTES"), record(id=2, status="applied", next_action="Ask for feedback")]
    assert logic.filter_records(rows, "STRASSE")[0]["id"] == 1
    assert logic.filter_records(rows, "feedback", ["applied"])[0]["id"] == 2
    assert logic.filter_records(rows, statuses=["offered"]) == []
    assert "PRIVATE_NOTES" not in str(logic.table_records(rows, TODAY))


def test_cards_cover_all_statuses_and_closed_records_not_active(tmp_path):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        for status in apps.STATUSES:
            apps.create_application(connection, company="Synthetic", role="Role", status=status)
        counts = logic.overview(connection)
        assert counts == {"Total applications": 6, "Saved jobs": 1, "Active applications": 3, "Interviews": 1, "Offers": 1}


def test_action_completion_persists_and_new_action_reopens(tmp_path):
    path = tmp_path / "test.sqlite3"
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Synthetic", role="Role", next_action="Follow up", follow_up_date="2026-11-01")
        apps.update_application(connection, app_id, {"action_completed": True})
        first = apps.get_application(connection, app_id)
        assert first["action_completed"] is True and first["action_completed_at"]
        apps.update_application(connection, app_id, {"notes": "Notes changed"})
        assert apps.get_application(connection, app_id)["action_completed_at"] == first["action_completed_at"]
    with storage.database(path) as connection:
        assert logic.action_timing(apps.get_application(connection, app_id), TODAY) == "Completed"
        apps.update_application(connection, app_id, {"next_action": "Prepare interview"})
        item = apps.get_application(connection, app_id)
        assert item["action_completed"] is False and item["action_completed_at"] is None
        assert len(item["history"]) == 1  # No invented application-status transition.
        exported = json.loads(export_applications(connection))["applications"][0]
        assert exported["action_completed"] is False and exported["follow_up_date"] == "2026-11-01"


@pytest.mark.parametrize("changes", [{"follow_up_date": "not-a-date"}, {"follow_up_date": "2026-02-30"},
                                     {"action_completed": "yes"}, {"action_completed": 2}])
def test_invalid_followups_and_completion_are_rejected(tmp_path, changes):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        app_id = apps.create_application(connection, company="Synthetic", role="Role", next_action="Follow up")
        before = apps.get_application(connection, app_id)
        with pytest.raises(apps.ApplicationError):
            apps.update_application(connection, app_id, changes)
        assert apps.get_application(connection, app_id) == before


def test_no_due_or_completed_empty_action(tmp_path):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        for changes in ({"follow_up_date": "2026-11-01"}, {"action_completed": True}):
            with pytest.raises(apps.ApplicationError, match="next action"):
                apps.create_application(connection, company="Synthetic", role="Role", **changes)


def make_v2(path):
    with sqlite3.connect(path) as connection:
        migrations.create_v1(connection)
        migrations.migrate_v1_to_v2(connection)
        connection.execute(f"PRAGMA application_id = {storage.APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 2")
        connection.execute("INSERT INTO applications(id,company,role,status,next_action,notes,created_at,updated_at) VALUES (5,'Synthetic','Role','applied','Follow up','Private notes','2020-01-01','2020-01-01')")
        connection.execute("INSERT INTO application_status_history(application_id,from_status,to_status,changed_at) VALUES (5,NULL,'applied','2020-01-01')")


def test_v2_to_v3_keeps_original_application_history_and_defaults(tmp_path):
    path = tmp_path / "v2.sqlite3"
    make_v2(path)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM applications").fetchall()
        history = connection.execute("SELECT * FROM application_status_history").fetchall()
    with storage.database(path) as connection:
        after = [tuple(row) for row in connection.execute("SELECT * FROM applications")]
        assert after[0][:-3] == before[0]
        assert after[0][-3:] == (None, 0, None)
        assert [tuple(row) for row in connection.execute("SELECT * FROM application_status_history")] == history
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION


def test_v2_to_v3_failure_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "v2.sqlite3"
    make_v2(path)
    original = migrations.migrate_v2_to_v3
    def fail(connection):
        original(connection)
        raise sqlite3.OperationalError("Synthetic upgrade failure")
    monkeypatch.setattr(migrations, "migrate_v2_to_v3", fail)
    with pytest.raises(sqlite3.Error):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "follow_up_date" not in {row[1] for row in connection.execute("PRAGMA table_info(applications)")}
        assert connection.execute("SELECT notes FROM applications").fetchone()[0] == "Private notes"


def test_cli_followup_flags_share_business_logic(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    project = Path(__file__).resolve().parents[1]
    path = tmp_path / "cli.sqlite3"
    base = [sys.executable, "-B", str(project / "main.py"), "--database", str(path)]
    created = subprocess.run(base + ["application-create", "--company", "Synthetic", "--role", "Role", "--next-action", "Follow up", "--follow-up-date", "2026-11-01"], input="yes\n", text=True, capture_output=True)
    assert created.returncode == 0, created.stdout + created.stderr
    completed = subprocess.run(base + ["application-update", "1", "--complete-action"], input="yes\n", text=True, capture_output=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    with storage.database(path) as connection:
        assert apps.get_application(connection, 1)["action_completed"] is True
