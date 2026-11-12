"""Deliberate review/send/save workflow for local interview practice."""

import streamlit as st

from . import interview_store as practice, storage
from .dashboard_feedback import render_feedback
from .interview_questions import ROLES
from .openai_interview import coach_answer


def render(path):
    st.subheader("Start a practice session")
    st.caption("Practise locally for free. Answers and feedback are local plaintext. AI coaching is optional and requires a separate send action.")
    with st.form("practice_create"):
        role_col, title_col = st.columns(2)
        with role_col:
            role = st.selectbox("Practice role", list(ROLES), format_func=ROLES.get, key="practice_role")
        with title_col:
            title = st.text_input("Session title", max_chars=120, key="practice_title")
        with storage.database(path) as connection:
            cvs = [row[0] for row in connection.execute("SELECT id FROM cvs WHERE reviewed_at != '' ORDER BY id DESC")]
        cv_id = st.selectbox("Optional approved CV for local corroboration", [None, *cvs],
                             format_func=lambda v: "No CV linked" if v is None else f"CV #{v}", key="practice_cv")
        st.caption("Only an explicitly selected approved CV is read for local wording checks. CV text is never sent for AI coaching.")
        create = st.form_submit_button("Start practice session", type="primary")
    if create:
        with storage.database(path) as connection:
            selected = practice.start_session(connection, role, title=title.strip() or None, cv_id=cv_id)
        st.session_state["practice_session"] = selected
        st.session_state.pop("practice_review", None)
        st.success("Practice session created.")
    with storage.database(path) as connection:
        sessions = practice.list_sessions(connection, limit=1000)
    if not sessions:
        st.info("Start a session to practise curated questions and save answer attempts.")
        return
    st.caption("Showing the newest 1,000 sessions. Older sessions remain available through the CLI.")
    labels = {s["id"]: f"#{s['id']} · {s['title']}" for s in sessions}
    if st.session_state.get("practice_session") not in labels:
        st.session_state["practice_session"] = sessions[0]["id"]
    session_col, question_col = st.columns([1.4, 1])
    with session_col:
        selected = st.selectbox("Practice session", list(labels), format_func=labels.get, key="practice_session")
    with storage.database(path) as connection:
        session = practice.get_session(connection, selected)
    with question_col:
        question_number = st.selectbox("Practice question", [q["number"] for q in session["questions"]], key=f"practice_question_{selected}")
    question = next(q for q in session["questions"] if q["number"] == question_number)
    st.divider()
    st.subheader("Practise your answer")
    prefix = f"practice_{selected}_{question_number}"
    with st.container(key="interview_workspace"):
        question_panel, answer_panel = st.columns([1, 1.25], gap="large")
        with question_panel.container(border=True, key="interview_question_card"):
            st.caption("01 / YOUR QUESTION")
            with st.container(key="interview_question_prompt"):
                st.text(question["prompt"])
            st.badge(question["kind"].title(), color="violet")
            st.markdown("#### Approach your answer")
            for tip in question["guidance"]:
                st.text(tip)
        with answer_panel.container(border=True, key="interview_answer_card"):
            st.caption("02 / YOUR RESPONSE")
            text = st.text_area("Your practice answer", max_chars=8000, height=300, key=prefix + "_answer")
            review_clicked = st.button("Review offline feedback", key=prefix + "_review", type="primary", width="stretch")
            st.caption("Review first. Save an attempt only when you are ready.")
    if review_clicked:
        # Clear the previous result first, including on validation failure.
        st.session_state.pop("practice_review", None)
        st.session_state[prefix + "_consent"] = False
        with storage.database(path) as connection:
            assessment = practice.assess_answer(connection, selected, question_number, text)
        st.session_state["practice_review"] = {"session_id": selected, "question_number": question_number,
                                               "assessment": assessment, "coaching": None}
    review = st.session_state.get("practice_review")
    if review and (review["session_id"], review["question_number"], review["assessment"]["answer"]) == (selected, question_number, text.strip()):
        assessment = review["assessment"]
        render_feedback(assessment["feedback"])
        # Consent is deliberately in a form so reruns cannot accidentally send.
        with st.form(prefix + "_ai"):
            st.markdown("#### Optional AI coaching")
            st.caption("Send only the displayed question and answer to OpenAI. This may incur API charges. No CV text, titles, notes or other records are sent. Provider retention policies apply; store=false is requested.")
            model = st.text_input("OpenAI model ID", key=prefix + "_model", max_chars=80)
            consent = st.checkbox("I consent to sending this question and answer to OpenAI for this request", value=False, key=prefix + "_consent")
            send = st.form_submit_button("Request AI coaching once")
        if send:
            if not consent:
                st.error("Explicit consent is required. Nothing was sent; offline feedback remains available.")
            else:
                review["coaching"] = coach_answer(assessment["answer"], question, model, consent=True)
        if review["coaching"]:
            coaching = review["coaching"]
            if coaching["status"] == "offline_fallback":
                st.warning(coaching["notice"])
            else:
                st.text(coaching["notice"])
            for item in coaching["suggestions"]:
                st.text(item["guidance"])
                st.text(f"Answer chars {item['answer_evidence']['start']}:{item['answer_evidence']['end']}: {item['answer_evidence']['quote']}")
        if st.button("Save reviewed attempt", key=prefix + "_save"):
            with storage.database(path) as connection:
                answer_id = practice.record_answer(connection, selected, question_number, text,
                    expected_review_digest=assessment["review_digest"], coaching=review["coaching"])
            st.session_state.pop("practice_review", None)
            st.session_state["notice"] = f"Practice answer #{answer_id} saved."
            st.rerun()
    elif review:
        st.info("Answer or question changed. Review offline feedback again before requesting AI or saving.")
    if question["answers"]:
        st.divider()
        st.subheader("Saved attempts")
        answer_id = st.selectbox("Saved attempt", [a["id"] for a in question["answers"]], key=prefix + "_history")
        with storage.database(path) as connection:
            answer = practice.get_answer(connection, answer_id)
        st.caption(f"Attempt {answer['attempt']} · {answer['created_at']} · feedback as recorded, never silently regenerated")
        st.text(answer["answer"])
        render_feedback(answer["feedback"])
        st.caption("Answer deletion cannot be undone in the app. Other attempts are retained.")
        acknowledged = st.checkbox("Delete this saved answer and its feedback", key=f"practice_delete_answer_{answer_id}")
        if st.button("Confirm answer deletion", disabled=not acknowledged, key=f"practice_delete_answer_button_{answer_id}"):
            with storage.database(path) as connection:
                practice.delete_answer(connection, answer_id)
            st.rerun()
    with st.expander("Delete practice session"):
        st.caption("Cannot be undone in the app. Removes this session, questions and all attempts. CVs, applications and reports are retained.")
        digest = practice.session_review_digest(session)
        acknowledged = st.checkbox("I understand this removes all attempts in this session", key=f"practice_delete_session_{selected}_{digest}")
        if st.button("Confirm session deletion", disabled=not acknowledged, key=f"practice_delete_session_button_{selected}"):
            with storage.database(path) as connection:
                practice.delete_session(connection, selected, expected_review_digest=digest)
            st.session_state.pop("practice_review", None)
            st.rerun()
