"""Synthetic roadmap rules, persistence and privacy regression coverage."""

import json
import sqlite3

import pytest

from job_assistant import applications, comparison_records, interview_store, roadmap_store as plans, storage
from job_assistant.applications import ApplicationError
from job_assistant.documents import ExtractedDocument, Segment
from job_assistant.job_matching import compare_job
from job_assistant.job_requirements import job_from_text
from job_assistant.roadmap_rules import ROLE_SKILLS, generate_plan


def comparison(connection, cv_text="Built a Python tool.\nCurrently learning SQL.", job_text="Essential:\nPython required\nSQL required\nGit required"):
    profile = storage.create_profile(connection, "SYNTHETIC_PRIVATE_NAME", ["machine learning"])
    doc = ExtractedDocument("synthetic.txt", "txt", 50, "a" * 64, "fixture", [Segment("page 1", cv_text, cv_text)])
    cv_id = storage.save_cv(connection, profile, "SYNTHETIC_PRIVATE_TITLE", doc)
    result = compare_job(storage.get_cv(connection, cv_id), job_from_text(job_text))
    return comparison_records.save_comparison(connection, result), cv_id


@pytest.fixture
def database(tmp_path):
    with storage.database(tmp_path / "synthetic.sqlite3") as connection:
        yield connection


@pytest.mark.parametrize("role", ROLE_SKILLS)
@pytest.mark.parametrize("hours", [1, 3, 20])
def test_deterministic_role_budget_and_milestone_content(role, hours):
    plan = generate_plan(role, "Python, python, ML", hours)
    assert plan == generate_plan(role, "Python, python, ML", hours)
    assert plan["selected_skills"] == ["python", "machine learning"]
    assert len(plan["milestones"]) > 0
    assert [m["week"] for m in plan["milestones"]] == list(range(1, len(plan["milestones"]) + 1))
    assert all(1 <= m["study_hours"] <= hours for m in plan["milestones"])
    assert all(m[field] for m in plan["milestones"] for field in ("objective", "exercise", "project", "expected_evidence"))
    assert "not verified" in plan["notice"]


@pytest.mark.parametrize("changes", [
    {"role_id": "unknown"}, {"role_id": []}, {"weekly_hours": 0}, {"weekly_hours": 21},
    {"weekly_hours": True}, {"weekly_hours": 2.5}, {"weekly_hours": "4"},
    {"skills": []}, {"skills": "a" * 2001}, {"skills": "python\x00"},
    {"skills": "a" * 101},
])
def test_invalid_generation_is_rejected(changes):
    kwargs = dict(role_id="general", skills="", weekly_hours=4)
    kwargs.update(changes)
    with pytest.raises(ApplicationError):
        generate_plan(**kwargs)


def test_evidence_states_and_no_source_excerpts(database, monkeypatch):
    comp_id, cv_id = comparison(database)
    monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("Roadmap must not read CV text"))
    plan = plans.preview(database, "ai-engineering-apprentice", "Git", 2, comparison_id=comp_id)
    gaps = {g["skill"]: g for g in plan["gaps"]}
    assert gaps["python"]["state"] == "supported_wording"
    assert gaps["sql"]["state"] == "uncertain"
    assert gaps["git"]["state"] == "self_reported"
    assert gaps["apis"]["state"] == "missing_evidence"
    assert gaps["git"]["requirements"][0]["status"] == "missing"  # self-report does not rewrite comparison
    assert gaps["python"]["requirements"][0]["cv_spans"]
    encoded = json.dumps(plan)
    assert "Built a Python" not in encoded and "SYNTHETIC_PRIVATE" not in encoded


@pytest.mark.parametrize("job_text,cv_text,skill", [
    ("Python or Java required", "Built a Python tool", "java"),
    ("5 years Python experience required", "Built a Python tool", "python"),
    ("Python required", "Built a Python tool\nNo Python experience", "python"),
    ("PostgreSQL required", "Built SQL databases", "postgresql"),
    ("Python", "Built a Python tool", "python"),
])
def test_alternatives_qualifiers_conflicts_related_and_unclear_are_not_confirmed(database, job_text, cv_text, skill):
    comp_id, _ = comparison(database, cv_text, job_text)
    plan = plans.preview(database, "general", "", 4, comparison_id=comp_id)
    entry = next(g for g in plan["gaps"] if g["skill"] == skill)
    assert entry["state"] == "uncertain"
    task = next(m for m in plan["milestones"] if m["skill"] == skill)
    assert task["objective"].startswith("Clarify")


