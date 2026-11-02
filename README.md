# AI Job Assistant V3

An AI-powered Python application that helps users explore UK technology jobs, analyse job descriptions, and identify skills they need to develop.

## Features

- Search UK technology jobs using the Adzuna API
- Explore software engineering, AI, cybersecurity, data, cloud and IT careers
- Upload a PDF CV and extract technical skills using OpenAI
- Analyse job descriptions using AI
- Calculate weighted job-match scores
- Identify missing technical skills
- Generate personalised learning plans
- Select a job directly from search results for analysis
- Filter out senior-level vacancies
- Interactive Streamlit web interface
- Automated tests using pytest
- Skill alias normalisation (e.g. JS and JavaScript)
- Job-specific weighted matching using essential and desirable skills
- Salary range, remote/hybrid/on-site and experience-level filtering
- Compare up to three jobs by salary, match score and missing skills
- Demo Mode for comparing sample jobs without an Adzuna search
- Structured AI responses with validation and error handling
- Detailed CV-to-job analysis covering explicit skills, experience and qualifications
- Clear distinction between supported evidence, evidenced gaps and requirements not mentioned in the CV
- Personalised, evidence-safe CV improvement suggestions for a selected job
- Transparent heuristic scoring; not a scientifically calibrated hiring probability
- Automatic CV skill extraction immediately after a readable upload; no separate extraction click is required
- Current-input protection: matching is only shown for the active uploaded CV and current job description
- Equivalent explicit skill wording is normalised (for example, a Python application using the OpenAI API supports Python and OpenAI API)

## Technologies

Python, Streamlit, OpenAI API, Adzuna API, pytest and Git.

## Installation

Clone the repository and open the project folder:

```bash
git clone https://github.com/deanobuckland195/AIJobAssistantV3.git
cd AIJobAssistantV3
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

## API Configuration

This application uses the OpenAI API and Adzuna API.

Set these environment variables before starting the application:

- `OPENAI_API_KEY`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

Never commit API keys to GitHub.

## Running the Application

Start the Streamlit interface:

```bash
python -m streamlit run app.py
```

Open http://localhost:8501 in your browser.

## Running Tests

Run the automated tests:

```bash
python3 -m pytest tests -q
```

The CV-to-job matching tests mock OpenAI responses and never make live API calls. Invalid AI payloads, API connection failures, automatic extraction, upload identity, equivalent skill wording, evidence states and stale session inputs are covered. The repository test configuration excludes `ai_test.py`, an interactive/manual script, from automated discovery so it cannot make a live API call during testing.

## CV-to-job matching

After uploading a readable PDF CV and selecting or pasting a job description, CV skills are extracted automatically. Use **Analyse CV against this job** for one structured OpenAI request. The response is validated before display and reports:

- requirements supported by explicit CV evidence;
- potential gaps only where the CV provides evidence of a lack of the requirement; and
- requirements not mentioned in the CV, which are not treated as gaps.

The app does not log CV text or API keys. Suggestions are framed as ways to clarify or strengthen evidence already present in the CV and must not invent achievements or qualifications.

The score is a transparent estimate based on explicit evidence in the supplied CV and job description. It is not a hiring probability. A requirement that is not mentioned in the CV is shown separately from a potential gap and is not silently counted as a failure. Matching is unavailable until a readable CV has been uploaded.

## Existing matching features

- Fixed repeated AI calls during job comparison.
- Applied consistent skill normalisation to single-job analysis.
- Added essential and desirable skill weighting (3:1).
- Improved error handling for damaged or unreadable PDFs.
- Added error handling for AI-powered CV skill extraction.
- Tested realistic job matching scenarios (86% and 14%).
- Existing skill-only job comparison and learning-plan functionality remains available.
