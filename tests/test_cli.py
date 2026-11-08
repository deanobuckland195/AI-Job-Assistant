import os
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import cli

PROJECT = Path(__file__).resolve().parents[1]


def scripted(answers):
    values = iter(answers)
    return lambda prompt: next(values)


def test_validation_and_two_job_session(tmp_path):
    output = []
    path = tmp_path / "reports.txt"
    answers = ["", "Demo User", " , , ", " PYTHON,ml,python ", "", "Python and SQL",
               "maybe", " Y ", "Machine-learning and Python", " N "]
    assert cli.run_session(path, read=scripted(answers), write=output.append) == 0
    text = "\n".join(output)
    assert "blank input" in text
    assert "at least one skill" in text
    assert "yes/y or no/n" in text
    assert "Job Match Score: 50%" in text
    assert "Job Match Score: 100%" in text
    assert "Report #2" in path.read_text()


def test_no_skills_and_multiline(tmp_path):
    path = tmp_path / "reports.txt"
    answers = ["Demo", "none", "Python required", "SQL desirable", "", "no"]
    output = []
    assert cli.run_session(path, True, scripted(answers), output.append) == 0
    text = path.read_text()
    assert "- python" in text and "- sql" in text
    assert "Job Match Score: 0%" in text


def test_save_error_is_clear_and_not_reported_as_success(tmp_path):
    path = tmp_path / "directory"
    path.mkdir()
    output = []
    assert cli.run_session(path, read=scripted(["Demo", "python", "Python", "n"]),
                           write=output.append) == 1
    text = "\n".join(output)
    assert "Could not save report" in text
    assert "Job Match Score: 100%" in text
    assert "has been saved" not in text


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_interruption_exits_cleanly(monkeypatch, capsys, error):
    def interrupted(*args):
        raise error
    monkeypatch.setattr(cli, "run_session", interrupted)
    assert cli.main([]) == 130
    assert "Session ended" in capsys.readouterr().out


def test_default_path_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.DEFAULT_REPORT_PATH == PROJECT / "job_analysis.txt"


def test_import_has_no_prompts_or_file_writes(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(PROJECT)}
    result = subprocess.run([sys.executable, "-B", "-c", "import main"], cwd=tmp_path,
                            env=env, input="", text=True, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_existing_entry_point_from_another_directory(tmp_path):
    path = tmp_path / "demo.txt"
    result = subprocess.run(
        [sys.executable, "-B", str(PROJECT / "main.py"), "--report", str(path)],
        cwd=tmp_path, input="Demo User\nPython, ML\nPython and SQL\ny\nML and Python\nn\n",
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Job Match Score: 50%" in result.stdout
    assert "Job Match Score: 100%" in result.stdout
    assert "Report #2" in path.read_text()
