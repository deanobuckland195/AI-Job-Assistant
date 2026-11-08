"""Transactional interview sessions, snapshotted questions and append-only attempts."""

import hashlib
import json

from . import storage
from .applications import positive_id, text_field, write_transaction
from .cv_analysis import AnalysisError, analyse_cv
from .interview_feedback import FEEDBACK_VERSION, InterviewError, analyse_answer, validate_answer
from .interview_questions import BANK_VERSION, ROLES, questions_for

MAX_ATTEMPTS = 50


def start_session(connection, role_id, *, title=None, count=6, cv_id=None):
    try:
        bank = questions_for(role_id, count)
    except ValueError as error:
        raise InterviewError(str(error)) from None
    title = text_field(title if title is not None else ROLES[role_id], "Session title", 120, required=True)
    with write_transaction(connection):
        original_id = approved = digest = None
        if cv_id is not None:
            positive_id(cv_id, "CV")
            analysis = analyse_cv(storage.get_cv(connection, cv_id))
            original_id, approved, digest = cv_id, analysis.reviewed_at, analysis.source_digest
        cursor = connection.execute("""INSERT INTO interview_sessions
            (role_id,title,bank_version,created_at,cv_id,cv_original_id,cv_reviewed_at,cv_digest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (role_id, title, BANK_VERSION, storage.timestamp(), cv_id, original_id, approved, digest))
        session_id = cursor.lastrowid
        connection.executemany("""INSERT INTO interview_questions
            (session_id,number,code,kind,prompt,guidance_json,topics_json) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(session_id, number, q["code"], q["kind"], q["prompt"], json.dumps(q["guidance"]), json.dumps(q["topics"]))
             for number, q in enumerate(bank, 1)])
    return session_id


def get_session(connection, session_id):
    positive_id(session_id, "Session")
    row = connection.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise InterviewError("Practice session not found. Use interview-list to find a saved session.")
    result = dict(row)
    result["questions"] = []
    for question in connection.execute("SELECT * FROM interview_questions WHERE session_id = ? ORDER BY number", (session_id,)):
        item = dict(question)
        item["guidance"] = storage.decode_json(item.pop("guidance_json"))
        item["topics"] = storage.decode_json(item.pop("topics_json"))
        item["answers"] = [dict(answer) for answer in connection.execute(
            "SELECT id,attempt,created_at FROM interview_answers WHERE session_id = ? AND question_number = ? ORDER BY attempt", (session_id, item["number"]))]
        result["questions"].append(item)
    return result


