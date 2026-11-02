import streamlit as st
import json
from ai_engine import (
    analyse_cv_job_match,
    analyse_job_requirements,
    generate_learning_plan,
    extract_cv_skills,
)
from openai import APIConnectionError, AuthenticationError, APIError
from skill_matching import (
    calculate_cv_match_score,
    calculate_weighted_match,
    normalise_skill,
    normalise_skills,
)
from cv_reader import read_cv
from cv_matching import cached_match_is_current, cv_fingerprint, matching_inputs, valid_cv_text
from jobs_api import search_jobs, filter_senior_jobs, filter_by_salary, filter_by_work_type, filter_by_experience
from requests.exceptions import RequestException
from job_comparison import find_best_job
from sample_jobs import SAMPLE_JOBS


def _job_company(job):
    return job.get("company", {}).get("display_name", "Unknown")


def _job_location(job):
    return job.get("location", {}).get("display_name", "Unknown")


def _job_key(job):
    """Return a stable key even when an Adzuna result has no id."""
    job_id = job.get("id")
    if job_id is not None:
        return str(job_id)

    return "|".join(
        (
            str(job.get("title", "")),
            _job_company(job),
            _job_location(job),
            str(job.get("redirect_url", "")),
        )
    )


def _salary_text(job):
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min is not None and salary_max is not None:
        if salary_min == salary_max:
            return f"£{salary_min:,.0f}"
        return f"£{salary_min:,.0f} - £{salary_max:,.0f}"
    if salary_min is not None:
        return f"From £{salary_min:,.0f}"
    if salary_max is not None:
        return f"Up to £{salary_max:,.0f}"
    return "Not advertised"


def _normalise_skills(skills):
    return normalise_skills(skills)


for key, default in {
    "cv_skills": [],
    "searched_jobs": [],
    "comparison_results": [],
    "comparison_inputs": None,
    "learning_plans": {},
    "cv_job_match": None,
    "cv_text": "",
    "cv_fingerprint": None,
    "cv_skills_fingerprint": None,
    "cv_job_match_inputs": None,
}.items():
    st.session_state.setdefault(key, default)

st.title("AI Job Assistant V3")
st.write("Welcome to your AI-powered career assistant!")

st.subheader("Upload Your CV")
uploaded_cv = st.file_uploader(
    "Choose your CV (PDF only)",
    type=["pdf"]
)

if uploaded_cv is not None:
    st.success("CV uploaded successfully!")
    try:
        cv_text = read_cv(uploaded_cv)
        uploaded_fingerprint = cv_fingerprint(uploaded_cv)
        if uploaded_fingerprint != st.session_state.get("cv_fingerprint"):
            st.session_state["cv_fingerprint"] = uploaded_fingerprint
            st.session_state["cv_text"] = cv_text
            st.session_state["cv_skills"] = []
            st.session_state["cv_skills_fingerprint"] = None
            st.session_state["cv_job_match"] = None
            st.session_state["cv_job_match_inputs"] = None
        st.write("CV text extracted successfully!")
    except ValueError as error:
        st.error(str(error))
        st.stop()
    if (
        cv_text.strip()
        and st.session_state.get("cv_skills_fingerprint") != uploaded_fingerprint
    ):
        try:
            with st.spinner("AI is reading your CV..."):
                cv_skills = extract_cv_skills(cv_text)
                st.session_state["cv_skills"] = cv_skills
                st.session_state["cv_skills_fingerprint"] = uploaded_fingerprint

        except APIConnectionError:
            st.error("Unable to connect to OpenAI. Please check your connection.")

        except AuthenticationError:
            st.error("OpenAI authentication failed. Please check your API key.")

        except APIError:
            st.error("OpenAI could not process the CV. Please try again later.")

        except (ValueError, AttributeError):
            st.error("Unable to extract CV skills. Please try again.")

        else:
            st.success("CV skills extracted automatically!")
            st.write("Skills found in your CV:", cv_skills)
else:
    st.session_state["cv_text"] = ""
    st.session_state["cv_fingerprint"] = None
    st.session_state["cv_skills"] = []
    st.session_state["cv_skills_fingerprint"] = None
    st.session_state["cv_job_match"] = None
    st.session_state["cv_job_match_inputs"] = None

cv_text = st.session_state.get("cv_text", "")

