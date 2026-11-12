from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_assistant import applications as apps, storage
from job_assistant.documents import ExtractedDocument, Segment

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-dashboard.sqlite3"
    monkeypatch.setenv("AI_JOB_ASSISTANT_DATABASE", str(path))
    return path, AppTest.from_file(str(PROJECT / "dashboard.py"), default_timeout=20)


def seed(path, **changes):
    with storage.database(path) as connection:
        return apps.create_application(connection, company="Synthetic Ltd", role="AI Apprentice", **changes)


def button(at, label):
    return next(b for b in at.button if b.label == label)


def by_label(elements, label):
    return next(e for e in elements if e.label == label)


def test_empty_state_and_zero_cards(dashboard):
    path, at = dashboard
    at.run()
    assert not at.exception
    assert [m.value for m in at.metric] == ["0"] * 5
    assert any("next opportunity starts here" in info.value for info in at.info)


def test_create_form_validation_and_success(dashboard):
    path, at = dashboard
    at.run().radio(key="workspace").set_value("Add application").run()
    button(at, "Create application").click().run()
    assert at.error and not at.exception
    at.text_input(key="create_0_company").input("Synthetic Ltd")
    at.text_input(key="create_0_role").input("AI Apprentice")
    at.text_area(key="create_0_next_action").input("Prepare CV")
    at.date_input(key="create_0_follow_up").set_value(date.today() + timedelta(days=3))
    button(at, "Create application").click().run()
    assert not at.exception and at.success
    assert at.metric[0].value == "1"
    with storage.database(path) as connection:
        row = apps.get_application(connection, 1)
        assert row["next_action"] == "Prepare CV" and row["follow_up_date"]
    assert at.text_input(key="create_1_company").value == ""  # Submission cannot silently duplicate a record.


def test_search_status_and_followup_filters(dashboard):
    path, at = dashboard
    seed(path, next_action="Prepare", follow_up_date=(date.today() - timedelta(days=1)).isoformat())
    with storage.database(path) as connection:
        apps.create_application(connection, company="Other Company", role="Engineer", status="offered")
    at.run()
    assert len(at.dataframe[0].value) == 2
    at.text_input(key="search").input("Synthetic").run()
    assert len(at.dataframe[0].value) == 1
    at.multiselect(key="status_filter").set_value(["offered"]).run()
    assert not at.dataframe and any("No applications match" in x.value for x in at.info)
    at.multiselect(key="status_filter").set_value([])
    at.text_input(key="search").input("")
    at.selectbox(key="timing_filter").set_value("Overdue").run()
    assert len(at.dataframe[0].value) == 1


def test_edit_status_notes_and_history(dashboard):
    path, at = dashboard
    app_id = seed(path)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    at.selectbox(key="edit_1_1_status").set_value("interviewing")
    at.text_area(key="edit_1_1_notes").input("Synthetic interview notes")
    button(at, "Save changes").click().run()
    assert not at.exception
    with storage.database(path) as connection:
        row = apps.get_application(connection, app_id)
        assert row["status"] == "interviewing" and row["notes"] == "Synthetic interview notes"
        assert len(row["history"]) == 2


def test_mark_complete_then_reopen(dashboard):
    path, at = dashboard
    app_id = seed(path, next_action="Follow up", follow_up_date=(date.today() - timedelta(days=1)).isoformat())
    at.run().selectbox(key="open_application").set_value(app_id).run()
    button(at, "Mark action complete").click().run()
    assert not at.exception
    assert "Completed" in at.dataframe[0].value["Action state"].tolist()
    button(at, "Reopen action").click().run()
    assert "Overdue" in at.dataframe[0].value["Action state"].tolist()


def test_delete_requires_review_acknowledgement_and_confirmation(dashboard):
    path, at = dashboard
    app_id = seed(path)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    button(at, "Review deletion").click().run()
    assert button(at, "Confirm deletion").disabled
    button(at, "Cancel deletion").click().run()
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)
    button(at, "Review deletion").click().run()
    assert not at.checkbox(key="confirm_delete_1").value
    at.checkbox(key="confirm_delete_1").check().run()
    button(at, "Confirm deletion").click().run()
    assert not at.exception and at.metric[0].value == "0"
    with storage.database(path) as connection:
        assert apps.list_applications(connection) == []


def test_stale_form_cannot_overwrite_a_cli_edit(dashboard):
    path, at = dashboard
    app_id = seed(path)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    with storage.database(path) as connection:
        apps.update_application(connection, app_id, {"notes": "Newer CLI edit"})
    at.text_area(key="edit_1_1_notes").input("Stale browser draft")
    button(at, "Save changes").click().run()
    assert not at.exception
    assert any("changed since review" in e.value for e in at.error)
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)["notes"] == "Newer CLI edit"
    button(at, "Reload record").click().run()
    assert at.text_area(key="edit_1_2_notes").value == "Newer CLI edit"


