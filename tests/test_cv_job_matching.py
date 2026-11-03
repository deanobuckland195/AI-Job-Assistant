import json
import os
from unittest.mock import Mock, patch

import pytest
from openai import APIConnectionError

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")

from ai_engine import analyse_cv_job_match
from skill_matching import calculate_cv_match_score


def _response(payload):
    response = Mock()
    response.output_text = json.dumps(payload)
    return response


def test_cv_job_match_preserves_evidence_states_and_deduplicates_suggestions():
    payload = {
        "requirements": [
            {
                "requirement": "Python",
                "category": "skill",
                "importance": "required",
                "status": "matched",
                "evidence": "Built Python automation scripts.",
                "explanation": "The CV explicitly describes Python work."
            },
            {
                "requirement": "AWS",
                "category": "skill",
                "importance": "required",
                "status": "gap",
                "evidence": "The CV says the candidate has no AWS experience.",
                "explanation": "The CV indicates this required skill is not held."
            },
            {
                "requirement": "Degree in computer science",
                "category": "qualification",
                "importance": "preferred",
                "status": "not_mentioned",
                "evidence": "",
                "explanation": "The CV does not mention a degree."
            }
        ],
        "suggestions": [
            "Add measurable outcomes to the Python project bullet.",
            "Add measurable outcomes to the Python project bullet."
        ]
    }

    with patch("ai_engine.client.responses.create", return_value=_response(payload)) as create:
        result = analyse_cv_job_match("Python CV text", "Python and AWS job description")

    assert [item["status"] for item in result["requirements"]] == [
        "matched", "gap", "not_mentioned"
    ]
    assert result["suggestions"] == ["Add measurable outcomes to the Python project bullet."]
    assert create.call_count == 1


@pytest.mark.parametrize(
    ("matched", "total", "expected"),
    [(4, 8, 50), (0, 8, 0), (8, 8, 100)],
)
def test_cv_match_score_uses_all_requirements_in_coverage(matched, total, expected):
    requirements = [
        {"requirement": f"Skill {index}", "status": "matched" if index < matched else "not_mentioned", "importance": "required"}
        for index in range(total)
    ]

    assert calculate_cv_match_score(requirements) == pytest.approx(expected)


def test_cv_match_score_is_unavailable_for_empty_requirements():
    assert calculate_cv_match_score([]) is None


def test_cv_match_score_does_not_double_count_duplicate_requirements():
    requirements = [
        {"requirement": "Python", "status": "matched", "importance": "required"},
        {"requirement": " python ", "status": "not_mentioned", "importance": "required"},
        {"requirement": "SQL", "status": "not_mentioned", "importance": "required"},
    ]

    assert calculate_cv_match_score(requirements) == pytest.approx(50)


def test_cv_job_match_rejects_invalid_response():
    with patch(
        "ai_engine.client.responses.create",
        return_value=_response({"requirements": "invalid", "suggestions": []})
    ):
        with pytest.raises(ValueError):
            analyse_cv_job_match("CV text", "Job text")


def test_cv_job_match_propagates_connection_error():
    with patch("ai_engine.client.responses.create") as create:
        create.side_effect = APIConnectionError(request=None)
        with pytest.raises(APIConnectionError):
            analyse_cv_job_match("CV text", "Job text")