user_skills = st.text_input(
    "Enter your technical skills (separated by commas):"
)

if user_skills.strip():
    current_skills = _normalise_skills(user_skills.split(","))
else:
    current_skills = _normalise_skills(st.session_state["cv_skills"])

if current_skills:
    st.write("Your skills:", current_skills)

demo_mode = st.checkbox(
    "Demo Mode — Use sample jobs for testing",
    value=False
)

st.subheader("Search UK Tech Jobs")
job_category = st.selectbox(
    "Choose a technology career:",
    [
        "Software Developer",
        "AI Engineer",
        "Machine Learning Engineer",
        "Data Analyst",
        "Cyber Security",
        "Cloud Engineer",
        "IT Support",
        "Software Tester",
        "Software Apprentice",
        "Other"
    ]
)

if job_category == "Other":
    job_keywords = st.text_input("Enter your own tech job:")
else:
    job_keywords = job_category

job_location = st.text_input("Where would you like to work?")

minimum_salary = st.number_input(
    "Minimum annual salary (£)",
    min_value=0,
    value=0,
    step=1000
)

maximum_salary = st.number_input(
    "Maximum annual salary (£)",
    min_value=0,
    value=0,
    step=1000
)

work_type = st.selectbox(
    "Preferred working arrangement:",
    ["Any", "Remote", "Hybrid", "On-site"]
)

experience_level = st.selectbox(
    "Preferred experience level:",
    ["Any", "Junior", "Graduate", "Apprenticeship"]
)

if st.button("Search Jobs"):
    if not job_keywords.strip() or not job_location.strip():
        st.warning("Please enter both job keywords and a location.")
    elif maximum_salary > 0 and minimum_salary > maximum_salary:
        st.warning("Maximum salary must be greater than or equal to minimum salary.")
    else:
        st.write("Searching for UK tech jobs...")
        try:
            jobs = search_jobs(job_keywords, job_location)

        except RequestException:
            st.error("Unable to retrieve jobs. Please check your connection.")

        except ValueError:
            st.error("Job search is unavailable. Please check your Adzuna API settings.")

        else:
            jobs = filter_senior_jobs(jobs)

            if minimum_salary > 0 or maximum_salary > 0:
                jobs = filter_by_salary(
                    jobs,
                    minimum_salary,
                    maximum_salary
                )

            jobs = filter_by_work_type(jobs, work_type)
            jobs = filter_by_experience(jobs, experience_level)

            st.session_state["searched_jobs"] = jobs
            st.write(f"Found {len(jobs)} jobs.")

            if not jobs:
                st.info("No suitable entry-level jobs found. Try different keywords or another location.")


selected_job_description = ""
selected_job = None


