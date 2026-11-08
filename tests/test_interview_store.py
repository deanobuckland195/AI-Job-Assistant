import json
import sqlite3

import pytest

from job_assistant import interview_store as practice, storage
from job_assistant.documents import ExtractedDocument, Segment
from job_assistant.interview_feedback import InterviewError

ANSWER = "Situation: During college our parser rejected rows.\nTask: My task was to check the input.\nAction: I tested the parser with synthetic data.\nResult: I reduced processing time by 25% during the project."
CLAIM = "I reduced processing time by 25% during the project"


def create_cv(connection):
    profile = storage.create_profile(connection, "SYNTHETIC_PRIVATE_NAME", [])
    document = ExtractedDocument("synthetic.txt", "txt", 50, "a" * 64, "fixture", [
        Segment("page 1", "ORIGINAL_PRIVATE_MARKER", CLAIM + "\nOTHER_PRIVATE_CV_CONTENT")])
    return storage.save_cv(connection, profile, "PRIVATE_CV_TITLE", document)


def test_sessions_questions_attempts_and_feedback_survive_restarts(tmp_path):
    path = tmp_path / "interview.sqlite3"
    with storage.database(path) as connection:
        session_id = practice.start_session(connection, "ai-engineering-apprentice", count=2)
        first = practice.record_answer(connection, session_id, 1, ANSWER)
        second = practice.record_answer(connection, session_id, 1, ANSWER + "\nI learned how to check real input.")
    with storage.database(path) as connection:
        session = practice.get_session(connection, session_id)
        assert len(session["questions"]) == 2
        assert [a["attempt"] for a in session["questions"][0]["answers"]] == [1, 2]
        answer = practice.get_answer(connection, first)
        assert answer["answer"] == ANSWER and len(answer["answer_digest"]) == 64
        assert answer["feedback"]["version"] == answer["feedback_version"]
        assert practice.get_answer(connection, second)["attempt"] == 2
        assert len(practice.list_sessions(connection)) == 1


def test_without_cv_does_not_read_private_cv_tables(tmp_path, monkeypatch):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        monkeypatch.setattr(storage, "get_cv", lambda *a: pytest.fail("No CV was selected"))
        answer_id = practice.record_answer(connection, session_id, 1, ANSWER)
        assert practice.get_answer(connection, answer_id)["feedback"]["cv_availability"] == "No CV linked"


