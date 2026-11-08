"""Synthetic presentation checks; feedback cards never regenerate or send data."""

from streamlit.testing.v1 import AppTest

from job_assistant.interview_feedback import analyse_answer
from job_assistant.interview_questions import question

ANSWER = "Situation: During college our parser rejected rows.\nTask: My task was to check the input.\nAction: I tested the parser with synthetic data.\nResult: I learned how to check unexpected input."


def render(feedback):
    at = AppTest.from_string('''
import streamlit as st
from job_assistant.dashboard_feedback import render_feedback
render_feedback(st.session_state["synthetic_feedback"])
''')
    at.session_state["synthetic_feedback"] = feedback
    at.run()
    assert not at.exception
    return at


def test_behavioural_cards_show_structure_guidance_and_exact_citations():
    feedback = analyse_answer(ANSWER, question("synthetic", "behavioural", "Describe a project"))
    at = render(feedback)
    headings = [m.value for m in at.markdown]
    for part in ("Situation", "Task", "Action", "Result"):
        assert "##### " + part in headings
    shown = "\n".join(t.value for t in at.text)
    for part in feedback["star"].values():
        assert part["guidance"] in shown
        for evidence in part["answer_evidence"]:
            assert evidence["quote"] in shown
    assert any("Answer characters" in c.value for c in at.caption)
    assert not any("=== Offline Interview Feedback" in t.value for t in at.text)


def test_technical_answer_keeps_star_optional():
    at = render(analyse_answer("I would test invalid inputs and explain limitations.", question("synthetic", "technical", "Explain a test")))
    assert any("STAR is optional" in i.value for i in at.info)
    assert not any(m.value == "##### Situation" for m in at.markdown)


def test_candidate_html_and_external_images_are_literal_text():
    attack = '<script>alert("synthetic")</script> ![image](https://example.com/pixel)'
    feedback = analyse_answer("Action: " + attack, question("synthetic", "behavioural", "Describe a project"))
    at = render(feedback)
    assert attack in "\n".join(t.value for t in at.text)
    assert all(attack not in m.value for m in at.markdown)
    assert not at.get("imgs")


def test_all_claim_states_clarity_and_limitations_remain_visible():
    feedback = analyse_answer(ANSWER, question("synthetic", "behavioural", "Describe a project"))
    original = feedback["claims"][0]
    feedback["claims"] = [dict(original, state=state, cv_evidence=None) for state in ("supported_wording", "answer_only", "uncertain")]
    feedback["claims_truncated"] = True
    feedback["clarity"]["repeated_wording"] = True
    at = render(feedback)
    labels = [e.label for e in at.expander]
    assert "CV-supported wording · 1" in labels
    assert "Answer-only claims · 1" in labels
    assert "Uncertain or tentative claims · 1" in labels
    assert any("first 12" in c.value for c in at.caption)
    shown = "\n".join(t.value for t in at.text)
    assert "Some wording repeats" in shown
    assert all(item in shown for item in feedback["limitations"] + feedback["career_practice"])


def test_empty_claims_do_not_imply_verified_ability():
    at = render(analyse_answer("A short synthetic answer", question("synthetic", "behavioural", "Describe a project")))
    assert sum("No claims recognised" in c.value for c in at.caption) == 3
    assert any("not a quality grade" in c.value for c in at.caption)


def test_recorded_ai_coaching_stays_separate_from_offline_feedback():
    feedback = analyse_answer(ANSWER, question("synthetic", "behavioural", "Describe a project"))
    feedback["ai_coaching"] = {"notice": "Synthetic recorded AI notice", "suggestions": [
        {"guidance": "Synthetic guidance", "answer_evidence": {"start": 0, "end": 9, "quote": ANSWER[:9]}}]}
    at = render(feedback)
    assert any(m.value == "#### Recorded optional AI coaching" for m in at.markdown)
    assert any(t.value == "Synthetic recorded AI notice" for t in at.text)
    assert not at.button