def list_sessions(connection, limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 9223372036854775807:
        raise InterviewError("Use a session limit from 1 to 1,000 and a non-negative offset.")
    return [dict(row) for row in connection.execute(
        "SELECT id,role_id,title,created_at,cv_original_id FROM interview_sessions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))]


def session_cv(connection, session):
    if session["cv_id"] is None:
        return None, "Linked CV was deleted; recorded approval metadata remains" if session["cv_original_id"] else "No CV linked"
    try:
        cv = storage.get_cv(connection, session["cv_id"])
        analysis = analyse_cv(cv)
    except (storage.StorageError, AnalysisError):
        return None, "Linked approved CV is unavailable; no replacement CV was used"
    if analysis.source_digest != session["cv_digest"] or analysis.reviewed_at != session["cv_reviewed_at"]:
        return None, "Linked CV no longer matches the session's approved version; no replacement CV was used"
    return cv, "Linked approved CV version available; corroboration is wording-only"


def assess_answer(connection, session_id, question_number, text):
    positive_id(question_number, "Question number")
    session = get_session(connection, session_id)
    question = next((q for q in session["questions"] if q["number"] == question_number), None)
    if question is None:
        raise InterviewError("Question not found in this session. Use interview-show to see its question numbers.")
    text = validate_answer(text)
    cv, availability = session_cv(connection, session)
    feedback = analyse_answer(text, question, role_id=session["role_id"], cv=cv, cv_availability=availability)
    payload = {"answer": text, "feedback": feedback,
               "question": {k: question[k] for k in ("code", "kind", "prompt", "guidance", "topics")},
               "cv_digest": session["cv_digest"], "cv_reviewed_at": session["cv_reviewed_at"]}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return {"session": session, "question": question, "answer": text, "feedback": feedback, "review_digest": digest}


def record_answer(connection, session_id, question_number, text, *, expected_review_digest=None, coaching=None):
    with write_transaction(connection):
        assessed = assess_answer(connection, session_id, question_number, text)
        if expected_review_digest is not None and assessed["review_digest"] != expected_review_digest:
            raise InterviewError("Available question/evidence changed since review. Review feedback again before saving.")
        attempt = assessed["question"]["next_attempt"]
        if attempt > MAX_ATTEMPTS:
            raise InterviewError("This question has reached 50 recorded attempts. Start a new practice session.")
        if coaching is not None:
            if expected_review_digest is None:
                raise InterviewError("Review the answer before saving AI coaching.")
            # Revalidate the snapshot against the answer; saving never calls a provider.
            from .openai_interview import COACHING_VERSION, FALLBACK, validate_suggestions
            if not isinstance(coaching, dict) or coaching.get("version") != COACHING_VERSION:
                raise InterviewError("Invalid coaching snapshot; review feedback again.")
            if coaching.get("status") == "validated":
                items = coaching.get("suggestions")
                if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("answer_evidence"), dict) for item in items):
                    raise InterviewError("Invalid coaching snapshot; review feedback again.")
                payload = {"suggestions": [{"action": item.get("action"),
                           "start": item.get("answer_evidence", {}).get("start"),
                           "quote": item.get("answer_evidence", {}).get("quote")} for item in items]}
                suggestions = validate_suggestions(payload, assessed["answer"], assessed["question"])
                model = coaching.get("model")
                from .openai_interview import prepare_request
                prepare_request(assessed["answer"], assessed["question"], model)
                assessed["feedback"]["ai_coaching"] = {"version": COACHING_VERSION,
                    "status": "validated", "model": model, "suggestions": suggestions,
                    "notice": "AI-selected coaching prompts; review required. CV text was not sent."}
            elif coaching.get("status") == "offline_fallback":
                assessed["feedback"]["ai_coaching"] = {"version": COACHING_VERSION,
                    "status": "offline_fallback", "suggestions": [], "notice": FALLBACK}
            else:
                raise InterviewError("Invalid coaching snapshot; review feedback again.")
        feedback = json.dumps(assessed["feedback"], ensure_ascii=True, sort_keys=True)
        if len(feedback) > 100000:
            raise InterviewError("Feedback exceeds the local storage limit; use a shorter answer.")
        cursor = connection.execute("""INSERT INTO interview_answers
            (session_id,question_number,attempt,answer,answer_digest,feedback_json,feedback_version,created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, question_number, attempt, assessed["answer"], hashlib.sha256(assessed["answer"].encode()).hexdigest(),
             feedback, FEEDBACK_VERSION, storage.timestamp()))
        connection.execute("UPDATE interview_questions SET next_attempt = ? WHERE session_id = ? AND number = ?", (attempt + 1, session_id, question_number))
    return cursor.lastrowid


def get_answer(connection, answer_id):
    positive_id(answer_id, "Answer")
    row = connection.execute("SELECT * FROM interview_answers WHERE id = ?", (answer_id,)).fetchone()
    if row is None:
        raise InterviewError("Practice answer not found. Use interview-show to see saved answer IDs.")
    result = dict(row)
    result["feedback"] = storage.decode_json(result.pop("feedback_json"))
    if not isinstance(result["feedback"], dict) or result["feedback"].get("version") != result["feedback_version"]:
        raise InterviewError("Stored feedback format is invalid. Restore a known-good private backup.")
    return result


def session_review_digest(session):
    return hashlib.sha256(json.dumps(session, ensure_ascii=True, sort_keys=True).encode()).hexdigest()


def delete_session(connection, session_id, *, expected_review_digest=None):
    with write_transaction(connection):
        current = get_session(connection, session_id)
        if expected_review_digest is not None and session_review_digest(current) != expected_review_digest:
            raise InterviewError("Practice session changed since review. Review it again before deleting.")
        connection.execute("DELETE FROM interview_sessions WHERE id = ?", (session_id,))


def delete_answer(connection, answer_id):
    with write_transaction(connection):
        get_answer(connection, answer_id)
        connection.execute("DELETE FROM interview_answers WHERE id = ?", (answer_id,))
