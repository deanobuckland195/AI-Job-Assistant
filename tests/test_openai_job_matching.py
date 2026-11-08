from decimal import Decimal
import http.client
import json

import pytest

from job_assistant import openai_job_matching as ai
from job_assistant.cv_analysis import AnalysisError
from job_assistant.job_matching import compare_job
from job_assistant.job_requirements import job_from_text


@pytest.fixture
def source():
    cv_text = "Skills: Kubernetes"
    cv = {"id": 1, "title": "PRIVATE_TITLE", "filename": "PRIVATE_FILE", "reviewed_at": "2026-11-08", "warnings": [],
          "segments": [{"position": 1, "reference": "PRIVATE_REFERENCE", "source_text": "PRIVATE_ORIGINAL", "reviewed_text": cv_text}]}
    job = job_from_text("K8s required")
    return cv, job, compare_job(cv, job)


def entry():
    return {"requirement": 1, "kind": "abbreviation", "skill": "kubernetes", "claim": "matched",
            "cv_evidence": {"position": 1, "start": 8, "end": 18, "quote": "Kubernetes"},
            "job_evidence": {"position": 1, "start": 0, "end": 3, "quote": "K8s"}}


def response(payload=None, status="completed"):
    return json.dumps({"status": status, "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(payload if payload is not None else {"interpretations": [entry()]})}]}]}).encode()


class Connection:
    def __init__(self, body=None, status=200, error=None):
        self.body = response() if body is None else body
        self.status, self.error = status, error
        self.calls, self.closed = [], False

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error

    def getresponse(self):
        return self

    def read(self, limit):
        return self.body[:limit]

    def close(self):
        self.closed = True


def test_minimal_strict_request_and_no_private_metadata(source):
    cv, job, comparison = source
    data = ai.prepare_request(cv, job, comparison, "explicit-test-model")
    request = json.loads(data)
    assert b"PRIVATE" not in data
    assert request["store"] is False
    assert request["max_output_tokens"] == 2400
    assert request["text"]["format"]["strict"] is True
    assert "tools" not in request
    units = json.loads(request["input"][0]["content"])
    assert units["untrusted_cv_units"][0]["text"] == cv["segments"][0]["reviewed_text"]
    assert units["untrusted_job_units"][0]["text"] == "K8s required"


def test_estimate_uses_supplied_rates_and_bounded_usage():
    estimate = ai.estimate_cost(b"x" * 1000, "1", "2", "1")
    assert estimate.input_token_proxy == 2024
    assert estimate.usd == Decimal("0.006824")


@pytest.mark.parametrize("rate", [None, "", "0", "-1", "NaN", "Infinity", "1e999999", "1e-999999", "not-a-price"])
def test_invalid_rates_fail_before_network(rate):
    with pytest.raises(AnalysisError):
        ai.estimate_cost(b"synthetic", rate, "1")
    with pytest.raises(AnalysisError):
        ai.estimate_cost(b"synthetic", "1", rate)


@pytest.mark.parametrize("budget", ["0", "NaN", "101", "-1"])
def test_invalid_budgets_rejected(budget):
    with pytest.raises(AnalysisError):
        ai.estimate_cost(b"x", "1", "1", budget)


def test_budget_refuses_expensive_request(source, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_UNUSED_KEY")
    with pytest.raises(AnalysisError, match="exceeds"):
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", max_usd="0.000001",
                            consent=True, connection_factory=lambda *a, **k: pytest.fail("Over budget"))


def test_no_consent_never_reads_key_or_connects(source, monkeypatch):
    with pytest.raises(AnalysisError, match="consent"):
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1",
                            connection_factory=lambda *a, **k: pytest.fail("No consent"))


def test_no_key_is_safe(source, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AnalysisError, match="OPENAI_API_KEY"):
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True,
                            connection_factory=lambda *a, **k: pytest.fail("No key"))