def test_detail_shows_link_metadata_without_cv_passages(dashboard, monkeypatch):
    path, at = dashboard
    with storage.database(path) as connection:
        profile = storage.create_profile(connection, "PRIVATE_CV_NAME", [])
        document = ExtractedDocument("synthetic.txt", "txt", 30, "a" * 64, "fixture", [Segment("page 1", "PRIVATE_CV_PASSAGE", "PRIVATE_CV_PASSAGE")])
        cv_id = storage.save_cv(connection, profile, "PRIVATE_CV_TITLE", document)
        app_id = apps.create_application(connection, company="Synthetic", role="Role", cv_id=cv_id)
    monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("Dashboard must not load CV contents"))
    at.run().selectbox(key="open_application").set_value(app_id).run()
    assert not at.exception
    shown = str(at)
    assert "PRIVATE_CV_PASSAGE" not in shown and "PRIVATE_CV_NAME" not in shown and "PRIVATE_CV_TITLE" not in shown
    assert any("CV version #1" in text.value for text in at.text)


def test_database_error_is_friendly_without_private_details(dashboard, monkeypatch):
    path, at = dashboard
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXCEPTION_MARKER")
    monkeypatch.setattr(storage, "database", fail)
    at.run()
    assert not at.exception
    assert any("database is unavailable" in error.value for error in at.error)
    assert "PRIVATE_EXCEPTION_MARKER" not in str(at)


def test_replacing_links_requires_explicit_mode_and_keeps_by_default(dashboard):
    path, at = dashboard
    with storage.database(path) as connection:
        profile = storage.create_profile(connection, "Synthetic", [])
        document = ExtractedDocument("synthetic.txt", "txt", 6, "a" * 64, "fixture", [Segment("page 1", "Python", "Python")])
        cv_id = storage.save_cv(connection, profile, "Synthetic CV", document)
        app_id = apps.create_application(connection, company="Synthetic", role="Role", cv_id=cv_id)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    at.text_area(key="edit_1_1_notes").input("Keep this link")
    button(at, "Save changes").click().run()
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)["cv_id"] == cv_id
    at.selectbox(key="edit_1_2_link_mode").set_value("Clear links")
    button(at, "Save changes").click().run()
    assert not at.exception
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)["cv_id"] is None


def test_new_action_reopens_completed_task_in_edit_form(dashboard):
    path, at = dashboard
    app_id = seed(path, next_action="Old action", action_completed=True)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    at.text_area(key="edit_1_1_next_action").input("New next action")
    button(at, "Save changes").click().run()
    assert not at.exception
    with storage.database(path) as connection:
        row = apps.get_application(connection, app_id)
        assert row["action_completed"] is False and row["action_completed_at"] is None


def test_future_application_date_validation_in_form(dashboard):
    path, at = dashboard
    at.run().radio(key="workspace").set_value("Add application").run()
    at.text_input(key="create_0_company").input("Synthetic")
    at.text_input(key="create_0_role").input("Role")
    at.date_input(key="create_0_application_date").set_value(date.today() + timedelta(days=1))
    button(at, "Create application").click().run()
    assert not at.exception
    assert any("future" in error.value for error in at.error)
    with storage.database(path) as connection:
        assert apps.list_applications(connection) == []


def test_stale_delete_does_not_remove_updated_record(dashboard):
    path, at = dashboard
    app_id = seed(path)
    at.run().selectbox(key="open_application").set_value(app_id).run()
    button(at, "Review deletion").click().run()
    with storage.database(path) as connection:
        apps.update_application(connection, app_id, {"notes": "CLI updated"})
    at.checkbox(key="confirm_delete_1").check().run()
    button(at, "Confirm deletion").click().run()
    assert not at.exception
    assert any("changed since review" in error.value for error in at.error)
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)["notes"] == "CLI updated"


def test_card_management_opens_existing_record_without_writing(dashboard):
    path, at = dashboard
    app_id = seed(path, application_date=date.today().isoformat(), next_action="Prepare project")
    with storage.database(path) as connection:
        before = list(connection.iterdump())
    at.run()
    assert any(c.value == "Applied · " + date.today().isoformat() for c in at.caption)
    assert any(c.value == "Deadline · Not set" for c in at.caption)
    button(at, "View & manage").click().run()
    assert not at.exception
    assert at.selectbox(key="open_application").value == app_id
    assert at.text_input(key="edit_1_1_company").value == "Synthetic Ltd"
    with storage.database(path) as connection:
        assert list(connection.iterdump()) == before


@pytest.mark.parametrize("key, route, form_label", [
    ("hero_add_application", "Add application", "Company *"),
    ("hero_interview_practice", "Interview Practice", "Session title"),
])
def test_hero_actions_open_existing_workflows_without_writing(dashboard, key, route, form_label):
    path, at = dashboard
    seed(path)
    with storage.database(path) as connection:
        before = list(connection.iterdump())
    at.run()
    assert any(t.value == "Your career, moving forward." for t in at.title)
    at.button(key=key).click().run()
    assert not at.exception
    assert at.radio(key="workspace").value == route
    assert any(field.label == form_label for field in at.text_input)
    with storage.database(path) as connection:
        assert list(connection.iterdump()) == before


def test_dashboard_overview_uses_saved_status_counts_and_is_read_only(dashboard):
    path, at = dashboard
    for status in ("saved", "applied", "interviewing", "offered", "rejected", "withdrawn"):
        seed(path, status=status)
    with storage.database(path) as connection:
        before = list(connection.iterdump())
    at.run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric} == {
        "Total applications": "6", "Saved jobs": "1", "Active applications": "3",
        "Interviews": "1", "Offers": "1",
    }
    assert {tab.label for tab in at.tabs} >= {"Application cards", "Table view"}
    assert any(field.label == "Search applications" for field in at.text_input)
    with storage.database(path) as connection:
        assert list(connection.iterdump()) == before
