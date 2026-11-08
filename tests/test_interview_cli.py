import argparse
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import cli, interview_cli, interview_store as practice, storage
from job_assistant.interview_feedback import InterviewError

ANSWER = "Situation: During college our parser rejected rows.\nTask: My task was to check input.\nAction: I tested the parser using synthetic records.\nResult: I learned how to make the parser more reliable."


def args_for(path, command):
    parser = argparse.ArgumentParser()
    interview_cli.register_commands(parser.add_subparsers(dest="command"))
    args = parser.parse_args(command)
    args.database = path
    return args


def scripted(values):
    answers = iter(values)
    return lambda prompt: next(answers)


@pytest.fixture
def session(tmp_path):
    path = tmp_path / "practice.sqlite3"
    with storage.database(path) as connection:
        session_id = practice.start_session(connection, "ai-engineering-apprentice", count=2)
    return path, session_id


def test_roles_require_no_database_access(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "database", lambda *a: pytest.fail("Roles are static"))
    output = []
    assert interview_cli.run_command(args_for(tmp_path / "unused.sqlite3", ["interview-roles"]), write=output.append) == 0
    assert "ai-engineering-apprentice" in "\n".join(output)


def test_session_start_confirmation_and_invalid_count(tmp_path):
    path = tmp_path / "practice.sqlite3"
    args = args_for(path, ["interview-start", "--role", "general"])
    assert interview_cli.run_command(args, scripted(["no"]), lambda text: None) == 0
    assert not path.exists()
    assert interview_cli.run_command(args, scripted(["yes"]), lambda text: None) == 0
    args.count = 99
    assert interview_cli.run_command(args, lambda prompt: pytest.fail("Invalid count"), lambda text: None) == 1


def test_feedback_is_shown_before_save_and_declining_leaves_no_answer(session):
    path, session_id = session
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--answer", ANSWER])
    output = []
    def decline(prompt):
        assert "=== Offline Interview Feedback" in "\n".join(output)
        assert "SUGGESTIONS" in "\n".join(output)
        return "no"
    assert interview_cli.run_command(args, decline, output.append) == 0
    with storage.database(path) as connection:
        assert practice.get_session(connection, session_id)["questions"][0]["answers"] == []


def test_multiline_and_star_inputs(session):
    path, session_id = session
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1"])
    assert interview_cli.run_command(args, scripted([*ANSWER.splitlines(), "/done", "yes"]), lambda text: None) == 0
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--star"])
    values = ["During college our parser rejected valid rows", "/done", "My task was to make the parser reliable", "/done",
              "I tested the parser using synthetic data", "/done", "I learned how to validate real input", "/done", "yes"]
    assert interview_cli.run_command(args, scripted(values), lambda text: None) == 0
    with storage.database(path) as connection:
        assert len(practice.get_session(connection, session_id)["questions"][0]["answers"]) == 2
        assert practice.get_answer(connection, 2)["answer"].startswith("Situation:")


def test_answer_review_show_feedback_and_safe_delete(session):
    path, session_id = session
    with storage.database(path) as connection:
        answer_id = practice.record_answer(connection, session_id, 1, ANSWER)
    output = []
    for command in ("interview-show", "interview-answer-show", "interview-feedback"):
        args = args_for(path, [command, str(session_id if command == "interview-show" else answer_id)])
        assert interview_cli.run_command(args, write=output.append) == 0
    assert "attempt 1" in "\n".join(output)
    assert "Recorded answer" in "\n".join(output)
    delete = args_for(path, ["interview-answer-delete", str(answer_id)])
    assert interview_cli.run_command(delete, scripted(["no"]), lambda text: None) == 0
    assert interview_cli.run_command(delete, scripted(["yes"]), lambda text: None) == 0
    with storage.database(path) as connection:
        assert practice.get_session(connection, session_id)["questions"][0]["answers"] == []


def test_session_deletion_cancel_then_confirm(session):
    path, session_id = session
    args = args_for(path, ["interview-delete", str(session_id)])
    assert interview_cli.run_command(args, scripted(["no"]), lambda text: None) == 0
    with storage.database(path) as connection:
        assert practice.get_session(connection, session_id)
    assert interview_cli.run_command(args, scripted(["yes"]), lambda text: None) == 0
    with storage.database(path) as connection:
        assert practice.list_sessions(connection) == []


def test_stale_session_delete_cannot_remove_newly_recorded_attempt(session):
    path, session_id = session
    args = args_for(path, ["interview-delete", str(session_id)])
    def new_attempt(prompt):
        with storage.database(path) as connection:
            practice.record_answer(connection, session_id, 1, ANSWER)
        return "yes"
    output = []
    assert interview_cli.run_command(args, new_attempt, output.append) == 1
    assert "changed since review" in "\n".join(output)
    with storage.database(path) as connection:
        assert len(practice.get_session(connection, session_id)["questions"][0]["answers"]) == 1


@pytest.mark.parametrize("values", [["" , "/done"], ["x" * 2001]])
def test_invalid_answers_not_saved(session, values):
    path, session_id = session
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1"])
    assert interview_cli.run_command(args, scripted(values), lambda text: None) == 1
    with storage.database(path) as connection:
        assert practice.get_session(connection, session_id)["questions"][0]["answers"] == []


