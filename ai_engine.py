import json

from openai import OpenAI, APIConnectionError

client = OpenAI()


def analyse_job(job_description):
    if not job_description.strip():
        return []

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract only technical skills explicitly required "
                        "in the supplied job description. "
                        "Do not invent skills or provide explanations. "
                        "If no technical skills are explicitly stated, "
                        "return an empty skills list."
                    )
                },
                {
                    "role": "user",
                    "content": job_description
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "job_skills",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "skills": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["skills"],
                        "additionalProperties": False
                    }
                }
            }
        )

    except APIConnectionError:
        print("Unable to connect to OpenAI.")
        raise

    data = json.loads(response.output_text)

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("skills"), list)
        or not all(isinstance(skill, str) for skill in data["skills"])
    ):
        raise ValueError("Invalid AI response: skills must be a list of strings.")

    skills = [
        skill.strip().lower()
        for skill in data["skills"]
        if skill.strip()
    ]

    return list(dict.fromkeys(skills))


def analyse_job_requirements(job_description):
    if not job_description.strip():
        return {
            "essential_skills": [],
            "desirable_skills": []
        }

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "Extract only technical skills explicitly mentioned "
                    "in the job description. "
                    "Put required or essential skills in essential_skills. "
                    "Put preferred, desirable or nice-to-have skills "
                    "in desirable_skills. "
                    "Do not invent skills. "
                    "Return empty lists when no skills qualify."
                )
            },
            {
                "role": "user",
                "content": job_description
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "job_requirements",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "essential_skills": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "desirable_skills": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": [
                        "essential_skills",
                        "desirable_skills"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    data = json.loads(response.output_text)

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("essential_skills"), list)
        or not isinstance(data.get("desirable_skills"), list)
        or not all(
            isinstance(skill, str)
            for category in ("essential_skills", "desirable_skills")
            for skill in data[category]
        )
    ):
        raise ValueError("Invalid AI response: expected two lists of skills.")

    essential = list(dict.fromkeys(
        skill.strip().lower()
        for skill in data["essential_skills"]
        if skill.strip()
    ))

    desirable = list(dict.fromkeys(
        skill.strip().lower()
        for skill in data["desirable_skills"]
        if skill.strip()
    ))

    desirable = [
        skill for skill in desirable
        if skill not in essential
    ]

    return {
        "essential_skills": essential,
        "desirable_skills": desirable
    }


def analyse_cv_job_match(cv_text, job_description):
    """Compare CV evidence with one job description in a single AI request.

    The model is instructed to quote or closely paraphrase only evidence in the
    CV.  The returned status deliberately separates a genuine gap from a
    requirement that the CV does not mention.
    """
    if not isinstance(cv_text, str) or not cv_text.strip():
        raise ValueError("CV text is required for a CV-to-job analysis.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Job description is required for a CV-to-job analysis.")

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": (
                    "Assess how the candidate CV matches the supplied job description. "
                    "Extract requirements only when explicitly stated in the job. "
                    "Use status matched only when the CV provides direct supporting evidence. "
                    "Recognise equivalent wording when the same explicit skill is evidenced, "
                    "for example 'built a Python application using the OpenAI API' supports "
                    "Python and OpenAI API experience. Treat 'Git' and 'Git version control' "
                    "as the same skill. Do not infer Streamlit, prompt engineering or any "
                    "other skill unless the CV explicitly supports it. "
                    "Use gap only when the CV provides evidence that the candidate lacks "
                    "the requirement. Use not_mentioned when the CV does not establish either "
                    "case; do not treat silence as a gap. Never invent qualifications, skills, "
                    "experience, achievements, employers, dates or levels. Keep evidence and "
                    "explanations concise. Suggestions must be practical CV improvements and "
                    "must never ask the candidate to claim something unsupported. Return an "
                    "empty requirements list if the job contains no assessable requirements."
                )
            },
            {
                "role": "user",
                "content": (
                    "CANDIDATE CV:\n"
                    f"{cv_text}\n\n"
                    "JOB DESCRIPTION:\n"
                    f"{job_description}"
                )
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "cv_job_match",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "requirement": {"type": "string"},
                                    "category": {
                                        "type": "string",
                                        "enum": ["skill", "experience", "qualification", "other"]
                                    },
                                    "importance": {
                                        "type": "string",
                                        "enum": ["required", "preferred"]
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": ["matched", "gap", "not_mentioned"]
                                    },
                                    "evidence": {"type": "string"},
                                    "explanation": {"type": "string"}
                                },
                                "required": [
                                    "requirement", "category", "importance", "status",
                                    "evidence", "explanation"
                                ],
                                "additionalProperties": False
                            }
                        },
                        "suggestions": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["requirements", "suggestions"],
                    "additionalProperties": False
                }
            }
        }
    )

    data = json.loads(response.output_text)
    if not isinstance(data, dict):
        raise ValueError("Invalid AI response: expected an object.")

    requirements = data.get("requirements")
    suggestions = data.get("suggestions")
    if not isinstance(requirements, list) or not isinstance(suggestions, list):
        raise ValueError("Invalid AI response: requirements and suggestions must be lists.")

    allowed_categories = {"skill", "experience", "qualification", "other"}
    allowed_importance = {"required", "preferred"}
    allowed_statuses = {"matched", "gap", "not_mentioned"}
    cleaned_requirements = []
    for item in requirements:
        if not isinstance(item, dict):
            raise ValueError("Invalid AI response: each requirement must be an object.")
        if not all(isinstance(item.get(key), str) for key in (
            "requirement", "category", "importance", "status", "evidence", "explanation"
        )):
            raise ValueError("Invalid AI response: requirement fields must be strings.")
        if (
            not item["requirement"].strip()
            or item["category"] not in allowed_categories
            or item["importance"] not in allowed_importance
            or item["status"] not in allowed_statuses
        ):
            raise ValueError("Invalid AI response: unsupported requirement value.")
        cleaned_requirements.append({
            key: item[key].strip()
            for key in ("requirement", "category", "importance", "status", "evidence", "explanation")
        })

    if not all(isinstance(suggestion, str) and suggestion.strip() for suggestion in suggestions):
        raise ValueError("Invalid AI response: suggestions must be non-empty strings.")

    return {
        "requirements": cleaned_requirements,
        "suggestions": list(dict.fromkeys(suggestion.strip() for suggestion in suggestions))
    }


def generate_learning_plan(skill):
    try:
        response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"Create a beginner-friendly, 5-step learning plan for {skill}. Keep each step short and practical."
    )
    except APIConnectionError:
        print("Unable to connect to OpenAI while generating the learning plan.")
        raise
    learning_plan = response.output_text.replace("**", "")
    return learning_plan

def extract_cv_skills(cv_text):
    try:
        response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"List only the technical skills found in this CV, separated by commas. Do not add explanations or numbering:\n\n{cv_text}"
        )
    except APIConnectionError:
        print("Unable to connect to OpenAI while generating the cv skills.")
        raise

    skills = [
        skill.strip().lower()
        for skill in response.output_text.split(",")
        if skill.strip().lower() not in ("", "none", "n/a", "no skills")
    ]

    return list(dict.fromkeys(skills))
