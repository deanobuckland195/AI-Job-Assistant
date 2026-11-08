from argparse import Namespace
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import cli, cv_cli, storage
from job_assistant.documents import ExtractedDocument, Segment


def scripted(values):
    answers = iter(values)
    return lambda prompt: next(answers)


@pytest.fixture
def setup_store(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    with storage.database(path) as connection:
        profile_id = storage.create_profile(connection, "Demo Candidate", ["python"])
    cv = tmp_path / "synthetic.txt"
    cv.write_text("Original Python\nSQL")
    return path, profile_id, cv


def test_review_correct_save_retrieve_and_delete(setup_store):
    path, profile, cv = setup_store
    output = []
    args = Namespace(command="cv-import", database=path, profile=profile, path=cv)
    answers = ["Reviewed CV", "bad", "999", "1", "Corrected Python experience", "/done", "done", "yes"]
    assert cv_cli.run_command(args, scripted(answers), output.append) == 0
    with storage.database(path) as connection:
        stored = storage.get_cv(connection, 1)
        assert stored["title"] == "Reviewed CV"
        assert stored["segments"][0]["source_text"] == "Original Python\n"
        assert stored["segments"][0]["reviewed_text"] == "Corrected Python experience"
    for source in (False, True):
        shown = []
        args = Namespace(command="cv-show", database=path, id=1, source=source)
        assert cv_cli.run_command(args, write=shown.append) == 0
        assert ("Original Python" if source else "Corrected Python") in "\n".join(shown)
    args = Namespace(command="cv-delete", database=path, id=1)
    assert cv_cli.run_command(args, scripted(["n"]), output.append) == 0
    with storage.database(path) as connection:
        assert len(storage.list_cvs(connection)) == 1
    assert cv_cli.run_command(args, scripted(["yes"]), output.append) == 0
    with storage.database(path) as connection:
        assert storage.list_cvs(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM cv_segments").fetchone()[0] == 0
    assert cv.read_text() == "Original Python\nSQL"


@pytest.mark.parametrize("review", [["cancel"], ["done", "no"]])
def test_cancelled_import_leaves_no_cv_content(setup_store, review):
    path, profile, cv = setup_store
    args = Namespace(command="cv-import", database=path, profile=profile, path=cv)
    assert cv_cli.run_command(args, scripted(["", *review]), lambda text: None) == 0
    with storage.database(path) as connection:
        assert storage.list_cvs(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM cv_segments").fetchone()[0] == 0


def test_interrupted_review_does_not_save(setup_store):
    path, profile, cv = setup_store
    args = Namespace(command="cv-import", database=path, profile=profile, path=cv)
    reads = iter([""])
    def interrupted(prompt):
        try:
            return next(reads)
        except StopIteration:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        cv_cli.run_command(args, interrupted, lambda text: None)
    with storage.database(path) as connection:
        assert storage.list_cvs(connection) == []


def test_profile_create_requires_confirmation(tmp_path):
    path = tmp_path / "profiles.sqlite3"
    args = Namespace(command="profile-create", database=path)
    output = []
    assert cv_cli.run_command(args, scripted(["Demo", "Python, ML", "n"]), output.append) == 0
    assert not path.exists()
    assert cv_cli.run_command(args, scripted(["Demo", "Python, ML", "yes"]), output.append) == 0
    with storage.database(path) as connection:
        assert storage.get_profile(connection, 1)["skills"] == ["python", "machine learning"]


@pytest.mark.parametrize("command", ["profile-list", "cv-list"])
def test_empty_list_commands(tmp_path, command):
    output = []
    args = Namespace(command=command, database=tmp_path / "empty.sqlite3", profile=None)
    assert cv_cli.run_command(args, write=output.append) == 0
    assert "No " in "\n".join(output)


def test_missing_profile_prevents_file_read(setup_store, monkeypatch):
    path, profile, cv = setup_store
    monkeypatch.setattr(cv_cli, "extract_document", lambda *a: pytest.fail("Must not read a CV for invalid profile"))
    output = []
    args = Namespace(command="cv-import", database=path, profile=999, path=cv)
    assert cv_cli.run_command(args, write=output.append) == 1
    assert "Profile not found" in "\n".join(output)


def test_invalid_document_not_stored(setup_store):
    path, profile, cv = setup_store
    cv.write_bytes(b"\xff\xfe")
    output = []
    args = Namespace(command="cv-import", database=path, profile=profile, path=cv)
    assert cv_cli.run_command(args, write=output.append) == 1
    assert "UTF-8" in "\n".join(output)
    with storage.database(path) as connection:
        assert storage.list_cvs(connection) == []


def test_clear_all_text_requires_correction_before_confirmation():
    document = ExtractedDocument("demo.txt", "txt", 4, "a" * 64, "test", [Segment("line 1", "demo", "demo")])
    output = []
    answers = ["1", "/done", "done", "1", "Corrected", "/done", "done", "y"]
    assert cv_cli.review_document(document, scripted(answers), output.append)
    assert "No readable text" in "\n".join(output)
    assert document.segments[0].source_text == "demo"
    assert document.segments[0].reviewed_text == "Corrected"


def test_control_characters_are_escaped():
    assert cv_cli.safe_display("Text\x1b[2J\u202e\x07\n") == "Text\\u001b[2J\\u202e\\u0007\n"


def test_database_error_does_not_expose_exception_content(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("SYNTHETIC_PRIVATE_MARKER")
    monkeypatch.setattr(storage, "database", fail)
    output = []
    args = Namespace(command="profile-list", database=tmp_path / "test.sqlite3")
    assert cv_cli.run_command(args, write=output.append) == 1
    assert "SYNTHETIC_PRIVATE_MARKER" not in "\n".join(output)


def test_main_dispatch_and_interruption(tmp_path, monkeypatch, capsys):
    def interrupted(args):
        assert args.command == "cv-import"
        assert args.profile == 2
        raise EOFError
    monkeypatch.setattr(cv_cli, "run_command", interrupted)
    assert cli.main(["--database", str(tmp_path / "db.sqlite3"), "cv-import", "synthetic.txt", "--profile", "2"]) == 130
    assert "Session ended" in capsys.readouterr().out


def test_real_cv_cli_entry_point(tmp_path):
    project = Path(__file__).resolve().parents[1]
    database = tmp_path / "demo.sqlite3"
    cv = tmp_path / "demo.txt"
    cv.write_text("Synthetic Candidate\nPython and SQL")
    base = [sys.executable, "-B", str(project / "main.py"), "--database", str(database)]
    def run(args, answers=""):
        result = subprocess.run(base + args, input=answers, text=True, capture_output=True, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    assert "Profile saved" in run(["profile-create"], "Demo\nPython\ny\n")
    assert "Reviewed CV saved" in run(["cv-import", str(cv), "--profile", "1"], "\ndone\ny\n")
    assert "demo.txt" in run(["cv-list"])
    assert "Python and SQL" in run(["cv-show", "1"])
    assert "deleted" in run(["cv-delete", "1"], "y\n")
    assert "No CVs" in run(["cv-list"])
