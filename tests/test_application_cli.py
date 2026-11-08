from pathlib import Path
import json
import subprocess
import sys

import pytest

from job_assistant import application_cli, applications as apps, cli, comparison_records, job_cli, storage


def args_for(path, command):
    result = cli_parser_args(command)
    result.database = path
    return result


def cli_parser_args(command):
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    application_cli.register_commands(subparsers)
    return parser.parse_args(command)


def scripted(values):
    answers = iter(values)
    return lambda prompt: next(answers)


def test_create_review_confirm_cancel_update_show_and_delete(tmp_path):
    path = tmp_path / "cli.sqlite3"
    args = args_for(path, ["application-create", "--company", "Synthetic Ltd", "--role", "Apprentice", "--deadline", "2099-12-31"])
    output = []
    assert application_cli.run_command(args, scripted(["no"]), output.append) == 0
    with storage.database(path) as connection:
        assert apps.list_applications(connection) == []
    assert application_cli.run_command(args, scripted(["yes"]), output.append) == 0
    assert "Application saved with ID 1" in "\n".join(output)
    update = args_for(path, ["application-update", "1", "--status", "applied", "--application-date", "2020-01-01"])
    assert application_cli.run_command(update, scripted(["yes"]), output.append) == 0
    show = args_for(path, ["application-show", "1"])
    assert application_cli.run_command(show, write=output.append) == 0
    assert "saved -> applied" in "\n".join(output)
    delete = args_for(path, ["application-delete", "1"])
    assert application_cli.run_command(delete, scripted(["no"]), output.append) == 0
    with storage.database(path) as connection:
        assert apps.get_application(connection, 1)["status"] == "applied"
    assert application_cli.run_command(delete, scripted(["yes"]), output.append) == 0
    with storage.database(path) as connection:
        assert apps.list_applications(connection) == []


def test_cli_export_is_confirmed_private_and_never_overwrites(tmp_path):
    path = tmp_path / "cli.sqlite3"
    with storage.database(path) as connection:
        apps.create_application(connection, company="Demo", role="Role", notes="PRIVATE_NOTES")
    target = tmp_path / "applications.json"
    args = args_for(path, ["application-export", "--output", str(target)])
    assert application_cli.run_command(args, scripted(["no"]), lambda text: None) == 0
    assert not target.exists()
    assert application_cli.run_command(args, scripted(["yes"]), lambda text: None) == 0
    original = target.read_text()
    assert "PRIVATE_NOTES" not in original
    assert len(json.loads(original)["applications"]) == 1
    assert application_cli.run_command(args, scripted(["yes"]), lambda text: None) == 1
    assert target.read_text() == original


@pytest.mark.parametrize("arguments", [
    ["application-create", "--company", "", "--role", "Role"],
    ["application-create", "--company", "Demo", "--role", "Role", "--deadline", "2026-02-30"],
    ["application-create", "--company", "Demo", "--role", "Role", "--application-date", "9999-01-01"],
    ["application-update", "1"], ["application-show", "999"], ["application-delete", "999"],
    ["application-update", "1", "--cv", "1", "--clear-links"],
])
def test_invalid_cli_input_fails_before_confirmation(tmp_path, arguments):
    args = args_for(tmp_path / "cli.sqlite3", arguments)
    output = []
    assert application_cli.run_command(args, lambda prompt: pytest.fail("No confirmation for invalid input"), output.append) == 1


def test_cancelled_update_and_interruption_do_not_write(tmp_path, monkeypatch):
    path = tmp_path / "cli.sqlite3"
    with storage.database(path) as connection:
        app_id = apps.create_application(connection, company="Demo", role="Role")
    args = args_for(path, ["application-update", str(app_id), "--status", "rejected"])
    assert application_cli.run_command(args, scripted(["no"]), lambda text: None) == 0
    def interrupt(prompt):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        application_cli.run_command(args, interrupt, lambda text: None)
    with storage.database(path) as connection:
        assert apps.get_application(connection, app_id)["status"] == "saved"


def test_stale_cli_review_cannot_clobber_concurrent_edit(tmp_path):
    path = tmp_path / "cli.sqlite3"
    with storage.database(path) as connection:
        apps.create_application(connection, company="Demo", role="Role")
    args = args_for(path, ["application-update", "1", "--notes", "Old review"])
    def concurrent_change(prompt):
        with storage.database(path) as connection:
            apps.update_application(connection, 1, {"notes": "Newer edit"})
        return "yes"
    output = []
    assert application_cli.run_command(args, concurrent_change, output.append) == 1
    assert "changed since review" in "\n".join(output)
    with storage.database(path) as connection:
        assert apps.get_application(connection, 1)["notes"] == "Newer edit"


def test_safe_error_messages_do_not_echo_exception_content(tmp_path, monkeypatch):
    def fail(*a, **kw):
        raise OSError("PRIVATE_MARKER")
    monkeypatch.setattr(storage, "database", fail)
    output = []
    args = args_for(tmp_path / "cli.sqlite3", ["application-list"])
    assert application_cli.run_command(args, write=output.append) == 1
    assert "PRIVATE_MARKER" not in "\n".join(output)


