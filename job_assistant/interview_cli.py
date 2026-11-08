"""Offline interview CLI; review before saving and confirm deletions."""

import sqlite3

from . import storage, interview_store as practice
from .applications import ApplicationError
from .cv_analysis import AnalysisError
from .cv_cli import confirm, safe_display
from .interview_feedback import InterviewError, MAX_ANSWER_CHARS, MAX_LINES, MAX_LINE_CHARS
from .interview_questions import ROLES, STAR


def register_commands(commands):
    commands.add_parser("interview-roles", help="List curated offline practice roles")
    start = commands.add_parser("interview-start", help="Review and save a role-specific practice session")
    start.add_argument("--role", choices=ROLES, required=True)
    start.add_argument("--count", type=int, default=6)
    start.add_argument("--title")
    start.add_argument("--cv", type=int, help="Explicit approved CV ID for optional wording corroboration")
    listing = commands.add_parser("interview-list", help="List local practice sessions")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)
    showing = commands.add_parser("interview-show", help="Show saved questions, guidance and attempt IDs")
    showing.add_argument("id", type=int)
    answer = commands.add_parser("interview-answer", help="Review feedback and record a new answer attempt")
    answer.add_argument("id", type=int, help="Session ID")
    answer.add_argument("--question", type=int, required=True)
    inputs = answer.add_mutually_exclusive_group()
    inputs.add_argument("--answer", help="Answer text; interactive input avoids placing personal answers in shell history")
    inputs.add_argument("--star", action="store_true", help="Enter Situation, Task, Action and Result separately")
    answer.add_argument("--ai", action="store_true", help="Optionally request answer-only AI coaching after explicit consent")
    answer.add_argument("--model", help="Explicit OpenAI model ID; no default or automatic calls")
    for name in ("interview-answer-show", "interview-feedback", "interview-delete", "interview-answer-delete"):
        parser = commands.add_parser(name, help="Review a practice record or confirm its deletion")
        parser.add_argument("id", type=int)


def read_text(read, write):
    write("Enter answer text; blank lines are allowed. Finish with /done on its own line.")
    lines, length = [], 0
    while True:
        line = read("")
        if line == "/done":
            return "\n".join(lines)
        length += len(line) + (1 if lines else 0)
        if len(line) > MAX_LINE_CHARS or len(lines) >= MAX_LINES or length > MAX_ANSWER_CHARS:
            raise InterviewError("Answer exceeds 8,000 characters, 100 lines or 2,000 characters per line. Nothing was saved.")
        lines.append(line)