def test_excluded_and_unknown_requirements_are_not_invented_skills(database):
    comp_id, _ = comparison(database, "Python", "Java not required\nCOBOL required")
    plan = plans.preview(database, "general", "", 4, comparison_id=comp_id)
    assert "java" not in {g["skill"] for g in plan["gaps"]}
    assert "cobol" not in {g["skill"] for g in plan["gaps"]}
    assert plan["unrecognised_requirements"]


def test_no_cv_and_old_comparison_use_explicit_fallback(database, monkeypatch):
    comp_id, _ = comparison(database)
    database.execute("DELETE FROM comparison_skill_snapshots WHERE comparison_id=?", (comp_id,))
    database.commit()
    monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("No CV reads"))
    plan = plans.preview(database, "general", "Git", 4, comparison_id=comp_id)
    assert "counts only" in plan["source_notice"]
    assert all(g["state"] != "supported_wording" for g in plan["gaps"])
    assert plans.create_roadmap(database, "general", "Git")


def test_persistence_completion_reopen_and_immutable_evidence(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    with storage.database(path) as connection:
        comp_id, cv_id = comparison(connection)
        roadmap_id = plans.create_roadmap(connection, "general", "Python", 3, comparison_id=comp_id)
        roadmap = plans.get_roadmap(connection, roadmap_id)
        milestone_id = roadmap["milestones"][0]["id"]
        plans.update_milestone(connection, roadmap_id, milestone_id,
            {"status": "completed", "completion_evidence": "local-demo.py: 3 synthetic checks passed"}, expected_revision=1)
    with storage.database(path) as connection:
        current = plans.get_roadmap(connection, roadmap_id)
        assert current["revision"] == 2 and current["milestones"][0]["completed_at"]
        assert plans.progress(current)["completed"] == 1
        assert current["plan"] == roadmap["plan"]
        plans.update_milestone(connection, roadmap_id, milestone_id, {"status": "in progress"}, expected_revision=2)
        reopened = plans.get_roadmap(connection, roadmap_id)["milestones"][0]
        assert reopened["completed_at"] is None and reopened["completion_evidence"]


@pytest.mark.parametrize("changes", [
    {"status": "done"}, {"status": []}, {"status": "completed"}, {"objective": " "},
    {"objective": "a" * 1001}, {"exercise": None}, {"project": "\x00"}, {"expected_evidence": ""},
    {"study_hours": 5}, {"study_hours": 0}, {"study_hours": True}, {"study_hours": 1.5},
    {"week": 9}, {"skill": "invented"}, {"completion_evidence": "a" * 4001},
])
def test_invalid_edit_rolls_back(database, changes):
    roadmap_id = plans.create_roadmap(database, "general", weekly_hours=4)
    original = plans.get_roadmap(database, roadmap_id)
    with pytest.raises(ApplicationError):
        plans.update_milestone(database, roadmap_id, original["milestones"][0]["id"], changes, expected_revision=1)
    assert plans.get_roadmap(database, roadmap_id) == original


def test_edit_every_field_and_stale_writes_cannot_overwrite(database):
    roadmap_id = plans.create_roadmap(database, "general")
    first = plans.get_roadmap(database, roadmap_id)["milestones"][0]
    updates = dict(objective="Practise one query", exercise="Try a JOIN", project="Synthetic contacts database",
                   expected_evidence="query.sql and checks", study_hours=2, status="in progress", completion_evidence="Draft query ready")
    assert plans.update_milestone(database, roadmap_id, first["id"], updates, expected_revision=1)
    edited = plans.get_roadmap(database, roadmap_id)
    assert all(edited["milestones"][0][k] == v for k, v in updates.items())
    with pytest.raises(ApplicationError, match="changed since review"):
        plans.update_milestone(database, roadmap_id, first["id"], {"status": "not started"}, expected_revision=1)
    with pytest.raises(ApplicationError):
        plans.delete_roadmap(database, roadmap_id, expected_revision=1)
    assert plans.rename_roadmap(database, roadmap_id, "Updated title", expected_revision=2)
    assert plans.get_roadmap(database, roadmap_id)["title"] == "Updated title"


def test_deletion_is_scoped_and_source_deletion_preserves_history(database):
    comp_id, cv_id = comparison(database)
    app_id = applications.create_application(database, company="Synthetic", role="Apprentice")
    session_id = interview_store.start_session(database, "general")
    roadmap_id = plans.create_roadmap(database, "general", comparison_id=comp_id)
    another = plans.create_roadmap(database, "data-analyst")
    comparison_records.delete_comparison(database, comp_id)
    current = plans.get_roadmap(database, roadmap_id)
    assert current["comparison_id"] is None and current["comparison_original_id"] == comp_id
    assert current["plan"]["comparison"]["cv_original_id"] == cv_id
    plans.delete_roadmap(database, roadmap_id, expected_revision=current["revision"])
    assert plans.get_roadmap(database, another)
    assert database.execute("SELECT 1 FROM roadmap_milestones WHERE roadmap_id=?", (roadmap_id,)).fetchone() is None
    assert storage.get_cv(database, cv_id) and applications.get_application(database, app_id) and interview_store.get_session(database, session_id)


def test_stale_preview_and_sql_text_are_safe(database):
    preview = plans.preview(database, "general", "Git", 2)
    with pytest.raises(ApplicationError, match="changed since preview"):
        plans.create_roadmap(database, "general", "Python", 2, expected_plan_digest=plans.plan_digest(preview))
    assert plans.list_roadmaps(database) == []
    attack = "Robert'); DROP TABLE roadmaps; --"
    roadmap_id = plans.create_roadmap(database, "general", title=attack)
    assert plans.get_roadmap(database, roadmap_id)["title"] == attack


def test_insert_and_edit_failure_are_atomic(database):
    database.execute("CREATE TRIGGER fail_milestone BEFORE INSERT ON roadmap_milestones BEGIN SELECT RAISE(ABORT,'Synthetic'); END")
    with pytest.raises(sqlite3.Error):
        plans.create_roadmap(database, "general")
    assert plans.list_roadmaps(database) == []
    database.execute("DROP TRIGGER fail_milestone")
    roadmap_id = plans.create_roadmap(database, "general")
    before = plans.get_roadmap(database, roadmap_id)
    database.execute("CREATE TRIGGER fail_revision BEFORE UPDATE ON roadmaps BEGIN SELECT RAISE(ABORT,'Synthetic'); END")
    with pytest.raises(sqlite3.Error):
        plans.update_milestone(database, roadmap_id, before["milestones"][0]["id"], {"objective": "Synthetic new objective"}, expected_revision=1)
    assert plans.get_roadmap(database, roadmap_id) == before


@pytest.mark.parametrize("limit,offset", [(0,0), (1001,0), (True,0), (10,-1), (10,True)])
def test_invalid_pagination(database, limit, offset):
    with pytest.raises(ApplicationError):
        plans.list_roadmaps(database, limit, offset)


def test_synthetic_end_to_end_demo(capsys):
    from examples.skills_roadmap_demo import main
    main()
    output = capsys.readouterr().out
    assert "schema 4 -> 5" in output and "survived reopening" in output
    assert "existing synthetic report retained" in output


@pytest.mark.parametrize("snapshot", [{}, [None], [{"terms": ["python"]}]])
def test_corrupt_snapshot_never_promotes_to_confirmed(database, snapshot):
    comp_id, _ = comparison(database)
    database.execute("UPDATE comparison_skill_snapshots SET snapshot_json=? WHERE comparison_id=?", (json.dumps(snapshot), comp_id))
    database.commit()
    with pytest.raises(storage.StorageError):
        plans.create_roadmap(database, "general", comparison_id=comp_id)
    assert plans.list_roadmaps(database) == []


def test_milestones_cannot_be_edited_via_another_roadmap(database):
    first = plans.create_roadmap(database, "general")
    second = plans.create_roadmap(database, "general")
    milestone = plans.get_roadmap(database, first)["milestones"][0]
    with pytest.raises(ApplicationError, match="not found in this roadmap"):
        plans.update_milestone(database, second, milestone["id"], {"objective": "Wrong parent"}, expected_revision=1)


def test_failed_delete_preserves_parent_and_children(database):
    roadmap_id = plans.create_roadmap(database, "general")
    before = plans.get_roadmap(database, roadmap_id)
    database.execute("CREATE TRIGGER fail_roadmap_delete BEFORE DELETE ON roadmaps BEGIN SELECT RAISE(ABORT,'Synthetic'); END")
    with pytest.raises(sqlite3.Error):
        plans.delete_roadmap(database, roadmap_id, expected_revision=1)
    assert plans.get_roadmap(database, roadmap_id) == before


def test_noop_does_not_change_revision_or_completion_time(database):
    roadmap_id = plans.create_roadmap(database, "general")
    before = plans.get_roadmap(database, roadmap_id)
    assert plans.update_milestone(database, roadmap_id, before["milestones"][0]["id"], {}, expected_revision=1) is False
    assert plans.rename_roadmap(database, roadmap_id, before["title"], expected_revision=1) is False
    assert plans.get_roadmap(database, roadmap_id) == before
