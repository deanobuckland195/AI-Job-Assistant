from pathlib import Path
import json

import pytest
from streamlit.testing.v1 import AppTest

from job_assistant import interview_store as practice, openai_interview as ai, storage
from test_openai_interview import ANSWER, ITEM, mock_response
from test_openai_analysis import FakeConnection
from job_assistant import openai_analysis as provider

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
    assert any("Offline feedback retained" in t.value and "credentials missing" in t.value for t in at.warning)
    click(at, "Save reviewed attempt")
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["feedback"]["ai_coaching"]["status"] == "offline_fallback"


@pytest.mark.parametrize("status,code,label", [
    (401, "invalid_api_key", "authentication/invalid key"),
    (429, "insufficient_quota", "API billing/quota"),
    (429, "rate_limit_exceeded", "API rate limit"),
    (404, "model_not_found", "model unavailable"),
    (400, "invalid_json_schema", "API request rejected"),
    (504, None, "connection failed or timed out"),
    (200, None, "Invalid API response"),
])
def test_dashboard_shows_safe_category_without_saving_or_retrying(dashboard, monkeypatch, status, code, label, caplog):
    path, at = dashboard
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE_SYNTHETIC_KEY")
    connection = FakeConnection(status=status, data=json.dumps({"error": {
        "code": code, "message": "PRIVATE_PROVIDER_MESSAGE"}}).encode())
    monkeypatch.setattr(provider.http.client, "HTTPSConnection", lambda *a, **kw: connection)
    start(at)
    with storage.database(path) as db:
        before = list(db.iterdump())
    at.text_input(key="practice_1_1_model").input("synthetic-model")
    at.checkbox(key="practice_1_1_consent").check()
    click(at, "Request AI coaching once")
    assert any(label in warning.value for warning in at.warning)
    rendered = str(at.warning) + str(at.text) + str(at.error) + caplog.text
    assert "PRIVATE" not in rendered and "Authorization" not in rendered and "Bearer" not in rendered
    at.run()
    assert len(connection.calls) == 1 and connection.closed
    with storage.database(path) as db:
        assert list(db.iterdump()) == before


def test_new_review_resets_consent(dashboard):
    path, at = dashboard
    start(at)
    at.checkbox(key="practice_1_1_consent").check().run()
    at.text_area(key="practice_1_1_answer").input(ANSWER + " Extra context.").run()
    click(at, "Review offline feedback")
    assert at.checkbox(key="practice_1_1_consent").value is False


def test_gpt41_mini_copyable_citation_and_multipart_response_in_dashboard(dashboard, monkeypatch, caplog):
    path, at = dashboard
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-offline-key")
    connection = FakeConnection()
    def request(method, route, **kwargs):
        FakeConnection.request(connection, method, route, **kwargs)
        body = json.loads(kwargs["body"])
        assert body["model"] == "gpt-4.1-mini"
        user = json.loads(body["input"][0]["content"])
        entry = user["safe_clause_spans"][0]
        payload = json.dumps({"suggestions": [{"action": "clarity", "start": entry["start"], "quote": entry["quote"]}]})
        connection.data = json.dumps({"status": "completed", "model": "gpt-4.1-mini-2025-04-14", "output": [{
            "type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": payload[:12], "annotations": []},
                {"type": "output_text", "text": payload[12:], "annotations": []}]}]}).encode()
    monkeypatch.setattr(connection, "request", request)
    monkeypatch.setattr(provider.http.client, "HTTPSConnection", lambda *a, **kw: connection)
    start(at)
    with storage.database(path) as db:
        before = list(db.iterdump())
    at.text_input(key="practice_1_1_model").input("gpt-4.1-mini")
    at.checkbox(key="practice_1_1_consent").check()
    click(at, "Request AI coaching once")
    assert any("AI-selected coaching prompts" in text.value for text in at.text)
    assert not at.warning and not at.error
    at.run()
    assert len(connection.calls) == 1 and connection.closed
    assert ANSWER not in caplog.text
    with storage.database(path) as db:
        assert list(db.iterdump()) == before


def test_dashboard_distinguishes_bad_citation_without_showing_provider_quote(dashboard, monkeypatch):
    _, at = dashboard
    mock_response(monkeypatch, {"suggestions": [dict(ITEM, quote="PRIVATE_PROVIDER_QUOTE")]})
    start(at)
    at.text_input(key="practice_1_1_model").input("gpt-4.1-mini")
    at.checkbox(key="practice_1_1_consent").check()
    click(at, "Request AI coaching once")
    assert any("stated character offset" in warning.value for warning in at.warning)
    assert "PRIVATE_PROVIDER_QUOTE" not in str(at.warning) + str(at.error) + str(at.text)


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
