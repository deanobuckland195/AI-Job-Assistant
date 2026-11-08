from argparse import Namespace
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import cli, job_cli, storage
from job_assistant.documents import ExtractedDocument, Segment


def scripted(answers):
    values = iter(answers)
    return lambda prompt: next(values)


@pytest.fixture
def setup_comparison(tmp_path):
    database = tmp_path / "synthetic.sqlite3"
    with storage.database(database) as connection:
        profile = storage.create_profile(connection, "Synthetic Profile", ["sql"])
        document = ExtractedDocument("synthetic.txt", "txt", 50, "a" * 64, "fixture",
                                     [Segment("page 1", "Skills: Python", "Skills: Python")])
        cv_id = storage.save_cv(connection, profile, "Synthetic CV", document)
    job = tmp_path / "synthetic-job.txt"
    job.write_text("Essential:\nPython required\nSQL required\nDesirable:\nDocker")
    return Namespace(database=database, id=cv_id, job_file=job, output=None)


def test_local_file_comparison_preserves_database_and_uses_cv_not_profile(setup_comparison):
    args = setup_comparison
    before = args.database.read_bytes()
    output = []
    assert job_cli.run_comparison(args, write=output.append) == 0
    report = "\n".join(output)
    assert "MATCHED (1 item)" in report
    assert "MISSING (2 items)" in report
    assert "Job [unit" in report and "CV [unit" in report
    assert "SQL" in report
    assert args.database.read_bytes() == before


def test_multiline_cli_entry_with_blanks(setup_comparison):
    args = setup_comparison
    args.job_file = None
    output = []
    answers = ["Essential:", "", "Python required", "/done"]
    assert job_cli.run_comparison(args, scripted(answers), output.append) == 0
    assert "MATCHED (1 item)" in "\n".join(output)


def test_explicit_save_is_exact_displayed_report(setup_comparison, tmp_path):
    args = setup_comparison
    args.output = tmp_path / "comparison.txt"
    output = []
    assert job_cli.run_comparison(args, scripted(["y"]), output.append) == 0
    assert args.output.read_text() == output[0]


def test_declined_save_and_existing_file_safety(setup_comparison, tmp_path):
    args = setup_comparison
    args.output = tmp_path / "comparison.txt"
    assert job_cli.run_comparison(args, scripted(["no"]), lambda text: None) == 0
    assert not args.output.exists()
    args.output.write_text("Existing synthetic report")
    assert job_cli.run_comparison(args, scripted(["yes"]), lambda text: None) == 1
    assert args.output.read_text() == "Existing synthetic report"


def test_save_failure_is_safe(setup_comparison, tmp_path, monkeypatch):
    args = setup_comparison
    args.output = tmp_path / "comparison.txt"
    def fail(*a, **kw):
        raise OSError("PRIVATE_MARKER")
    monkeypatch.setattr(job_cli, "save_cv_report", fail)
    output = []
    assert job_cli.run_comparison(args, scripted(["yes"]), output.append) == 1
    assert "could not be saved" in "\n".join(output)
    assert "PRIVATE_MARKER" not in "\n".join(output)


def test_missing_cv_does_not_read_job_file(setup_comparison, monkeypatch):
    args = setup_comparison
    args.id = 999
    monkeypatch.setattr(job_cli, "import_job", lambda *a: pytest.fail("Invalid CV must stop import"))
    output = []
    assert job_cli.run_comparison(args, write=output.append) == 1
    assert "CV not found" in "\n".join(output)


@pytest.mark.parametrize("content", ["", "x" * 1001, "Python\x00"])
def test_invalid_jobs_are_clear_without_cv_export(setup_comparison, content):
    args = setup_comparison
    args.job_file.write_text(content)
    output = []
    assert job_cli.run_comparison(args, write=output.append) == 1
    assert "=== Explainable" not in "\n".join(output)


def test_network_never_requested_even_with_key(setup_comparison, monkeypatch):
    from job_assistant import openai_analysis
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_UNUSED_KEY")
    monkeypatch.setattr(openai_analysis, "request_assistance", lambda *a, **k: pytest.fail("Phase 2A is offline"))
    assert job_cli.run_comparison(setup_comparison, write=lambda text: None) == 0


def test_dispatch_and_interruption(setup_comparison, monkeypatch):
    def interrupted(args):
        assert args.id == setup_comparison.id
        raise EOFError
    monkeypatch.setattr(job_cli, "run_comparison", interrupted)
    assert cli.main(["--database", str(setup_comparison.database), "job-compare", str(setup_comparison.id)]) == 130


def test_safe_database_errors(setup_comparison, monkeypatch):
    def fail(*a, **k):
        raise OSError("PRIVATE_MARKER")
    monkeypatch.setattr(storage, "database", fail)
    output = []
    assert job_cli.run_comparison(setup_comparison, write=output.append) == 1
    assert "PRIVATE_MARKER" not in "\n".join(output)


def test_real_cli_comparison(setup_comparison, tmp_path):
    args = setup_comparison
    project = Path(__file__).resolve().parents[1]
    export = tmp_path / "comparison.txt"
    result = subprocess.run([sys.executable, "-B", str(project / "main.py"), "--database", str(args.database),
                             "job-compare", str(args.id), "--job-file", str(args.job_file), "--output", str(export)],
                            input="yes\n", text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCHED (1 item)" in export.read_text()
    assert "MISSING (2 items)" in export.read_text()
    assert "Score:" not in export.read_text()