if demo_mode or st.session_state["searched_jobs"]:
    saved_jobs = SAMPLE_JOBS if demo_mode else st.session_state["searched_jobs"]
    st.subheader("Your Saved Job Search Results")

    for job in saved_jobs:
        st.write(job.get("title", "Unknown job"))

        st.write("Company:", _job_company(job))

        st.write("Location:", _job_location(job))

        st.write("Salary:", _salary_text(job))

        st.write("Apply here:", job.get("redirect_url", "No link available"))

        st.divider()

    st.subheader("Compare Jobs")

    selected_comparison_jobs = st.multiselect(
        "Select jobs to compare:",
        saved_jobs,
        format_func=lambda job: (
            f"{job.get('title', 'Unknown job')} - "
            f"{_job_company(job)} - "
            f"£{job.get('salary_min', 0):,.0f}"
        ),
        max_selections=3
    )

    if selected_comparison_jobs:
        st.session_state["comparison_jobs"] = selected_comparison_jobs
        st.success(f"{len(selected_comparison_jobs)} job(s) selected for comparison!")

        comparison_data = []

        for job in selected_comparison_jobs:
            comparison_data.append({
                "Job Title": job.get("title", "Unknown job"),
                "Company": _job_company(job),
                "Location": _job_location(job),
                "Salary": _salary_text(job)
            })

        st.subheader("Job Comparison Results")
        st.dataframe(comparison_data, hide_index=True, width="stretch")

        if st.button("Analyse Selected Jobs", disabled=not selected_comparison_jobs):
            st.session_state["comparison_results"] = []

            st.session_state["comparison_inputs"] = (
                tuple(sorted(_normalise_skills(current_skills))),
                demo_mode,
                tuple(sorted(_job_key(job) for job in selected_comparison_jobs))
            )

            if not current_skills:
                st.warning("Please enter your skills or extract skills from your CV first.")
                st.stop()

            st.write("Skills being used for comparison:", current_skills)

            for job in selected_comparison_jobs:
                job_description = job.get("description", "")
                st.write("Checking job description for:", job.get("title", "Unknown job"))
                st.write("Description length:", len(job_description))

                if len(job_description) == 500:
                    st.info(
                        "This job description may be shortened by Adzuna. "
                        "The AI match score will only reflect the available information."
                    )

                with st.expander("View job description"):
                    st.write(job_description)

                if not job_description.strip():
                    st.warning(
                        f"No description available for {job.get('title', 'Unknown job')}."
                    )
                    continue

                try:
                    with st.spinner(
                        f"Analysing {job.get('title', 'Unknown job')}..."
                    ):
                        requirements = analyse_job_requirements(job_description)

                        essential_skills = {
                            normalise_skill(skill)
                            for skill in requirements["essential_skills"]
                        }

                        desirable_skills = {
                            normalise_skill(skill)
                            for skill in requirements["desirable_skills"]
                        }

                        detected_skills = sorted(essential_skills | desirable_skills)

                except (APIConnectionError, AuthenticationError, APIError, json.JSONDecodeError, ValueError):
                    st.error(
                        f"Unable to analyse {job.get('title', 'Unknown job')}."
                    )
                    continue

                required_skills = {
                    normalise_skill(skill)
                    for skill in detected_skills
                }

                user_skill_set = {
                    normalise_skill(skill)
                    for skill in current_skills
                }

                matching_skills = sorted(required_skills & user_skill_set)

                missing_skills = sorted(required_skills - user_skill_set)

                if required_skills:
                    skill_weights = {
                        skill: 3 if skill in essential_skills else 1
                        for skill in required_skills
                    }

                    match_score = calculate_weighted_match(
                        required_skills,
                        matching_skills,
                        skill_weights
                    )
                else:
                    match_score = None

                st.session_state["comparison_results"].append({
                    "job": job,
                    "detected_skills": detected_skills,
                    "matching_skills": matching_skills,
                    "missing_skills": missing_skills,
                    "score": match_score
                })

            st.success("Job comparison analysis finished!")

    comparison_inputs = (
        tuple(sorted(_normalise_skills(current_skills))),
        demo_mode,
        tuple(sorted(_job_key(job) for job in selected_comparison_jobs))
    )

    if st.session_state.get("comparison_inputs") != comparison_inputs:
        st.session_state["comparison_results"] = []

    st.subheader("Skills Comparison Summary")

    summary_data = []

    for result in st.session_state["comparison_results"]:
        job = result["job"]
        summary_data.append({

            "Job Title": job.get("title", "Unknown job"),

            "Salary Range": _salary_text(job),

            "Match Score": (
                f"{result['score']:.0f}%"
                if result["score"] is not None
                else "N/A"
            ),
            "Missing Skills": ", ".join(result["missing_skills"]) or "None"
        })

    st.dataframe(summary_data, hide_index=True, width="stretch")

    if st.session_state.get("comparison_results"):
        st.subheader("AI Skills Detected for Each Job")

        for result in st.session_state["comparison_results"]:
            job = result["job"]
            detected_skills = result["detected_skills"]
            matching_skills = result["matching_skills"]
            missing_skills = result["missing_skills"]
            match_score = result["score"]

            st.write(
                f"**{job.get('title', 'Unknown job')} - "
                f"{_job_company(job)}**"
            )

            if match_score is not None:
                st.write(f"Job Match Score: {match_score:.0f}%")
                st.write("Matching skills:", matching_skills)
                st.write("Missing skills:", missing_skills)


            if detected_skills:
                st.write("Required technical skills:", detected_skills)
            else:
                st.warning(
                    "No explicit technical skills detected. "
                    "A reliable job match score cannot be calculated."
                )

            st.divider()

        valid_results = [
            result
            for result in st.session_state["comparison_results"]
            if result["score"] is not None
        ]

        if valid_results:
            best_job = find_best_job(valid_results)

            st.subheader("Best Matching Job")

            st.success(
                f"{best_job['job'].get('title', 'Unknown job')} - "
                f"{best_job['job'].get('company', {}).get('display_name', 'Unknown')} "
                f"({best_job['score']:.0f}% match)"
            )
        else:
            st.info("No reliable job match scores are available.")

    selected_job = st.selectbox(
        "Choose a job to analyse:",
        saved_jobs,
        format_func=lambda job: job.get("title", "Unknown job"),
        index=None,
        placeholder="Select a job"
    )

    if selected_job is not None:
        selected_job_description = selected_job.get("description", "")

        if not selected_job_description:
            st.warning("This job has no description available to analyse.")

