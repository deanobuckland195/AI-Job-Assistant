import io
import json
from unittest.mock import Mock, patch

from cv_matching import cached_match_is_current, cv_fingerprint, matching_inputs, valid_cv_text
from skill_matching import normalise_skills
from ai_engine import extract_cv_skills


class UploadedFile:
    def __init__(self, content):
        self.content = content

    def getvalue(self):
        return self.content


def test_cv_upload_fingerprint_and_valid_text():
    first = UploadedFile(b"sample cv")
    same = UploadedFile(b"sample cv")
    changed = UploadedFile(b"new cv")

    assert cv_fingerprint(first) == cv_fingerprint(same)
    assert cv_fingerprint(first) != cv_fingerprint(changed)
    assert valid_cv_text("Python CV")
    assert not valid_cv_text("  ")


def test_matching_uses_current_cv_and_job_not_cached_inputs():
    cached = matching_inputs("old CV", "old job")
    assert cached_match_is_current(cached, "old CV", "old job")
    assert not cached_match_is_current(cached, "new CV", "old job")
    assert not cached_match_is_current(cached, "old CV", "new job")
    assert matching_inputs("", "job") is None


def test_equivalent_skill_phrase_exposes_python_git_and_openai_api():
    skills = normalise_skills([
        "built a Python application using the OpenAI API",
        "Git version control",
    ])
    assert {"python", "git", "openai api"}.issubset(skills)
    assert "streamlit" not in skills
    assert "prompt engineering" not in skills


def test_cv_skill_extraction_is_automatic_contract_and_mocked():
    response = Mock()
    response.output_text = "Python, Git, SQL, Machine Learning, OpenAI API"
    with patch("ai_engine.client.responses.create", return_value=response) as create:
        skills = extract_cv_skills("Built a Python application using the OpenAI API.")

    assert {"python", "git", "sql", "machine learning", "openai api"} == set(skills)
    create.assert_called_once()