def test_command_dispatch_and_interruption(monkeypatch):
    def interrupt(args):
        assert args.command == "application-list"
        raise EOFError
    monkeypatch.setattr(application_cli, "run_command", interrupt)
    assert cli.main(["application-list"]) == 130


def test_synthetic_real_cli_lifecycle_and_export(tmp_path):
    project = Path(__file__).resolve().parents[1]
    path = tmp_path / "cli.sqlite3"
    base = [sys.executable, "-B", str(project / "main.py"), "--database", str(path)]
    def run(command, answers=""):
        result = subprocess.run(base + command, input=answers, text=True, capture_output=True, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    assert "Application saved" in run(["application-create", "--company", "Synthetic Ltd", "--role", "Apprentice"], "yes\n")
    run(["application-update", "1", "--status", "applied", "--application-date", "2020-01-01"], "yes\n")
    run(["application-update", "1", "--status", "interviewing", "--next-action", "Practise interview"], "yes\n")
    assert "Synthetic Ltd" in run(["application-list", "--status", "interviewing"])
    assert "applied -> interviewing" in run(["application-show", "1"])
    export = tmp_path / "applications.json"
    run(["application-export", "--output", str(export), "--include-history"], "yes\n")
    assert len(json.loads(export.read_text())["applications"][0]["history"]) == 3
    run(["application-delete", "1"], "yes\n")
    assert "Listed 0" in run(["application-list"])


def test_real_comparison_storage_and_application_link_journey(tmp_path):
    project = Path(__file__).resolve().parents[1]
    database = tmp_path / "linked.sqlite3"
    base = [sys.executable, "-B", str(project / "main.py"), "--database", str(database)]
    cv = tmp_path / "cv.txt"
    cv.write_text("Skills: Python\nSYNTHETIC_PRIVATE_CV_MARKER")
    job = tmp_path / "job.txt"
    job.write_text("Python required")
    def run(command, answers=""):
        result = subprocess.run(base + command, input=answers, text=True, capture_output=True, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    run(["profile-create"], "Synthetic\nPython\ny\n")
    run(["cv-import", str(cv), "--profile", "1"], "\ndone\ny\n")
    assert "Comparison metadata saved with ID 1" in run(["job-compare", "1", "--job-file", str(job), "--store"], "yes\n")
    assert "Listed 1 comparison" in run(["comparison-list"])
    assert "SYNTHETIC_PRIVATE_CV_MARKER" not in run(["comparison-show", "1"])
    run(["application-create", "--company", "Synthetic", "--role", "Engineer", "--comparison", "1"], "yes\n")
    assert "CV version: original ID 1" in run(["application-show", "1"])
    run(["comparison-delete", "1"], "yes\n")
    with storage.database(database) as connection:
        assert apps.get_application(connection, 1)["comparison_id"] is None
        assert storage.get_cv(connection, 1)["segments"][1]["reviewed_text"] == "SYNTHETIC_PRIVATE_CV_MARKER"
    run(["application-update", "1", "--clear-links"], "yes\n")
    with storage.database(database) as connection:
        assert apps.get_application(connection, 1)["cv_digest"] is None


def test_store_comparison_is_explicit_and_failure_keeps_report_available(tmp_path, monkeypatch):
    from argparse import Namespace
    from job_assistant.documents import ExtractedDocument, Segment
    path = tmp_path / "store.sqlite3"
    with storage.database(path) as connection:
        profile = storage.create_profile(connection, "Synthetic", [])
        cv_id = storage.save_cv(connection, profile, "Synthetic", ExtractedDocument("cv.txt", "txt", 6, "a" * 64, "fixture", [Segment("line 1", "Python", "Python")]))
    job = tmp_path / "job.txt"
    job.write_text("Python required")
    args = Namespace(database=path, id=cv_id, job_file=job, output=None, store=True)
    assert job_cli.run_comparison(args, scripted(["no"]), lambda text: None) == 0
    with storage.database(path) as connection:
        assert comparison_records.list_comparisons(connection) == []
    def fail(*a, **kw):
        raise OSError("PRIVATE_ERROR_DETAILS")
    monkeypatch.setattr(comparison_records, "save_comparison", fail)
    args.output = tmp_path / "comparison.txt"
    output = []
    assert job_cli.run_comparison(args, scripted(["yes", "yes"]), output.append) == 1
    assert args.output.exists()
    assert "MATCHED (1 item)" in args.output.read_text()
    assert "PRIVATE_ERROR_DETAILS" not in "\n".join(output)


def test_reproducible_synthetic_demo():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-B", "-m", "examples.application_tracking_demo"], cwd=project,
                            input="", text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"schema 1 -> {storage.SCHEMA_VERSION} migration preserved" in result.stdout
    assert "Temporary demo files removed" in result.stdout