def test_explicit_approved_cv_corroboration_keeps_only_reference_metadata(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        cv_id = create_cv(connection)
        session_id = practice.start_session(connection, "general", cv_id=cv_id)
        answer_id = practice.record_answer(connection, session_id, 1, ANSWER)
        answer = practice.get_answer(connection, answer_id)
        supported = [c for c in answer["feedback"]["claims"] if c["state"] == "supported_wording"]
        assert supported and supported[0]["cv_evidence"]["reference"] == "page 1"
        assert "OTHER_PRIVATE_CV_CONTENT" not in json.dumps(answer)
        assert "ORIGINAL_PRIVATE_MARKER" not in json.dumps(answer)
        assert "PRIVATE_CV_TITLE" not in json.dumps(practice.get_session(connection, session_id))


def test_deleted_cv_keeps_practice_and_never_binds_reused_id(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        cv_id = create_cv(connection)
        session_id = practice.start_session(connection, "general", cv_id=cv_id)
        first = practice.record_answer(connection, session_id, 1, ANSWER)
        storage.delete_cv(connection, cv_id)
        assert create_cv(connection) == cv_id
        session = practice.get_session(connection, session_id)
        assert session["cv_id"] is None and session["cv_original_id"] == cv_id
        second = practice.record_answer(connection, session_id, 1, ANSWER)
        assert any(c["state"] == "supported_wording" for c in practice.get_answer(connection, first)["feedback"]["claims"])
        assert not any(c["state"] == "supported_wording" for c in practice.get_answer(connection, second)["feedback"]["claims"])
        assert "deleted" in practice.get_answer(connection, second)["feedback"]["cv_availability"]


def test_stale_cv_or_changed_review_invalidates_confirmation(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        cv_id = create_cv(connection)
        session_id = practice.start_session(connection, "general", cv_id=cv_id)
        assessed = practice.assess_answer(connection, session_id, 1, ANSWER)
        connection.execute("UPDATE cv_segments SET reviewed_text = ? WHERE cv_id = ?", ("Changed synthetic CV", cv_id))
        connection.commit()
        with pytest.raises(InterviewError, match="changed since review"):
            practice.record_answer(connection, session_id, 1, ANSWER, expected_review_digest=assessed["review_digest"])
        assert practice.get_session(connection, session_id)["questions"][0]["answers"] == []
        second = practice.record_answer(connection, session_id, 1, ANSWER)
        assert "no longer matches" in practice.get_answer(connection, second)["feedback"]["cv_availability"]


def test_question_snapshot_not_rewritten_by_bank_edits(tmp_path, monkeypatch):
    from job_assistant import interview_questions
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        prompt = practice.get_session(connection, session_id)["questions"][0]["prompt"]
        monkeypatch.setitem(interview_questions.BANK, "general", [])
        assert practice.get_session(connection, session_id)["questions"][0]["prompt"] == prompt


def test_sql_injection_is_stored_as_text(tmp_path):
    attack = "Robert'); DROP TABLE interview_sessions; --"
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general", title=attack)
        answer_id = practice.record_answer(connection, session_id, 1, attack)
        assert practice.get_answer(connection, answer_id)["answer"] == attack
        assert practice.get_session(connection, session_id)["title"] == attack
        assert len(practice.list_sessions(connection)) == 1


def test_session_creation_failure_rolls_back_parent(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        connection.execute("CREATE TRIGGER fail_questions BEFORE INSERT ON interview_questions BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            practice.start_session(connection, "general")
        assert practice.list_sessions(connection) == []


def test_failed_answer_insert_does_not_consume_attempt(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        connection.execute("CREATE TRIGGER fail_answer BEFORE INSERT ON interview_answers BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            practice.record_answer(connection, session_id, 1, ANSWER)
        assert practice.get_session(connection, session_id)["questions"][0]["next_attempt"] == 1
        connection.execute("DROP TRIGGER fail_answer")
        answer_id = practice.record_answer(connection, session_id, 1, ANSWER)
        assert practice.get_answer(connection, answer_id)["attempt"] == 1


def test_individual_deletion_keeps_other_answers_and_never_reuses_attempts(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        first = practice.record_answer(connection, session_id, 1, ANSWER)
        second = practice.record_answer(connection, session_id, 1, ANSWER)
        practice.delete_answer(connection, second)
        third = practice.record_answer(connection, session_id, 1, ANSWER)
        assert third > second and practice.get_answer(connection, third)["attempt"] == 3
        assert practice.get_answer(connection, first)


def test_session_deletion_cascades_only_practice_records(tmp_path):
    from job_assistant.applications import create_application, get_application
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        cv_id = create_cv(connection)
        app_id = create_application(connection, company="Synthetic", role="Role", cv_id=cv_id)
        session_id = practice.start_session(connection, "general", cv_id=cv_id)
        practice.record_answer(connection, session_id, 1, ANSWER)
        practice.delete_session(connection, session_id)
        assert practice.list_sessions(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM interview_questions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM interview_answers").fetchone()[0] == 0
        assert storage.get_cv(connection, cv_id) and get_application(connection, app_id)


def test_failed_session_delete_preserves_every_record(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        answer_id = practice.record_answer(connection, session_id, 1, ANSWER)
        connection.execute("CREATE TRIGGER fail_session_delete BEFORE DELETE ON interview_sessions BEGIN SELECT RAISE(ABORT, 'Synthetic failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            practice.delete_session(connection, session_id)
        assert practice.get_answer(connection, answer_id)


def test_attempt_limit_and_invalid_question_are_predictable(tmp_path):
    with storage.database(tmp_path / "interview.sqlite3") as connection:
        session_id = practice.start_session(connection, "general")
        with pytest.raises(InterviewError, match="Question not found"):
            practice.record_answer(connection, session_id, 99, ANSWER)
        connection.execute("UPDATE interview_questions SET next_attempt = 51 WHERE session_id = ? AND number = 1", (session_id,))
        connection.commit()
        with pytest.raises(InterviewError, match="50 recorded"):
            practice.record_answer(connection, session_id, 1, ANSWER)