def format_feedback(feedback):
    lines = ["=== Offline Interview Feedback ===", f"Feedback rules: {feedback['version']} · words: {feedback['word_count']}",
             "Coaching cues only. No quality score, hiring prediction or independently verified achievements.",
             "CV availability at assessment: " + safe_display(feedback["cv_availability"]), "\nSTAR GUIDANCE"]
    for label, part in feedback["star"].items():
        lines.append(f"- {label.title()}: {part['state']}. {part['guidance']}")
        for evidence in part["answer_evidence"]:
            lines.append(f"  Answer chars {evidence['start']}:{evidence['end']}: {safe_display(evidence['quote'])}")
    for state, heading in (("supported_wording", "CV-SUPPORTED WORDING (not independently verified achievements)"),
                           ("answer_only", "ANSWER-ONLY CLAIMS (not corroborated)"), ("uncertain", "UNCERTAIN / TENTATIVE CLAIMS")):
        lines.append("\n" + heading)
        claims = [c for c in feedback["claims"] if c["state"] == state]
        if not claims:
            lines.append("None recognised.")
        for claim in claims:
            evidence = claim["answer_evidence"]
            lines.append(f"- Answer chars {evidence['start']}:{evidence['end']}: {safe_display(evidence['quote'])}" + (" [excerpt clipped]" if evidence["truncated"] else ""))
            lines.append("  " + claim["reason"])
            if claim["cv_evidence"]:
                cv = claim["cv_evidence"]
                lines.append(f"  CV unit {cv['position']}: {safe_display(cv['reference'])}, reviewed chars {cv['start']}:{cv['end']}" + (" [corrected text]" if cv["corrected"] else ""))
    lines.append("\nCLARITY CUES (heuristics, not a quality grade)")
    for key, label in (("long_sentences", "Long sentence"), ("vague_wording", "Vague wording")):
        for evidence in feedback["clarity"][key]:
            lines.append(f"- {label}, answer chars {evidence['start']}:{evidence['end']}: {safe_display(evidence['quote'])}")
    if feedback["clarity"]["repeated_wording"]:
        lines.append("- Repeated wording detected; review concision without losing important context.")
    lines.append("\nMISSING DETAIL / REVIEW")
    lines.extend("- " + item for item in feedback["missing_detail"])
    lines.append("\nSUGGESTIONS (conditional; never add unsupported facts)")
    lines.extend("- " + item for item in feedback["suggestions"])
    lines.append("\nCAREER PRACTICE NEXT STEPS (suggestions, not candidate facts)")
    lines.extend("- " + item for item in feedback["career_practice"])
    if feedback["claims_truncated"]:
        lines.append("Only the first 12 recognised claims are displayed/checked; this is not an exhaustive inventory.")
    if "ai_coaching" in feedback:
        ai = feedback["ai_coaching"]
        lines.append("\nOPTIONAL AI COACHING · " + safe_display(ai["status"]))
        lines.append(safe_display(ai["notice"]))
        for item in ai["suggestions"]:
            evidence = item["answer_evidence"]
            lines.append(f"- {item['guidance']} Answer chars {evidence['start']}:{evidence['end']}: {safe_display(evidence['quote'])}")
    lines.append("\nLIMITATIONS")
    lines.extend("- " + item for item in feedback["limitations"])
    return "\n".join(lines)


def format_session(session):
    lines = [f"=== Practice session {session['id']}: {safe_display(session['title'])} ===",
             f"Role: {safe_display(session['role_id'])} · bank {safe_display(session['bank_version'])} · created {safe_display(session['created_at'])}"]
    if session["cv_original_id"]:
        lines.append(f"CV approval version #{session['cv_original_id']}; live link: {session['cv_id'] or '(deleted)'}; approved {safe_display(session['cv_reviewed_at'])}")
    else:
        lines.append("No CV linked; answers remain fully usable offline without CV corroboration.")
    for question in session["questions"]:
        lines.append(f"\n{question['number']}. [{question['kind']}] {safe_display(question['prompt'])}")
        lines.extend("   Guidance: " + safe_display(item) for item in question["guidance"])
        lines.append("   Saved attempts: " + (", ".join(f"#{a['id']} (attempt {a['attempt']})" for a in question["answers"]) or "None"))
    return "\n".join(lines)


