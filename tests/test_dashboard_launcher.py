from pathlib import Path
from types import SimpleNamespace

import pytest

from job_assistant import dashboard_launcher as launcher


def test_launcher_forces_local_defaults_and_explicit_database(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: True)
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    def fake(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(launcher.subprocess, "run", fake)
    path = tmp_path / "synthetic.sqlite3"
    assert launcher.main(["--database", str(path), "--port", "8512"]) == 0
    command, options = calls[0]
    assert "--server.address=127.0.0.1" in command and "--server.port=8512" in command
    assert "--browser.gatherUsageStats=false" in command
    assert "--server.enableXsrfProtection=true" in command
    assert options["env"]["AI_JOB_ASSISTANT_DATABASE"] == str(path)
    assert Path(options["cwd"]) == Path(__file__).resolve().parents[1]


def test_missing_dashboard_dependency_explains_install(monkeypatch, capsys):
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: None)
    assert launcher.main([]) == 1
    assert "requirements-dashboard.txt" in capsys.readouterr().out


@pytest.mark.parametrize("port", ["0", "65536"])
def test_bad_port_rejected_without_launch(port):
    with pytest.raises(SystemExit):
        launcher.main(["--port", port])


def test_server_failure_is_friendly(monkeypatch, capsys):
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: True)
    def fail(*args, **kwargs):
        raise OSError("PRIVATE_ERROR")
    monkeypatch.setattr(launcher.subprocess, "run", fail)
    assert launcher.main([]) == 1
    assert "PRIVATE_ERROR" not in capsys.readouterr().out
