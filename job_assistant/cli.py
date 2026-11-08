"""Interactive terminal workflow; all analysis can also run without the CLI."""

import argparse
from pathlib import Path

from .catalogue import REQUIRED_SKILLS
from .reports import DEFAULT_REPORT_PATH, format_analysis, save_analysis
from .skills import analyse_job, calculate_match, check_skills, normalise_skills


def read_required(prompt, read=input, write=print):
    while True:
        value = read(prompt).strip()
        if value:
            return value
        write("Please enter a value; blank input is not accepted.")


def read_skills(read=input, write=print):
    while True:
        value = read_required("\nEnter skills separated by commas (or 'none'): ", read, write)
        if value.casefold() == "none":
            return []
        skills = normalise_skills(value)
        if skills:
            return skills
        write("Please enter at least one skill, or type 'none'.")


def read_job(multiline=False, read=input, write=print):
    if not multiline:
        return read_required("\nPaste a job description here: ", read, write)
    write("Paste the job description over multiple lines. Finish with a blank line.")
    first = read_required("Job description: ", read, write)
    lines = [first]
    while True:
        line = read("")
        if not line.strip():
            return "\n".join(lines)
        lines.append(line)


def ask_again(read=input, write=print):
    while True:
        answer = read("\nWould you like to analyse another job? (yes/no): ").strip().casefold()
        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False
        write("Please answer yes/y or no/n.")


def run_session(report_path=DEFAULT_REPORT_PATH, multiline=False, read=input, write=print):
    write("=== AI Job & Apprenticeship Assistant ===")
    write("Local rule-based analysis. No external AI service is used.")
    name = read_required("What is your name? ", read, write)
    write(f"\nWelcome, {name}!")
    user_skills = read_skills(read, write)
    write("\nYour current skills are:")
    for skill in user_skills:
        write(f"- {skill}")
    if not user_skills:
        write("No skills entered yet.")
    matching, missing = check_skills(user_skills, REQUIRED_SKILLS)
    write("\n=== AI Developer Skill Check ===")
    write("Skills you already have: " + (", ".join(matching) or "None recognised"))
    write("Skills you should learn: " + (", ".join(missing) or "None from this catalogue"))
    write(f"AI Developer Match Score: {calculate_match(matching, REQUIRED_SKILLS):.0f}%")
    write("This is coverage of a fixed learning catalogue, not a readiness assessment.")
    save_failed = False
    while True:
        write("\n=== Job Description Analyser ===")
        analysis = analyse_job(user_skills, read_job(multiline, read, write))
        write(format_analysis(analysis))
        try:
            number = save_analysis(analysis, report_path)
        except (OSError, UnicodeError) as error:
            save_failed = True
            write(f"Could not save report to {report_path}: {error}")
            write("The analysis is shown above. Check the path and permissions before trying again.")
        else:
            write(f"Your job analysis has been saved! Report #{number}: {report_path}")
        if not ask_again(read, write):
            return 1 if save_failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local rule-based job skills comparison")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH,
                        help="Report path (default: job_analysis.txt beside main.py)")
    parser.add_argument("--multiline", action="store_true",
                        help="Read job descriptions until a blank line")
    from .storage import DEFAULT_DATABASE
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE,
                        help="Local SQLite path (default: local_data/assistant.sqlite3)")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("profile-create", help="Review and save a local profile")
    commands.add_parser("profile-list", help="List local profiles")
    importer = commands.add_parser("cv-import", help="Extract, review and save a CV")
    importer.add_argument("path", type=Path)
    importer.add_argument("--profile", type=int, required=True)
    listing = commands.add_parser("cv-list", help="List saved CV metadata")
    listing.add_argument("--profile", type=int)
    showing = commands.add_parser("cv-show", help="Retrieve saved CV text and references")
    showing.add_argument("id", type=int)
    showing.add_argument("--source", action="store_true", help="Show original extraction instead of corrections")
    deletion = commands.add_parser("cv-delete", help="Delete a CV and all its stored content")
    deletion.add_argument("id", type=int)
    analysis = commands.add_parser("cv-analyse", help="Analyse a reviewed CV offline, with optional OpenAI suggestions")
    analysis.add_argument("id", type=int)
    analysis.add_argument("--output", type=Path, help="Offer to save a private report at a new path")
    analysis.add_argument("--openai", action="store_true", help="Offer an explicit, paid external-data opt-in")
    analysis.add_argument("--model", help="Explicit Responses API model supporting structured outputs; no default")
    comparison = commands.add_parser("job-compare", help="Compare entered/imported job requirements with an approved CV offline")
    comparison.add_argument("id", type=int, help="Approved imported CV ID")
    comparison.add_argument("--job-file", type=Path, help="Explicit local TXT/PDF/DOCX job description; otherwise enter text")
    comparison.add_argument("--output", type=Path, help="Offer to save the displayed comparison at a new path")
    comparison.add_argument("--openai", action="store_true", help="Offer separately consented AI interpretations; offline results stay authoritative")
    comparison.add_argument("--model", help="Explicit Responses API model supporting structured outputs")
    comparison.add_argument("--input-usd-per-million", help="Current model input price in USD per million tokens (required for AI estimate)")
    comparison.add_argument("--output-usd-per-million", help="Current model output price in USD per million tokens (required for AI estimate)")
    comparison.add_argument("--max-estimated-usd", default="0.25", help="Reject AI request if estimated cost exceeds this USD amount (default 0.25)")
    comparison.add_argument("--store", action="store_true", help="Offer to persist comparison provenance/counts without document excerpts")
    from .application_cli import register_commands
    register_commands(commands)
    from .interview_cli import register_commands as register_interview_commands
    register_interview_commands(commands)
    args = parser.parse_args(argv)
    try:
        if args.command and args.command.startswith("interview-"):
            from .interview_cli import run_command
            return run_command(args)
        if args.command and args.command.startswith(("application-", "comparison-")):
            from .application_cli import run_command
            return run_command(args)
        if args.command == "job-compare":
            from .job_cli import run_comparison
            return run_comparison(args)
        if args.command == "cv-analyse":
            from .analysis_cli import run_analysis
            return run_analysis(args)
        if args.command:
            from .cv_cli import run_command
            return run_command(args)
        return run_session(args.report, args.multiline)
    except (EOFError, KeyboardInterrupt):
        print("\nSession ended. Only completed, confirmed saves are stored.")
        return 130