def run_command(args, read=input, write=print):
    try:
        if args.command == "interview-roles":
            for role_id, label in ROLES.items():
                write(f"{role_id}: {label}")
            return 0
        if args.command == "interview-start":
            from .interview_questions import questions_for
            try:
                bank = questions_for(args.role, args.count)
            except ValueError as error:
                raise InterviewError(str(error)) from None
            write(f"Practice role: {ROLES[args.role]}; {len(bank)} curated questions. No AI service is used.")
            for i, question in enumerate(bank, 1):
                write(f"{i}. [{question['kind']}] {question['prompt']}")
            write("Answers are local plaintext. CV corroboration is optional and never verifies real-world achievement.")
            if confirm("Save this practice session? (yes/no)", read, write):
                with storage.database(args.database) as connection:
                    session_id = practice.start_session(connection, args.role, title=args.title, count=args.count, cv_id=args.cv)
                write(f"Practice session saved with ID {session_id}.")
            else:
                write("Cancelled; no session saved.")
        elif args.command == "interview-answer":
            with storage.database(args.database) as connection:
                session = practice.get_session(connection, args.id)
            question = next((q for q in session["questions"] if q["number"] == args.question), None)
            if question is None:
                raise InterviewError("Question not found in this session.")
            write(safe_display(question["prompt"]))
            for tip in question["guidance"]:
                write("Guidance: " + safe_display(tip))
            if args.star:
                parts = []
                for name, guidance in STAR.items():
                    write(name.title() + ": " + guidance)
                    parts.append(name.title() + ": " + read_text(read, write))
                text = "\n".join(parts)
            else:
                text = args.answer if args.answer is not None else read_text(read, write)
            with storage.database(args.database) as connection:
                assessment = practice.assess_answer(connection, args.id, args.question, text)
            coaching = None
            if args.ai:
                if not args.model:
                    raise InterviewError("Use --model with --ai. Offline practice needs neither.")
                write("Only this question and answer will be sent to OpenAI, which may charge your account. CV text, session titles and other records are excluded. Provider retention policies apply; store=false is requested.")
                write("Question: " + safe_display(question["prompt"]) + "\nAnswer: " + safe_display(assessment["answer"]))
                if confirm("Send this question and answer once for AI coaching? (yes/no)", read, write):
                    from .openai_interview import coach_answer
                    coaching = coach_answer(assessment["answer"], question, args.model, consent=True)
                    assessment["feedback"]["ai_coaching"] = coaching
                else:
                    write("AI cancelled; offline feedback remains available.")
            write("\nAnswer to save:\n" + safe_display(assessment["answer"]))
            write(format_feedback(assessment["feedback"]))
            if confirm("Save this answer and feedback as a new attempt? (yes/no)", read, write):
                with storage.database(args.database) as connection:
                    answer_id = practice.record_answer(connection, args.id, args.question, assessment["answer"], expected_review_digest=assessment["review_digest"], coaching=coaching)
                write(f"Practice answer saved with ID {answer_id}.")
            else:
                write("Cancelled; no answer saved.")
        elif args.command in {"interview-answer-show", "interview-feedback", "interview-answer-delete"}:
            with storage.database(args.database) as connection:
                answer = practice.get_answer(connection, args.id)
                session = practice.get_session(connection, answer["session_id"])
            write(f"Answer #{answer['id']} · session {answer['session_id']} · question {answer['question_number']} · attempt {answer['attempt']} · {safe_display(answer['created_at'])}")
            if args.command != "interview-feedback":
                write("Recorded answer:\n" + safe_display(answer["answer"]))
            write("Feedback describes evidence available at recording time; it is not silently regenerated.")
            if session["cv_original_id"] and session["cv_id"] is None:
                write("Linked CV is now deleted. Recorded reference metadata remains, but its source cannot be rechecked here.")
            if args.command == "interview-answer-delete":
                if confirm("Delete this answer and its feedback? Other attempts and CVs are retained. (yes/no)", read, write):
                    with storage.database(args.database) as connection:
                        practice.delete_answer(connection, args.id)
                    write("Practice answer and feedback deleted.")
                else:
                    write("Cancelled; nothing deleted.")
            else:
                write(format_feedback(answer["feedback"]))
        elif args.command == "interview-list":
            with storage.database(args.database) as connection:
                sessions = practice.list_sessions(connection, args.limit, args.offset)
            for session in sessions:
                write(f"{session['id']}: {safe_display(session['title'])} | {safe_display(session['role_id'])} | {safe_display(session['created_at'])}")
            write(f"Listed {len(sessions)} practice session(s).")
        else:
            with storage.database(args.database) as connection:
                session = practice.get_session(connection, args.id)
            write(format_session(session))
            if args.command == "interview-delete":
                if confirm("Delete this session, its questions and all answer/feedback attempts? CVs/applications/reports remain. (yes/no)", read, write):
                    with storage.database(args.database) as connection:
                        practice.delete_session(connection, args.id, expected_review_digest=practice.session_review_digest(session))
                    write("Practice session, questions and answers deleted.")
                else:
                    write("Cancelled; nothing deleted.")
        return 0
    except (InterviewError, ApplicationError, storage.StorageError, AnalysisError) as error:
        write(str(error))
    except (OSError, sqlite3.Error):
        write("Local practice operation failed. Check database permissions, space or locks; no incomplete attempt was saved.")
    return 1
