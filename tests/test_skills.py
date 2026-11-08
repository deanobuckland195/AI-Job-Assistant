import pytest

from job_assistant.skills import (
    analyse_job, calculate_match, check_skills, detect_job_skills,
    match_job_skills, normalise_skills,
)


@pytest.mark.parametrize("text, expected", [
    (" PYTHON, ml, ML, API, rest api, , python ", ["python", "machine learning", "apis"]),
    (" , , ", []),
    ("Machine-learning, Customer   Support, JS", ["machine learning", "customer service", "javascript"]),
    ("Docker, Rust", ["docker", "rust"]),
])
def test_normalisation(text, expected):
    assert normalise_skills(text) == expected


def test_comparison_preserves_required_order():
    expected = (["python", "sql"], ["git"])
    assert check_skills(["sql", "python"], ["python", "git", "sql"]) == expected
    assert match_job_skills(["sql", "python"], ["python", "git", "sql"]) == expected


@pytest.mark.parametrize("matching, required, expected", [
    ([], [], 0), ([], ["python"], 0),
    (["python"], ["python", "sql"], 50),
    (["python", "python", "unknown"], ["python"], 100),
])
def test_scoring(matching, required, expected):
    assert calculate_match(matching, required) == expected


@pytest.mark.parametrize("text, expected", [
    ("PYTHON, SQL and REST API required", ["python", "sql", "apis"]),
    ("python python APIs API REST API", ["python", "apis"]),
    ("Machine-learning and data   analysis", ["machine learning", "data analysis"]),
    ("legitimate excellent htmlish", []),
    ("Communication and customer care", ["communication", "customer service"]),
    ("Kubernetes and Docker", []),
    ("", []),
])
def test_detection(text, expected):
    assert detect_job_skills(text) == expected


def test_detection_respects_custom_catalogue():
    assert detect_job_skills("ML Python", ["python"], {"ml": "machine learning"}) == ["python"]


def test_job_analysis():
    analysis = analyse_job(["python"], "Python and SQL")
    assert analysis.matching == ["python"]
    assert analysis.missing == ["sql"]
    assert analysis.score == 50


def test_unknown_job_is_unscored():
    analysis = analyse_job(["python"], "Kubernetes required")
    assert analysis.score is None
    assert analysis.detected == []


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_empty_job_rejected(text):
    with pytest.raises(ValueError, match="job description"):
        analyse_job([], text)