def test_success_uses_shared_bounded_transport_and_local_validator(source, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    connection = Connection()
    hosts = []
    def factory(host, timeout):
        hosts.append((host, timeout))
        return connection
    results = ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True, connection_factory=factory)
    assert hosts == [("api.openai.com", 30)]
    assert len(connection.calls) == 1
    assert results[0].status == "matched"
    assert source[2].matches[0].status == "unsupported"
    assert connection.closed


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_provider_failures_never_retry_or_echo_private_body(source, monkeypatch, status, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE_KEY")
    connection = Connection(body=b"PRIVATE_BODY", status=status)
    with pytest.raises(AnalysisError) as caught:
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True,
                            connection_factory=lambda *a, **k: connection)
    assert len(connection.calls) == 1
    assert connection.closed
    assert "PRIVATE" not in str(caught.value) + caplog.text


@pytest.mark.parametrize("error", [TimeoutError("PRIVATE"), OSError("PRIVATE"), http.client.HTTPException("PRIVATE")])
def test_network_failures_are_safe(source, monkeypatch, error):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    connection = Connection(error=error)
    with pytest.raises(AnalysisError, match="connection failed") as caught:
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True,
                            connection_factory=lambda *a, **k: connection)
    assert "PRIVATE" not in str(caught.value)
    assert connection.closed


@pytest.mark.parametrize("data", [
    b"not-json", b"\xff", response(status="incomplete"), response([]), response({"facts": ["Invented"]}),
    response({"interpretations": "invalid"}), response({"interpretations": [dict(entry(), qualification="PhD")]}),
    b'{"status":"completed","output":[{"type":"message","content":[{"type":"refusal","refusal":"PRIVATE"}]}]}',
    b'{"status":"completed","output":[{"type":"function_call","name":"read_private_files"}]}',
    b'{"status":"completed","output":null}',
])
def test_bad_output_returns_safe_failure_and_no_partial_result(source, data):
    with pytest.raises(AnalysisError, match="retained"):
        ai.parse_response(data, *source)


def test_duplicate_json_keys_rejected(source):
    data = json.dumps({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"interpretations":[],"interpretations":[]}'}]}]}).encode()
    with pytest.raises(AnalysisError):
        ai.parse_response(data, *source)


def test_response_size_limit(source, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    connection = Connection(body=b"x" * 65537)
    with pytest.raises(AnalysisError, match="size limit"):
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True,
                            connection_factory=lambda *a, **k: connection)


def test_input_limits_and_snapshot_binding(source, monkeypatch):
    cv, job, comparison = source
    cv["segments"][0]["reviewed_text"] = "x" * 12001
    with pytest.raises(AnalysisError, match="12,000"):
        ai.prepare_request(cv, job, comparison, "explicit-test-model")
    cv["segments"][0]["reviewed_text"] = "Changed synthetic CV"
    with pytest.raises(AnalysisError, match="changed"):
        ai.prepare_request(cv, job, comparison, "explicit-test-model")


def test_job_limits_and_encoded_request_limit(source, monkeypatch):
    cv, job, comparison = source
    oversized = job_from_text(("x" * 100 + "\n") * 80)
    with pytest.raises(AnalysisError, match="8,000"):
        ai.prepare_request(cv, oversized, comparison, "explicit-test-model")
    monkeypatch.setattr(ai.provider, "MAX_REQUEST_BYTES", 10)
    with pytest.raises(AnalysisError, match="96,000"):
        ai.prepare_request(cv, job, comparison, "explicit-test-model")


@pytest.mark.parametrize("model", [None, "", "http://other-host", "model\nINJECT"])
def test_model_required_and_validated(source, model):
    with pytest.raises(AnalysisError, match="--model"):
        ai.prepare_request(*source, model)


@pytest.mark.parametrize("key", ["unsafe key", "key\x00PRIVATE", "key\nPRIVATE", "kéyPRIVATE"])
def test_bad_api_key_never_reaches_headers(source, monkeypatch, key):
    monkeypatch.setenv("OPENAI_API_KEY", key.replace("\x00", "\x01"))
    with pytest.raises(AnalysisError) as caught:
        ai.request_matching(*source, "explicit-test-model", input_rate="1", output_rate="1", consent=True,
                            connection_factory=lambda *a, **k: pytest.fail("Invalid key"))
    assert "PRIVATE" not in str(caught.value)