def test_interruption_never_saves_draft(session, monkeypatch):
    path, session_id = session
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1"])
    def interrupt(prompt):
        raise EOFError
    with pytest.raises(EOFError):
        interview_cli.run_command(args, interrupt, lambda text: None)
    with storage.database(path) as connection:
        assert practice.get_session(connection, session_id)["questions"][0]["answers"] == []
    monkeypatch.setattr(interview_cli, "run_command", lambda args: (_ for _ in ()).throw(KeyboardInterrupt))
    assert cli.main(["interview-list"]) == 130


def test_practice_does_not_call_live_ai_even_when_key_exists(session, monkeypatch):
    from job_assistant import openai_analysis
    path, session_id = session
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_UNUSED_KEY")
    monkeypatch.setattr(openai_analysis, "send_request", lambda *a, **k: pytest.fail("Practice must remain offline"))
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--answer", ANSWER])
    assert interview_cli.run_command(args, scripted(["yes"]), lambda text: None) == 0


def test_unexpected_database_error_is_safe(session, monkeypatch):
    path, session_id = session
    def fail(*args):
        raise OSError("PRIVATE_EXCEPTION_DETAILS")
    monkeypatch.setattr(storage, "database", fail)
    output = []
    args = args_for(path, ["interview-list"])
    assert interview_cli.run_command(args, write=output.append) == 1
    assert "PRIVATE_EXCEPTION_DETAILS" not in "\n".join(output)


def test_terminal_controls_are_escaped_in_stored_answer_review(session):
    path, session_id = session
    with storage.database(path) as connection:
        answer_id = practice.record_answer(connection, session_id, 1, "I learned to check input \u202e safely.")
    output = []
    args = args_for(path, ["interview-answer-show", str(answer_id)])
    assert interview_cli.run_command(args, write=output.append) == 0
    assert "\u202e" not in "\n".join(output)
    assert "\\u202e" in "\n".join(output)


def test_real_cli_session_and_answer_retrieval(tmp_path):
    project = Path(__file__).resolve().parents[1]
    path = tmp_path / "cli.sqlite3"
    base = [sys.executable, "-B", str(project / "main.py"), "--database", str(path)]
    def run(command, answers=""):
        result = subprocess.run(base + command, input=answers, text=True, capture_output=True, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    run(["interview-start", "--role", "ai-engineering-apprentice", "--count", "2"], "yes\n")
    assert "Practice answer saved" in run(["interview-answer", "1", "--question", "1"], ANSWER + "\n/done\nyes\n")
    assert "Offline Interview Feedback" in run(["interview-feedback", "1"])
    assert "attempt 1" in run(["interview-show", "1"])
    run(["interview-delete", "1"], "yes\n")
    assert "Listed 0" in run(["interview-list"])


def test_reproducible_synthetic_interview_demo():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-B", "-m", "examples.interview_practice_demo"], cwd=project,
                            input="", text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STAR/clarity coaching" in result.stdout
    assert "Temporary files removed" in result.stdout


def test_ai_declined_keeps_offline_save(session, monkeypatch):
    from job_assistant import openai_interview
    path, session_id = session
    monkeypatch.setattr(openai_interview, "send_request", lambda *a, **kw: pytest.fail("Consent declined"))
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--answer", ANSWER,
                           "--ai", "--model", "synthetic-model"])
    output = []
    assert interview_cli.run_command(args, scripted(["no", "yes"]), output.append) == 0
    assert "AI cancelled" in "\n".join(output)
    with storage.database(path) as connection:
        assert "ai_coaching" not in practice.get_answer(connection, 1)["feedback"]


def test_ai_cli_consent_payload_save_and_reopen(session, monkeypatch):
    from job_assistant import openai_interview
    from test_openai_interview import mock_response
    path, session_id = session
    calls = mock_response(monkeypatch, {"suggestions": []})
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--answer", ANSWER,
                           "--ai", "--model", "synthetic-model"])
    output = []
    responses = iter(["yes", "yes"])
    def consent(prompt):
        assert ANSWER in "\n".join(output)
        assert "CV text" in "\n".join(output)
        return next(responses)
    assert interview_cli.run_command(args, consent, output.append) == 0
    assert len(calls) == 1
    with storage.database(path) as connection:
        assert practice.get_answer(connection, 1)["feedback"]["ai_coaching"]["status"] == "validated"
    assert interview_cli.run_command(args_for(path, ["interview-feedback", "1"]), write=output.append) == 0
    assert len(calls) == 1


def test_ai_cli_missing_model_sends_nothing(session, monkeypatch):
    from job_assistant import openai_interview
    path, session_id = session
    monkeypatch.setattr(openai_interview, "send_request", lambda *a, **kw: pytest.fail("Missing model"))
    args = args_for(path, ["interview-answer", str(session_id), "--question", "1", "--answer", ANSWER, "--ai"])
    assert interview_cli.run_command(args, lambda prompt: pytest.fail("Must validate first"), lambda text: None) == 1
