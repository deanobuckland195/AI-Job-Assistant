from argparse import Namespace
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import analysis_cli, cli, openai_analysis, storage
from job_assistant.cv_analysis import AnalysisError
from job_assistant.cv_analysis_report import save_cv_report
from job_assistant.documents import ExtractedDocument, Segment


def scripted(answers):
    values = iter(answers)
    return lambda prompt: next(values)


@pytest.fixture
def saved_cv(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    document = ExtractedDocument("synthetic.txt", "txt", 50, "a" * 64, "synthetic extractor", [
        Segment("line 1", "Skills: Rust", "Skills: Python"),
        Segment("line 2", "Projects\nBuilt a Python service", "Projects\nBuilt a Python service"),
    ])
    with storage.database(path) as connection:
        profile = storage.create_profile(connection, "Synthetic", [])
        cv_id = storage.save_cv(connection, profile, "Synthetic CV", document)
    return Namespace(database=path, id=cv_id, openai=False, model=None, output=None)


def test_offline_has_no_key_or_connection_dependency(saved_cv, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai_analysis, "request_assistance", lambda *a, **k: pytest.fail("Offline must not call AI"))
    output = []
    assert analysis_cli.run_analysis(saved_cv, write=output.append) == 0
    report = "\n".join(output)
    assert "Mention: python" in report and "corrected text" in report
    assert "CANNOT BE DETERMINED" in report
    assert "IMPROVEMENT SUGGESTIONS" in report


def test_export_requires_review_confirmation_and_is_exactly_displayed(saved_cv, tmp_path):
    saved_cv.output = tmp_path / "new" / "analysis.txt"
    output = []
    assert analysis_cli.run_analysis(saved_cv, scripted(["yes"]), output.append) == 0
    assert saved_cv.output.read_text() == output[0]
    with storage.database(saved_cv.database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION
        assert storage.get_cv(connection, saved_cv.id)["segments"][0]["source_text"] == "Skills: Rust"


def test_declining_export_creates_no_report(saved_cv, tmp_path):
    saved_cv.output = tmp_path / "not-saved.txt"
    assert analysis_cli.run_analysis(saved_cv, scripted(["n"]), lambda text: None) == 0
    assert not saved_cv.output.exists()


@pytest.mark.parametrize("consent", ["", "yes", "send", "no"])
def test_opt_in_flag_alone_never_sends(saved_cv, monkeypatch, consent):
    saved_cv.openai = True
    saved_cv.model = "explicit-test-model"
    monkeypatch.setattr(openai_analysis, "request_assistance", lambda *a, **k: pytest.fail("Must type SEND"))
    output = []
    assert analysis_cli.run_analysis(saved_cv, scripted([consent]), output.append) == 0
    assert "may incur API charges" in "\n".join(output)
    assert "including any personal data" in "\n".join(output)
    assert "request declined" in "\n".join(output)


def test_explicit_send_calls_assistance_once(saved_cv, monkeypatch):
    saved_cv.openai = True
    saved_cv.model = "explicit-test-model"
    calls = []
    def assistance(cv, model, consent):
        calls.append((cv["id"], model, consent))
        return []
    monkeypatch.setattr(openai_analysis, "request_assistance", assistance)
    assert analysis_cli.run_analysis(saved_cv, scripted(["SEND"]), lambda text: None) == 0
    assert calls == [(saved_cv.id, "explicit-test-model", True)]


def test_model_failure_keeps_offline_report_and_allows_export(saved_cv, tmp_path, monkeypatch):
    saved_cv.openai = True
    saved_cv.model = "explicit-test-model"
    saved_cv.output = tmp_path / "fallback.txt"
    def fail(*args, **kwargs):
        raise AnalysisError("OpenAI authentication failed. Offline analysis is retained.")
    monkeypatch.setattr(openai_analysis, "request_assistance", fail)
    assert analysis_cli.run_analysis(saved_cv, scripted(["SEND", "yes"]), lambda text: None) == 0
    text = saved_cv.output.read_text()
    assert "Mention: python" in text
    assert "authentication failed" in text


def test_model_required_before_request_prompt(saved_cv):
    saved_cv.openai = True
    output = []
    assert analysis_cli.run_analysis(saved_cv, lambda prompt: pytest.fail("No request possible"), output.append) == 0
    assert "--model" in "\n".join(output)


def test_missing_cv_is_clear(saved_cv):
    saved_cv.id = 999
    output = []
    assert analysis_cli.run_analysis(saved_cv, write=output.append) == 1
    assert "CV not found" in "\n".join(output)


def test_existing_report_never_overwritten(saved_cv, tmp_path):
    saved_cv.output = tmp_path / "existing.txt"
    saved_cv.output.write_text("Existing synthetic report")
    assert analysis_cli.run_analysis(saved_cv, scripted(["y"]), lambda text: None) == 1
    assert saved_cv.output.read_text() == "Existing synthetic report"
    assert not list(tmp_path.glob(".cv-analysis-*.tmp"))


def test_atomic_export_failure_cleans_temporary_file(tmp_path, monkeypatch):
    from job_assistant import cv_analysis_report
    path = tmp_path / "new.txt"
    def fail(*args):
        raise OSError("Synthetic filesystem failure")
    monkeypatch.setattr(cv_analysis_report.os, "link", fail)
    with pytest.raises(OSError):
        save_cv_report("Synthetic report", path)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_export_symlink_never_replaced_or_followed(tmp_path):
    target = tmp_path / "existing.txt"
    target.write_text("Synthetic existing content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        save_cv_report("Synthetic new content", link)
    assert link.is_symlink()
    assert target.read_text() == "Synthetic existing content"


def test_command_dispatch_and_interruption(saved_cv, monkeypatch):
    def interrupted(args):
        assert args.id == saved_cv.id
        raise KeyboardInterrupt
    monkeypatch.setattr(analysis_cli, "run_analysis", interrupted)
    assert cli.main(["--database", str(saved_cv.database), "cv-analyse", str(saved_cv.id)]) == 130


def test_real_offline_cv_analysis_entry_point(saved_cv, tmp_path):
    project = Path(__file__).resolve().parents[1]
    report = tmp_path / "real-cli-report.txt"
    result = subprocess.run([sys.executable, "-B", str(project / "main.py"), "--database", str(saved_cv.database),
                             "cv-analyse", str(saved_cv.id), "--output", str(report)],
                            input="yes\n", text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Evidence-based CV Analysis" in result.stdout
    assert "Mention: python" in report.read_text()
    assert "line 1" in report.read_text()


def test_database_read_errors_do_not_expose_private_details(saved_cv, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_MARKER")
    monkeypatch.setattr(storage, "database", fail)
    output = []
    assert analysis_cli.run_analysis(saved_cv, write=output.append) == 1
    assert "PRIVATE_MARKER" not in "\n".join(output)