st.subheader("Job Description Analyser")

job_description = st.text_area(
    "Paste a job description here:",
    value=selected_job_description,
    key=f"job_description_{_job_key(selected_job) if selected_job is not None else 'manual'}"
)

if st.button("Analyse CV against this job"):
    if not valid_cv_text(cv_text):
        st.warning("Upload a readable CV first. The detailed analysis uses CV text, not only a skill list.")
    elif not job_description.strip():
        st.warning("Please paste or select a job description first.")
    else:
        try:
            with st.spinner("AI is comparing your CV with this job..."):
                cv_job_match = analyse_cv_job_match(cv_text, job_description)
                cv_job_match["score"] = calculate_cv_match_score(
                    cv_job_match["requirements"]
                )
                cv_job_match["inputs"] = matching_inputs(cv_text, job_description)
                st.session_state["cv_job_match"] = cv_job_match
                st.session_state["cv_job_match_inputs"] = cv_job_match["inputs"]
                st.session_state["missing_skills"] = [
                    item["requirement"]
                    for item in cv_job_match["requirements"]
                    if item["status"] == "gap"
                ]
        except AuthenticationError:
            st.error("OpenAI authentication failed. Please check your API key.")
        except (APIConnectionError, APIError):
            st.error("Unable to connect to OpenAI. Please try again later.")
        except (json.JSONDecodeError, ValueError, AttributeError):
            st.error("The AI returned an invalid CV match response. Please try again.")
        else:
            st.success("CV-to-job analysis complete.")

cv_job_match = st.session_state.get("cv_job_match")
if cv_job_match and cached_match_is_current(
    st.session_state.get("cv_job_match_inputs"), cv_text, job_description
):
    st.subheader("CV-to-Job Match")
    st.caption(
        "This is an AI-assisted heuristic based only on the job details and CV text provided. "
        "It is not a scientifically calibrated probability of getting hired. "
        "Requirements not mentioned in the CV are not counted as gaps."
    )

    score = cv_job_match.get("score")
    if score is None:
        st.info("There is not enough explicit CV evidence to calculate a reliable heuristic score.")
    else:
        st.metric("Heuristic CV match", f"{score:.0f}%")

    requirements = cv_job_match.get("requirements", [])
    status_groups = (
        ("matched", "Supported by your CV", "success"),
        ("gap", "Potential gaps", "warning"),
        ("not_mentioned", "Not mentioned in your CV", "info"),
    )
    for status, heading, message_type in status_groups:
        items = [item for item in requirements if item["status"] == status]
        if not items:
            continue
        getattr(st, message_type)(f"{heading}: {len(items)}")
        for item in items:
            importance = "Required" if item["importance"] == "required" else "Preferred"
            with st.expander(f"{item['requirement']} · {importance}"):
                st.write(item["explanation"])
                if item["evidence"]:
                    st.caption(f"CV evidence: {item['evidence']}")

    suggestions = cv_job_match.get("suggestions", [])
    if suggestions:
        st.markdown("**Personalised CV improvements**")
        for suggestion in suggestions:
            st.write(f"- {suggestion}")

if st.session_state.get("missing_skills"):
    generate_plans = st.checkbox("Generate learning plans for missing skills")

    if generate_plans:
        if st.button("Create Learning Plans"):
            for skill in st.session_state["missing_skills"]:
                try:
                    with st.spinner(f"Creating a learning plan for {skill}..."):
                        plan = generate_learning_plan(skill)
                        st.session_state.setdefault("learning_plans", {})[skill] = plan

                except (APIConnectionError, AuthenticationError, APIError):
                    st.error(f"Unable to generate a learning plan for {skill}.")

    for skill, plan in st.session_state.get("learning_plans", {}).items():
        st.subheader(f"{skill.title()} Learning Plan")
        st.write(plan)
