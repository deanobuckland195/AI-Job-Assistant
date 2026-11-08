from datetime import datetime

import pytest

from job_assistant import reports
from job_assistant.skills import analyse_job


def test_first_run_and_second_save(tmp_path):
    path = tmp_path / "new" / "reports.txt"
    analysis = analyse_job(["python"], "Python and SQL")
    when = datetime(2026, 11, 8, 10, 15)
    assert reports.save_analysis(analysis, path, when) == 1
    first = path.read_text()
    assert "08 November 2026" in first
    assert "10:15" in first
    assert "Job Match Score: 50%" in first
    assert reports.save_analysis(analysis, path, when) == 2
    assert path.read_text().startswith(first)
    assert "Report #2" in path.read_text()


@pytest.mark.parametrize("previous, expected", [
    ("Legacy content\n", 1),
    (f"{reports.REPORT_TITLE}\n{reports.REPORT_TITLE}\n", 3),
    (f"{reports.REPORT_TITLE} #8\n", 9),
])
def test_legacy_content_preserved(tmp_path, previous, expected):
    path = tmp_path / "reports.txt"
    path.write_text(previous)
    assert reports.save_analysis(analyse_job([], "SQL"), path) == expected
    assert path.read_text().startswith(previous)


def test_replace_failure_preserves_previous_report(tmp_path, monkeypatch):
    path = tmp_path / "reports.txt"
    original = b"Existing synthetic report\n"
    path.write_bytes(original)

    def fail(*args):
        raise PermissionError("Synthetic replacement failure")

    monkeypatch.setattr(reports.os, "replace", fail)
    with pytest.raises(PermissionError):
        reports.save_analysis(analyse_job([], "SQL"), path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_write_failure_preserves_previous_report(tmp_path, monkeypatch):
    path = tmp_path / "reports.txt"
    path.write_text("Previous content")

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(reports.os, "fsync", fail)
    with pytest.raises(OSError):
        reports.save_analysis(analyse_job([], "SQL"), path)
    assert path.read_text() == "Previous content"
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_existing_encoding_is_not_overwritten(tmp_path):
    path = tmp_path / "reports.txt"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeError):
        reports.save_analysis(analyse_job([], "SQL"), path)
    assert path.read_bytes() == b"\xff\xfe"


def test_unknown_job_does_not_claim_no_gaps():
    text = reports.format_analysis(analyse_job([], "Kubernetes"))
    assert "Job Match Score: N/A" in text
    assert "No missing recognised skills!" not in text
    assert "Unknown - no recognised requirements" in text


def test_fallback_plan_is_in_shared_output():
    analysis = analyse_job([], "Git")
    assert "Research beginner tutorials for this skill" in reports.format_analysis(analysis)


@pytest.mark.parametrize("score, phrase", [
    (100, "Excellent"), (80, "Excellent"), (60, "Good"),
    (40, "Possible"), (0, "Low"), (None, "unable to calculate"),
])
def test_recommendation_boundaries(score, phrase):
    analysis = analyse_job([], "SQL")
    analysis.score = score
    assert phrase in reports.recommendation(analysis)
