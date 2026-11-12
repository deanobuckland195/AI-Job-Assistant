from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_assistant import roadmap_store as plans, storage
from test_roadmaps import comparison

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sqlite3"
    monkeypatch.setenv("AI_JOB_ASSISTANT_DATABASE", str(path))
    at = AppTest.from_file(str(PROJECT / "dashboard.py"), default_timeout=20)
    at.run().radio(key="workspace").set_value("Skills Roadmap").run()
    return path, at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def create(at):
    click(at, "Preview skills roadmap")
    click(at, "Save new roadmap")


def test_empty_preview_and_save_are_separate(dashboard):
    path, at = dashboard
    assert any("No roadmaps yet" in info.value for info in at.info)
    at.text_input(key="roadmap_skills").input("Python, Git")
    at.number_input(key="roadmap_hours").set_value(2)
    click(at, "Preview skills roadmap")
    assert at.dataframe
    with storage.database(path) as connection:
        assert plans.list_roadmaps(connection) == []
    click(at, "Save new roadmap")
    with storage.database(path) as connection:
        current = plans.get_roadmap(connection, 1)
        assert current["plan"]["selected_skills"] == ["python", "git"]
        assert current["weekly_hours"] == 2
    assert at.get("progress")
    assert not any(b.label == "Save new roadmap" for b in at.button)


def test_edit_completion_requires_evidence_and_survives_reload(dashboard):
    path, at = dashboard
    create(at)
    at.text_area(key="roadmap_edit_1_1_1_objective").input("Build one synthetic CSV check")
    at.selectbox(key="roadmap_edit_1_1_1_status").set_value("completed")
    click(at, "Save milestone progress")
    assert any("completion evidence" in e.value for e in at.error)
    at.text_area(key="roadmap_edit_1_1_1_evidence").input("demo.py: missing row check passed")
    click(at, "Save milestone progress")
    click(at, "Reload roadmap")
    with storage.database(path) as connection:
        current = plans.get_roadmap(connection, 1)
        assert current["milestones"][0]["status"] == "completed"
        assert current["milestones"][0]["objective"] == "Build one synthetic CSV check"
        assert plans.progress(current)["completed"] == 1
    assert at.selectbox(key="roadmap_edit_1_2_1_status").value == "completed"


def test_stale_edit_and_delete_rejected(dashboard):
    path, at = dashboard
    create(at)
    with storage.database(path) as connection:
        plans.update_milestone(connection, 1, 1, {"objective": "Newer synthetic change"}, expected_revision=1)
    at.text_area(key="roadmap_edit_1_1_1_objective").input("Stale draft")
    click(at, "Save milestone progress")
    assert any("changed since review" in e.value for e in at.error)
    at.run()
    at.checkbox(key="roadmap_edit_1_1_delete_ack").check().run()
    click(at, "Confirm roadmap deletion")
    assert at.error
    click(at, "Reload roadmap")
    assert at.text_area(key="roadmap_edit_1_2_1_objective").value == "Newer synthetic change"


def test_delete_requires_acknowledgement_and_preserves_other_records(dashboard):
    path, at = dashboard
    create(at)
    assert next(b for b in at.button if b.label == "Confirm roadmap deletion").disabled
    at.checkbox(key="roadmap_edit_1_1_delete_ack").check().run()
    click(at, "Confirm roadmap deletion")
    with storage.database(path) as connection:
        assert plans.list_roadmaps(connection) == []
    assert any("No roadmaps yet" in info.value for info in at.info)


def test_comparison_dashboard_uses_metadata_without_cv_reads(dashboard, monkeypatch):
    path, at = dashboard
    with storage.database(path) as connection:
        comp_id, _ = comparison(connection)
    monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("Dashboard cannot load CV text"))
    at.run()
    at.selectbox(key="roadmap_comparison").set_value(comp_id)
    click(at, "Preview skills roadmap")
    click(at, "Save new roadmap")
    assert "SYNTHETIC_PRIVATE" not in str(at)
    with storage.database(path) as connection:
        assert any(g["state"] == "supported_wording" for g in plans.get_roadmap(connection, 1)["plan"]["gaps"])


def test_title_can_be_edited_without_regenerating_progress(dashboard):
    path, at = dashboard
    create(at)
    at.text_input(key="roadmap_edit_1_1_title").input("My apprenticeship plan")
    click(at, "Save roadmap title")
    with storage.database(path) as connection:
        assert plans.get_roadmap(connection, 1)["title"] == "My apprenticeship plan"


def test_milestone_summary_displays_evidence_as_text(dashboard):
    path, at = dashboard
    create(at)
    evidence = '<b>Synthetic artifact</b> ![image](https://example.com/pixel)'
    at.text_area(key="roadmap_edit_1_1_1_evidence").input(evidence)
    at.selectbox(key="roadmap_edit_1_1_1_status").set_value("in progress")
    click(at, "Save milestone progress")
    assert any(e.label == "Recorded completion evidence" for e in at.expander)
    assert any(t.value == evidence for t in at.text)
    assert all(evidence not in m.value for m in at.markdown)
    assert any("In Progress" in t.value for t in at.text)


def test_studio_cards_show_saved_tasks_and_real_progress_without_writing(dashboard):
    path, at = dashboard
    create(at)
    with storage.database(path) as connection:
        saved = plans.get_roadmap(connection, 1)
        before = list(connection.iterdump())
    at.run()
    assert not at.exception
    shown = [text.value for text in at.text]
    for milestone in saved["milestones"]:
        for field in ("objective", "exercise", "project", "expected_evidence"):
            assert milestone[field] in shown
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Weekly study budget"] == f"{saved['weekly_hours']} hours"
    assert metrics["Completed milestones"] == f"0 / {len(saved['milestones'])}"
    assert metrics["In progress"] == "0"
    assert any(e.label == "Exercise & mini-project" for e in at.expander)
    with storage.database(path) as connection:
        assert list(connection.iterdump()) == before


def test_studio_preview_keeps_exercises_unsaved(dashboard):
    path, at = dashboard
    click(at, "Preview skills roadmap")
    assert {"Milestone preview", "Detailed plan"} <= {tab.label for tab in at.tabs}
    with storage.database(path) as connection:
        preview = plans.preview(connection, "ai-engineering-apprentice", "", 4)
        assert plans.list_roadmaps(connection) == []
    shown = [text.value for text in at.text]
    for milestone in preview["milestones"]:
        assert milestone["exercise"] in shown
        assert milestone["project"] in shown
