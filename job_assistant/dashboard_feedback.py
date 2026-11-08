"""Read-only interview feedback cards. Candidate text is always rendered as text."""

import streamlit as st

STATE_LABELS = {
    "explicit_detail": "Detail supplied · review relevance",
    "possible_detail": "Possible detail · check the meaning",
    "missing_detail": "More detail needed",
    "ambiguous_labels": "Repeated labels · clarify structure",
    "not_required": "Optional for this question",
}


def evidence_text(evidence):
    st.caption(f"Answer characters {evidence['start']}–{evidence['end']}" + (" · excerpt clipped" if evidence.get("truncated") else ""))
    st.text(evidence["quote"])


def render_feedback(feedback):
    st.subheader("Answer feedback")
    st.caption(f"Offline rules {feedback['version']} · {feedback['word_count']} words · coaching cues, not a score or hiring prediction")
    st.text("CV availability: " + feedback["cv_availability"])
    if feedback["question_kind"] == "behavioural":
        st.markdown("#### STAR structure")
        parts = list(feedback["star"].items())
        for start in (0, 2):
            for column, (name, part) in zip(st.columns(2), parts[start:start + 2]):
                with column.container(border=True):
                    st.markdown("##### " + name.title())
                    st.text(STATE_LABELS.get(part["state"], "Review this section"))
                    st.text(part["guidance"])
                    for evidence in part["answer_evidence"]:
                        evidence_text(evidence)
    else:
        st.info("STAR is optional for this question. Give a direct explanation, your reasoning, a truthful example where useful, and limitations.")
    st.markdown("#### Evidence behind your claims")
    st.caption("CV-supported wording is not independent verification. Missing corroboration does not mean a claim is false.")
    headings = {"supported_wording": "CV-supported wording", "answer_only": "Answer-only claims", "uncertain": "Uncertain or tentative claims"}
    for state, heading in headings.items():
        claims = [claim for claim in feedback["claims"] if claim["state"] == state]
        with st.expander(f"{heading} · {len(claims)}", expanded=bool(claims)):
            if not claims:
                st.caption("No claims recognised in this category.")
            for claim in claims:
                with st.container(border=True):
                    evidence_text(claim["answer_evidence"])
                    st.text(claim["reason"])
                    if claim["cv_evidence"]:
                        cv = claim["cv_evidence"]
                        st.text(f"CV unit {cv['position']} · {cv['reference']} · reviewed characters {cv['start']}–{cv['end']}" + (" · corrected text" if cv["corrected"] else ""))
    if feedback["claims_truncated"]:
        st.caption("Only the first 12 recognised claims were checked; this is not an exhaustive inventory.")
    with st.expander("Clarity and missing detail", expanded=True):
        has_clarity = False
        for key, heading in (("long_sentences", "Long sentence"), ("vague_wording", "Vague wording")):
            for evidence in feedback["clarity"][key]:
                has_clarity = True
                st.text(heading)
                evidence_text(evidence)
        if feedback["clarity"]["repeated_wording"]:
            has_clarity = True
            st.text("Some wording repeats; review concision without losing context.")
        if not has_clarity:
            st.caption("No clarity cues recognised by these heuristics; this is not a quality grade.")
        for item in feedback["missing_detail"]:
            st.text("• " + item)
    with st.container(border=True):
        st.markdown("#### Suggested next steps")
        if not feedback["suggestions"]:
            st.caption("No additional suggestions from these rules. Review your answer for relevance and accuracy.")
        for item in feedback["suggestions"]:
            st.text("• " + item)
    with st.expander("Career practice and limitations"):
        for item in feedback["career_practice"] + feedback["limitations"]:
            st.text("• " + item)
    if feedback.get("ai_coaching"):
        ai = feedback["ai_coaching"]
        with st.container(border=True):
            st.markdown("#### Recorded optional AI coaching")
            st.text(ai["notice"])
            for item in ai["suggestions"]:
                st.text(item["guidance"])
                evidence_text(item["answer_evidence"])
