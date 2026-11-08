from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_assistant import interview_store as practice, openai_interview as ai, storage
from test_openai_interview import ANSWER, ITEM, mock_response

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.sqlite3"
    monkeypatch.setenv("AI_JOB_ASSISTANT_DATABASE", str(path))
    at = AppTest.from_file(str(PROJECT / "dashboard.py"), default_timeout=20)
    at.run().radio(key="workspace").set_value("Interview Practice").run()
    return path, at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def start(at):
    click(at, "Start practice session")
    at.text_area(key="practice_1_1_answer").input(ANSWER)
    click(at, "Review offline feedback")


def test_offline_review_save_history_and_delete(dashboard, monkeypatch):
    path, at = dashboard
    monkeypatch.setattr(ai, "send_request", lambda *a, **kw: pytest.fail("offline must not send"))
    monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("no CV selected"))
    start(at)
    click(at, "Save reviewed attempt")
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["answer"] == ANSWER
    assert any("as recorded" in c.value for c in at.caption)
    assert next(b for b in at.button if b.label == "Confirm answer deletion").disabled
    at.checkbox(key="practice_delete_answer_1").check().run()
    click(at, "Confirm answer deletion")
    with storage.database(path) as connection:
        assert practice.get_session(connection, 1)["questions"][0]["answers"] == []


def test_consent_send_save_reruns_and_snapshot(dashboard, monkeypatch):
    path, at = dashboard
    calls = mock_response(monkeypatch, {"suggestions": [ITEM]})
    start(at)
    assert len(calls) == 0
    click(at, "Request AI coaching once")
    assert at.error and len(calls) == 0
    at.text_input(key="practice_1_1_model").input("synthetic-model")
    at.checkbox(key="practice_1_1_consent").check()
    click(at, "Request AI coaching once")
    assert len(calls) == 1
    at.run()
    click(at, "Save reviewed attempt")
    at.run()
    assert len(calls) == 1
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["feedback"]["ai_coaching"]["status"] == "validated"


def test_edited_answer_hides_save_until_review(dashboard):
    path, at = dashboard
    start(at)
    at.text_area(key="practice_1_1_answer").input("A different synthetic answer.").run()
    assert not any(b.label == "Save reviewed attempt" for b in at.button)
    click(at, "Review offline feedback")
    click(at, "Save reviewed attempt")
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["answer"] == "A different synthetic answer."


def test_ai_failure_can_save_offline_feedback(dashboard, monkeypatch):
    path, at = dashboard
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    start(at)
    at.text_input(key="practice_1_1_model").input("synthetic-model")
    at.checkbox(key="practice_1_1_consent").check()
    click(at, "Request AI coaching once")
    assert any("Offline feedback retained" in t.value for t in at.text)
    click(at, "Save reviewed attempt")
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["feedback"]["ai_coaching"]["status"] == "offline_fallback"


def test_new_review_resets_consent(dashboard):
    path, at = dashboard
    start(at)
    at.checkbox(key="practice_1_1_consent").check().run()
    at.text_area(key="practice_1_1_answer").input(ANSWER + " Extra context.").run()
    click(at, "Review offline feedback")
    assert at.checkbox(key="practice_1_1_consent").value is False


def test_changed_question_blocks_stale_save(dashboard):
    path, at = dashboard
    start(at)
    with storage.database(path) as connection:
        connection.execute("UPDATE interview_questions SET prompt = ? WHERE session_id = 1 AND number = 1", ("Changed synthetic question",))
        connection.commit()
    click(at, "Save reviewed attempt")
    assert any("changed since review" in error.value for error in at.error)
    with storage.database(path) as connection:
        assert practice.get_session(connection, 1)["questions"][0]["answers"] == []
