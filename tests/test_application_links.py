import json

import pytest

from job_assistant import applications as apps, comparison_records as records, storage
from job_assistant.application_export import export_applications
from job_assistant.documents import ExtractedDocument, Segment
from job_assistant.job_matching import compare_job
from job_assistant.job_requirements import job_from_text


@pytest.fixture
def linked_store(tmp_path):
    path = tmp_path / "links.sqlite3"
    with storage.database(path) as connection:
        profile = storage.create_profile(connection, "SYNTHETIC_PRIVATE_NAME", [])
        document = ExtractedDocument("synthetic.txt", "txt", 30, "a" * 64, "fixture", [
            Segment("page 1", "SYNTHETIC_ORIGINAL_PRIVATE_TEXT", "Skills: Python\nSYNTHETIC_REVIEWED_PRIVATE_TEXT")])
        cv_id = storage.save_cv(connection, profile, "SYNTHETIC_PRIVATE_TITLE", document)
        comparison = compare_job(storage.get_cv(connection, cv_id), job_from_text("Python required"))
        comparison_id = records.save_comparison(connection, comparison)
    return path, cv_id, comparison_id


def test_comparison_provenance_persisted_without_excerpts(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        row = records.get_comparison(connection, comparison_id)
        assert row["cv_id"] == cv_id and row["counts"] == {"matched": 1}
        assert len(row["cv_digest"]) == len(row["job_digest"]) == 64
        serialised = json.dumps(row)
        assert "PRIVATE" not in serialised and "Python" not in serialised
        assert len(records.list_comparisons(connection)) == 1


def test_application_auto_links_comparison_cv_and_keeps_version_fingerprint(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        app = apps.get_application(connection, app_id)
        comparison = records.get_comparison(connection, comparison_id)
        assert app["cv_id"] == cv_id
        assert app["cv_digest"] == comparison["cv_digest"]
        assert app["cv_reviewed_at"] == comparison["cv_reviewed_at"]
        assert app["comparison_job_digest"] == comparison["job_digest"]
        assert "PRIVATE" not in json.dumps(app)


def test_incompatible_cv_and_unapproved_cv_do_not_create_applications(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        document = ExtractedDocument("another.txt", "txt", 10, "b" * 64, "fixture", [Segment("line 1", "SQL", "SQL")])
        other = storage.save_cv(connection, 1, "Another CV", document)
        with pytest.raises(apps.ApplicationError, match="does not refer"):
            apps.create_application(connection, company="Demo", role="Role", cv_id=other, comparison_id=comparison_id)
        connection.execute("UPDATE cvs SET reviewed_at = '' WHERE id = ?", (cv_id,))
        connection.commit()
        from job_assistant.cv_analysis import AnalysisError
        with pytest.raises(AnalysisError, match="approved"):
            apps.create_application(connection, company="Demo", role="Role", cv_id=cv_id)
        assert apps.list_applications(connection) == []


def test_deleted_cv_and_comparison_detach_without_deleting_application(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        original = apps.get_application(connection, app_id)
        storage.delete_cv(connection, cv_id)
        current = apps.get_application(connection, app_id)
        assert current["cv_id"] is None and current["cv_original_id"] == cv_id
        assert current["cv_digest"] == original["cv_digest"]
        assert records.get_comparison(connection, comparison_id)["cv_id"] is None
        historical = apps.create_application(connection, company="Demo historical", role="Role", comparison_id=comparison_id)
        assert apps.get_application(connection, historical)["cv_digest"] == original["cv_digest"]
        records.delete_comparison(connection, comparison_id)
        current = apps.get_application(connection, app_id)
        assert current["comparison_id"] is None and current["comparison_original_id"] == comparison_id
        assert len(current["history"]) == 1


def test_deleting_application_keeps_comparison_and_cv(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        apps.delete_application(connection, app_id)
        assert storage.get_cv(connection, cv_id)["id"] == cv_id
        assert records.get_comparison(connection, comparison_id)["id"] == comparison_id


def test_link_replacement_and_clear_are_explicit(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        apps.update_application(connection, app_id, {"notes": "Keep links"})
        assert apps.get_application(connection, app_id)["comparison_id"] == comparison_id
        apps.update_application(connection, app_id, {}, links={"cv_id": cv_id})
        current = apps.get_application(connection, app_id)
        assert current["cv_id"] == cv_id and current["comparison_id"] is None
        apps.update_application(connection, app_id, {}, links={})
        assert all(apps.get_application(connection, app_id)[key] is None for key in apps.LINK_FIELDS)


def test_changed_link_snapshot_prevents_silent_version_rebinding(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        expected = apps.resolve_links(connection, cv_id=cv_id)
        connection.execute("UPDATE cv_segments SET reviewed_text = 'Changed synthetic CV' WHERE cv_id = ?", (cv_id,))
        connection.commit()
        with pytest.raises(apps.ApplicationError, match="changed since review"):
            apps.create_application(connection, company="Demo", role="Role", cv_id=cv_id, expected_links=expected)
        assert apps.list_applications(connection) == []


def test_stale_comparison_not_saved_or_attached(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        comparison = compare_job(storage.get_cv(connection, cv_id), job_from_text("Python required"))
        connection.execute("UPDATE cv_segments SET reviewed_text = 'Changed synthetic CV' WHERE cv_id = ?", (cv_id,))
        connection.commit()
        with pytest.raises(apps.ApplicationError, match="changed since comparison"):
            records.save_comparison(connection, comparison)
        with pytest.raises(apps.ApplicationError, match="does not refer"):
            apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)


def test_export_defaults_exclude_notes_cv_contents_and_digests(linked_store):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id,
                                         notes="SYNTHETIC_PRIVATE_NOTES", next_action="Follow up")
        raw = export_applications(connection)
        result = json.loads(raw)
        assert result["applications"][0]["next_action"] == "Follow up"
        assert "PRIVATE" not in raw and "cv_digest" not in raw and '"notes"' not in raw
        assert '"history"' not in raw
        detailed = json.loads(export_applications(connection, include_notes=True, include_history=True))["applications"][0]
        assert detailed["notes"] == "SYNTHETIC_PRIVATE_NOTES"
        assert len(detailed["history"]) == 1
        assert detailed["id"] == app_id


def test_export_does_not_read_cv_tables(linked_store):
    import sqlite3
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        def authorize(action, table, column, db, source):
            if action == sqlite3.SQLITE_READ and table in {"cvs", "cv_segments", "profiles", "job_comparisons"}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        assert json.loads(export_applications(connection, include_history=True))["applications"]


def test_export_filters_and_empty_result(linked_store):
    path, _, _ = linked_store
    with storage.database(path) as connection:
        apps.create_application(connection, company="Demo", role="Role")
        apps.create_application(connection, company="Other", role="Role", status="rejected")
        selected = json.loads(export_applications(connection, status="saved"))["applications"]
        assert len(selected) == 1 and selected[0]["company"] == "Demo"
        assert json.loads(export_applications(connection, company="No matches"))["applications"] == []


def test_export_limit_is_explicit_not_silent(linked_store, monkeypatch):
    from job_assistant import application_export
    path, _, _ = linked_store
    monkeypatch.setattr(application_export, "list_applications", lambda *a, **k: [{}] * 10001)
    with storage.database(path) as connection:
        with pytest.raises(apps.ApplicationError, match="10,000"):
            export_applications(connection)
        assert not connection.in_transaction


def test_reused_cv_id_is_not_mistaken_for_the_original_approved_version(linked_store, monkeypatch):
    path, cv_id, comparison_id = linked_store
    with storage.database(path) as connection:
        old = storage.get_cv(connection, cv_id)
        storage.delete_cv(connection, cv_id)
        monkeypatch.setattr(storage, "timestamp", lambda: "2099-01-01T00:00:00+00:00")
        document = ExtractedDocument("synthetic.txt", "txt", 30, "a" * 64, "fixture", [
            Segment(s["reference"], s["source_text"], s["reviewed_text"]) for s in old["segments"]])
        reused = storage.save_cv(connection, old["profile_id"], old["title"], document)
        assert reused == cv_id
        app_id = apps.create_application(connection, company="Demo", role="Role", comparison_id=comparison_id)
        assert apps.get_application(connection, app_id)["cv_id"] is None
        with pytest.raises(apps.ApplicationError, match="does not refer"):
            apps.create_application(connection, company="Demo", role="Role", cv_id=reused, comparison_id=comparison_id)
