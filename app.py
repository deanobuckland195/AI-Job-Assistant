import streamlit as st
import json
from html import escape
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
    deduplicate_requirements,
    normalise_skill,
    normalise_skills,
)
from cv_reader import read_cv
from cv_matching import cached_match_is_current, cv_fingerprint, matching_inputs, valid_cv_text
from jobs_api import search_jobs, filter_senior_jobs, filter_by_salary, filter_by_work_type, filter_by_experience
from requests.exceptions import RequestException
from job_comparison import find_best_job
from sample_jobs import SAMPLE_JOBS

st.set_page_config(
    page_title="AI Job Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

THEMES = {
    "Professional Light": {
        "page": "#f8fbff",
        "surface": "#ffffff",
        "soft": "#eff6ff",
        "text": "#172033",
        "muted": "#475569",
        "line": "#cbd5e1",
        "input": "#ffffff",
        "input_text": "#172033",
        "brand": "#1d4ed8",
        "brand_soft": "#dbeafe",
        "button_text": "#ffffff",
        "hero": "linear-gradient(135deg, #172554 0%, #1d4ed8 58%, #0284c7 140%)",
        "badge": "#e8f0ff",
        "badge_text": "#1e40af",
    },
    "Professional Dark": {
        "page": "#0f172a",
        "surface": "#1e293b",
        "soft": "#172554",
        "text": "#f8fafc",
        "muted": "#cbd5e1",
        "line": "#475569",
        "input": "#111827",
        "input_text": "#f8fafc",
        "brand": "#93c5fd",
        "brand_soft": "#1e3a8a",
        "button_text": "#0f172a",
        "hero": "linear-gradient(135deg, #172554 0%, #1d4ed8 58%, #0369a1 140%)",
        "badge": "#1e3a8a",
        "badge_text": "#dbeafe",
    },
    "Navy Blue": {
        "page": "#081a2f",
        "surface": "#102a4c",
        "soft": "#12345d",
        "text": "#f1f5f9",
        "muted": "#d1d5db",
        "line": "#416486",
        "input": "#0b203b",
        "input_text": "#f8fafc",
        "brand": "#93c5fd",
        "brand_soft": "#1e416b",
        "button_text": "#071426",
        "hero": "linear-gradient(135deg, #071426 0%, #123b6b 58%, #075985 140%)",
        "badge": "#16416b",
        "badge_text": "#dbeafe",
    },
}

st.session_state.setdefault("theme_name", "Professional Light")
selected_theme = st.sidebar.selectbox(
    "Colour theme",
    list(THEMES),
    index=list(THEMES).index(st.session_state["theme_name"]),
    key="theme_selector",
    help="Choose a high-contrast colour palette for this session.",
)
st.session_state["theme_name"] = selected_theme
theme = THEMES[selected_theme]


st.markdown(
    f"""
    <style>
    :root {{
        --ink: {theme['text']};
        --muted: {theme['muted']};
        --brand: {theme['brand']};
        --brand-dark: {theme['brand']};
        --surface: {theme['surface']};
        --soft: {theme['soft']};
        --line: {theme['line']};
        --input: {theme['input']};
        --input-text: {theme['input_text']};
    }}
    .stApp {{ background: linear-gradient(180deg, {theme['page']} 0%, {theme['surface']} 46%); color: var(--ink); }}
    [data-testid="stHeader"] {{ background: {theme['page']}ee; }}
    [data-testid="stSidebar"] {{ background: {theme['surface']}; border-right: 1px solid var(--line); }}
    .stApp p, .stApp li, .stApp label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] {{ color: var(--ink); }}
    .stApp small, .stCaption, [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; }}
    input, textarea, [data-baseweb="select"] > div, [data-testid="stNumberInput"] input {{
        background-color: var(--input) !important; color: var(--input-text) !important;
        border-color: var(--line) !important;
    }}
    input::placeholder, textarea::placeholder {{ color: var(--muted) !important; opacity: 1 !important; }}
    [data-baseweb="select"] span, [data-baseweb="select"] input {{ color: var(--input-text) !important; }}
    [data-baseweb="popover"] {{ background: var(--surface); }}
    [data-baseweb="popover"] li {{ color: var(--ink) !important; }}
    .stButton > button, .stDownloadButton > button {{ background: var(--brand); color: {theme['button_text']} !important; border: 1px solid var(--brand); }}
    .stButton > button:hover, .stDownloadButton > button:hover {{ filter: brightness(1.08); }}
    [data-testid="stAlert"] {{ background: var(--surface); color: var(--ink); border: 1px solid var(--line); }}
    [data-testid="stExpander"] {{ background: var(--surface); border: 1px solid var(--line); }}
    [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {{ color: var(--ink) !important; }}
    .block-container {{ max-width: 1180px; padding-top: 2rem; padding-bottom: 4rem; }}
    h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.02em; }}
    h1 {{ font-size: clamp(2rem, 5vw, 3.25rem) !important; margin-bottom: 0.25rem; }}
    h2 {{ margin-top: 1.5rem; }}
    .hero {{ background: {theme['hero']}; border-radius: 1.25rem; padding: 2rem 2.25rem; color: white; box-shadow: 0 16px 40px rgba(30, 64, 175, 0.24); margin-bottom: 1.5rem; }}
    .hero h1 {{ color: white; margin: 0; }}
    .hero p {{ color: #e0f2fe; font-size: 1.05rem; margin: 0.45rem 0 0; }}
    .section-kicker {{ color: var(--brand-dark); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 1.6rem; }}
    .card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 0.9rem; padding: 1.1rem 1.25rem; box-shadow: 0 5px 18px rgba(15, 23, 42, 0.12); }}
    .muted {{ color: var(--muted) !important; }}
    .skill-badge {{ display: inline-block; background: {theme['badge']}; color: {theme['badge_text']}; border: 1px solid var(--line); border-radius: 999px; padding: 0.28rem 0.68rem; margin: 0.16rem 0.2rem 0.16rem 0; font-size: 0.84rem; font-weight: 600; }}
    .skill-badge.success {{ background: #14532d; color: #dcfce7; border-color: #4ade80; }}
    .skill-badge.warning {{ background: #78350f; color: #fef3c7; border-color: #fbbf24; }}
    .skill-badge.neutral {{ background: var(--soft); color: var(--ink); border-color: var(--line); }}
    .file-status {{ background: var(--soft); border-left: 4px solid var(--brand); border-radius: 0.5rem; padding: 0.75rem 1rem; }}
    @media (max-width: 640px) {{
        .block-container {{ padding: 1rem 0.8rem 3rem; }}
        .hero {{ padding: 1.4rem; border-radius: 0.9rem; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


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


def _skill_badges(skills, style=""):
    """Render a compact, readable skill list without exposing raw list syntax."""
    skills = [str(skill) for skill in skills if str(skill).strip()]
    if not skills:
        return '<span class="muted">None identified</span>'
    return "".join(
        f'<span class="skill-badge {style}">{escape(skill.title())}</span>'
        for skill in skills
    )


def _job_label(job):
    return f"{job.get('title', 'Unknown job')} · {_job_company(job)}"


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

st.markdown(
    '<div class="hero"><h1>AI Job Assistant</h1>'
    '<p>Turn your CV and the right opportunity into an evidence-led career plan.</p></div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-kicker">01 · Candidate profile</div>', unsafe_allow_html=True)
st.header("Upload your CV", anchor=False)
st.caption("Upload a readable PDF to automatically extract skills and unlock evidence-based matching.")
uploaded_cv = st.file_uploader(
    "Choose a CV (PDF only)",
    type=["pdf"],
    help="Your CV is used only for this session's matching workflow.",
)

if uploaded_cv is not None:
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
            st.session_state["missing_skills"] = []
            st.session_state["learning_plans"] = {}
        st.markdown(
            f'<div class="file-status"><strong>Analysing:</strong> {escape(uploaded_cv.name)}'
            '<br><span class="muted">Readable CV text extracted successfully.</span></div>',
            unsafe_allow_html=True,
        )
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
            st.markdown(
                f'<div class="card"><strong>Skills found in your CV</strong><br>{_skill_badges(cv_skills)}</div>',
                unsafe_allow_html=True,
            )
else:
    st.session_state["cv_text"] = ""
    st.session_state["cv_fingerprint"] = None
    st.session_state["cv_skills"] = []
    st.session_state["cv_skills_fingerprint"] = None
    st.session_state["cv_job_match"] = None
    st.session_state["cv_job_match_inputs"] = None
    st.session_state["missing_skills"] = []
    st.session_state["learning_plans"] = {}

cv_text = st.session_state.get("cv_text", "")

user_skills = st.text_input(
    "Enter your technical skills (separated by commas):"
)

if user_skills.strip():
    current_skills = _normalise_skills(user_skills.split(","))
else:
    current_skills = _normalise_skills(st.session_state["cv_skills"])

if current_skills:
    source_label = "Skills used for matching" if user_skills.strip() else "Skills used from your CV"
    st.markdown(
        f'<div class="card"><strong>{source_label}</strong><br>{_skill_badges(current_skills)}</div>',
        unsafe_allow_html=True,
    )

demo_mode = st.checkbox(
    "Demo Mode — Use sample jobs for testing",
    value=False
)

st.markdown('<div class="section-kicker">02 · Opportunity discovery</div>', unsafe_allow_html=True)
st.header("Search UK tech jobs", anchor=False)
st.caption("Filter for entry-level roles, then compare the opportunities that fit your goals.")
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
    st.markdown('<div class="section-kicker">03 · Shortlist</div>', unsafe_allow_html=True)
    st.header("Saved job results", anchor=False)
    st.caption(f"{len(saved_jobs)} opportunity(ies) ready for review and comparison.")

    for job in saved_jobs:
        with st.container(border=True):
            st.subheader(_job_label(job), anchor=False)
            job_meta = (
                f"**Location:** {_job_location(job)}  ·  **Salary:** {_salary_text(job)}"
            )
            st.markdown(job_meta)
            if job.get("redirect_url"):
                st.link_button("View application", job["redirect_url"])

    st.subheader("Compare shortlisted jobs", anchor=False)

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
        st.success(f"{len(selected_comparison_jobs)} job(s) selected for comparison.")

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

            st.markdown(
                f'<div class="card"><strong>Skills used for comparison</strong><br>{_skill_badges(current_skills, "success")}</div>',
                unsafe_allow_html=True,
            )

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

    st.subheader("Comparison summary", anchor=False)

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
        st.subheader("Comparison details", anchor=False)

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
                st.markdown(
                    f'<strong>Matching skills</strong><br>{_skill_badges(matching_skills, "success")}',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<strong>Missing skills</strong><br>{_skill_badges(missing_skills, "warning")}',
                    unsafe_allow_html=True,
                )


            if detected_skills:
                with st.expander("View detected requirements"):
                    st.markdown(_skill_badges(detected_skills), unsafe_allow_html=True)
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

st.markdown('<div class="section-kicker">04 · Evidence-led matching</div>', unsafe_allow_html=True)
st.header("CV-to-job matching", anchor=False)
st.caption("Paste a description or select a saved role. The analysis uses only the current CV and job text.")

job_description = st.text_area(
    "Paste a job description here:",
    value=selected_job_description,
    key=f"job_description_{_job_key(selected_job) if selected_job is not None else 'manual'}",
    height=220,
    placeholder="Example: Junior AI Engineer requiring Python, Git, OpenAI APIs and prompt engineering...",
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
                cv_job_match["requirements"] = deduplicate_requirements(
                    cv_job_match["requirements"]
                )
                cv_job_match["score"] = calculate_cv_match_score(cv_job_match["requirements"])
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
    st.markdown('<div class="section-kicker">05 · Saved analysis</div>', unsafe_allow_html=True)
    st.header("Your match report", anchor=False)
    st.caption(
        "This is an AI-assisted heuristic based only on the supplied CV and job description. "
        "It is an estimate of requirement alignment, not a probability of being hired. "
        "Requirements not evidenced in the CV are shown separately from potential gaps."
    )

    score = cv_job_match.get("score")
    if score is None:
        st.info("There is not enough explicit CV evidence to calculate a reliable heuristic score.")
    else:
        requirements = deduplicate_requirements(cv_job_match.get("requirements", []))
        matched_count = sum(item["status"] == "matched" for item in requirements)
        requirement_count = len(requirements)
        score_col, evidence_col, scope_col = st.columns(3)
        score_col.metric("CV requirement coverage", f"{score:.0f}%")
        evidence_col.metric("Supported requirements", f"{matched_count}/{requirement_count}")
        scope_col.metric("CV analysed", uploaded_cv.name if uploaded_cv is not None else "Current CV")

    requirements = deduplicate_requirements(cv_job_match.get("requirements", []))
    requirement_rows = [
        {
            "Requirement": item["requirement"],
            "Importance": item["importance"].title(),
            "Evidence status": {
                "matched": "Supported",
                "gap": "Potential gap",
                "not_mentioned": "Not evidenced",
            }[item["status"]],
        }
        for item in requirements
    ]
    if requirement_rows:
        st.dataframe(requirement_rows, hide_index=True, width="stretch")

    status_groups = (
        ("matched", "Supported by your CV", "success"),
        ("gap", "Potential gaps", "warning"),
        ("not_mentioned", "Not evidenced in your CV", "info"),
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
                elif status == "not_mentioned":
                    st.caption("No supporting statement was found in the uploaded CV.")

    suggestions = cv_job_match.get("suggestions", [])
    if suggestions:
        st.subheader("Personalised next steps", anchor=False)
        for suggestion in suggestions:
            st.info(suggestion)

if st.session_state.get("missing_skills"):
    st.subheader("Learning plans", anchor=False)
    st.caption("Optional plans for requirements explicitly identified as potential gaps.")
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
        with st.expander(f"{skill.title()} learning plan"):
            st.write(plan)
