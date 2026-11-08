from argparse import Namespace
from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from job_assistant import cli, job_cli, openai_job_matching as ai, storage
from job_assistant.cv_analysis import AnalysisError
from job_assistant.documents import ExtractedDocument, Segment


def scripted(values):
    answers = iter(values)
    return lambda prompt: next(answers)


@pytest.fixture
def setup_ai(tmp_path):
    database = tmp_path / "synthetic.sqlite3"
    document = ExtractedDocument("synthetic.txt", "txt", 20, "a" * 64, "test",
                                 [Segment("page 1", "Skills: Kubernetes", "Skills: Kubernetes")])
    with storage.database(database) as connection:
        profile = storage.create_profile(connection, "Synthetic", [])
        cv_id = storage.save_cv(connection, profile, "Synthetic", document)
    job = tmp_path / "synthetic-job.txt"
    job.write_text("K8s required")
    return Namespace(database=database, id=cv_id, job_file=job, output=None, openai=True,
                     model="explicit-test-model", input_usd_per_million="1", output_usd_per_million="2", max_estimated_usd="0.25")


@pytest.mark.parametrize("consent", ["", "yes", "send", "NO"])
def test_flags_are_not_consent_and_warnings_precede_prompt(setup_ai, monkeypatch, consent):
    monkeypatch.setattr(ai, "request_matching", lambda *a, **k: pytest.fail("No explicit SEND"))
    output = []
    def read(prompt):
        assert "including personal/confidential data" in "\n".join(output)
        assert "Estimated conservative cost" in "\n".join(output)
        assert "not a guaranteed bill" in "\n".join(output)
        assert "retention" in "\n".join(output)
        return consent
    assert job_cli.run_comparison(setup_ai, read, output.append) == 0
    assert "AI request declined" in "\n".join(output)


def test_offline_does_not_read_rates_or_api_key(setup_ai, monkeypatch):
    setup_ai.openai = False
    setup_ai.input_usd_per_million = "invalid"
    monkeypatch.setattr(ai, "prepare_request", lambda *a: pytest.fail("Offline branch"))
    assert job_cli.run_comparison(setup_ai, write=lambda text: None) == 0


@pytest.mark.parametrize("field, value", [
    ("model", None), ("input_usd_per_million", None), ("output_usd_per_million", "NaN"),
    ("max_estimated_usd", "0.000001"),
])
def test_preflight_failures_keep_offline_report_without_consent_prompt(setup_ai, field, value):
    setattr(setup_ai, field, value)
    output = []
    assert job_cli.run_comparison(setup_ai, lambda prompt: pytest.fail("No transmissible request"), output.append) == 0
    assert "AI assistance unavailable" in "\n".join(output)
    assert "UNSUPPORTED (1 item)" in "\n".join(output)


def test_validated_assistance_is_separate_and_export_preserves_data(setup_ai, tmp_path, monkeypatch):
    from job_assistant.ai_job_validation import validate_interpretations
    calls = []
    def assistance(cv, job, comparison, model, **kwargs):
        calls.append(kwargs)
        original = deepcopy(comparison.matches)
        payload = {"interpretations": [{"requirement": 1, "kind": "abbreviation", "skill": "kubernetes", "claim": "matched",
            "cv_evidence": {"position": 1, "start": 8, "end": 18, "quote": "Kubernetes"},
            "job_evidence": {"position": 1, "start": 0, "end": 3, "quote": "K8s"}}]}
        results = validate_interpretations(payload, cv, job, comparison, ai.ALLOWED_SKILLS)
        assert comparison.matches == original
        return results
    monkeypatch.setattr(ai, "request_matching", assistance)
    setup_ai.output = tmp_path / "ai-comparison.txt"
    before = setup_ai.database.read_bytes()
    output = []
    assert job_cli.run_comparison(setup_ai, scripted(["SEND", "yes"]), output.append) == 0
    assert len(calls) == 1 and calls[0]["consent"] is True
    report = setup_ai.output.read_text()
    assert "AI EVIDENCE-VALIDATED MATCHES (1)" in report
    assert "UNSUPPORTED (1 item)" in report  # Offline conclusion is not rewritten.
    assert "proposed=matched; validated=matched" in report
    assert "Origin: offline rules" in report
    assert setup_ai.database.read_bytes() == before
    displayed = [text for text in output if text.startswith("=== Explainable")]
    assert report == displayed[-1]


@pytest.mark.parametrize("failure", ["Provider timed out", "Malformed model output", "Citation validation failed"])
def test_provider_and_validation_failures_allow_offline_export(setup_ai, tmp_path, monkeypatch, failure):
    def fail(*a, **kw):
        raise AnalysisError(failure + "; offline comparison is retained.")
    monkeypatch.setattr(ai, "request_matching", fail)
    setup_ai.output = tmp_path / "fallback.txt"
    assert job_cli.run_comparison(setup_ai, scripted(["SEND", "yes"]), lambda text: None) == 0
    report = setup_ai.output.read_text()
    assert "AI assistance unavailable" in report
    assert failure in report
    assert "UNSUPPORTED (1 item)" in report
    assert "AI EVIDENCE-VALIDATED MATCHES (0)" in report


def test_cancelled_export_does_not_save(setup_ai, tmp_path):
    setup_ai.output = tmp_path / "cancelled.txt"
    assert job_cli.run_comparison(setup_ai, scripted(["", "no"]), lambda text: None) == 0
    assert not setup_ai.output.exists()


def test_new_arguments_parse_and_interrupt_safely(setup_ai, monkeypatch):
    def interrupted(args):
        assert args.openai is True
        assert args.input_usd_per_million == "1"
        assert args.output_usd_per_million == "2"
        assert args.max_estimated_usd == "0.25"
        raise KeyboardInterrupt
    monkeypatch.setattr(job_cli, "run_comparison", interrupted)
    assert cli.main(["job-compare", str(setup_ai.id), "--openai", "--model", "explicit-test-model",
                     "--input-usd-per-million", "1", "--output-usd-per-million", "2"]) == 130


def test_real_cli_declined_request_is_fully_local(setup_ai, tmp_path):
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-B", str(project / "main.py"), "--database", str(setup_ai.database),
                             "job-compare", str(setup_ai.id), "--job-file", str(setup_ai.job_file), "--openai",
                             "--model", "explicit-test-model", "--input-usd-per-million", "1", "--output-usd-per-million", "2"],
                            input="\n", text=True, capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Estimated conservative cost" in result.stdout
    assert "AI request declined" in result.stdout
