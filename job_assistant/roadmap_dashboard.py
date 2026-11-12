"""Accessible offline roadmap preview, explicit saves and revision-safe progress forms."""

import streamlit as st

from . import comparison_records, roadmap_store as plans, storage
from .interview_questions import ROLES
from .roadmap_rules import NOTICE


def render(path):
    with st.container(key="roadmap_studio"):
        planner, guide = st.columns([2.2, 1], gap="large")
        with planner:
            with st.form("roadmap_generate"):
                st.subheader("Plan your learning")
                goal, budget = st.columns([1.25, 1])
                with goal:
                    st.caption("01 / YOUR CAREER GOAL")
                    role = st.selectbox("Target role", list(ROLES), format_func=ROLES.get, key="roadmap_role")
                    skills = st.text_input("Existing skills (comma separated)", max_chars=2000, key="roadmap_skills", help="Self-reported, not verified. No CV is required. Examples: Python, Git, SQL.")
                with budget:
                    st.caption("02 / YOUR LEARNING ROUTINE")
                    hours = st.number_input("Available study hours per week", min_value=1, max_value=20, value=4, step=1, key="roadmap_hours")
                    title = st.text_input("Roadmap title", max_chars=120, key="roadmap_title")
                with st.expander("Optional comparison context"):
                    with storage.database(path) as connection:
                        comparisons = comparison_records.list_comparisons(connection, limit=1000)
                    ids = [None, *[c["id"] for c in comparisons]]
                    comparison_id = st.selectbox("Optional stored CV/job comparison", ids,
                        format_func=lambda v: "No comparison · no CV needed" if v is None else f"Comparison #{v}", key="roadmap_comparison")
                    st.caption("Only comparison metadata is read. Original CVs, job text and reports are not opened. New comparisons include per-skill evidence status; older counts-only records cannot supply individual gaps.")
                generate = st.form_submit_button("Preview skills roadmap", type="primary", width="stretch")
                st.caption(NOTICE)
        with guide.container(border=True, key="roadmap_guide"):
            st.caption("THE ROADMAP STUDIO")
            st.markdown("### A clear path.\nOne week at a time.")
            st.caption("Turn your career goal into a practical learning routine.")
            st.divider()
            st.markdown("**01 · Choose your direction**")
            st.caption("Start with a target role and the skills you already bring.")
            st.markdown("**02 · Make room to learn**")
            st.caption("Set a weekly budget. Preview the objectives and exercises before saving.")
            st.markdown("**03 · Build your evidence**")
            st.caption("Edit each milestone, practise with a mini-project and record what you checked.")
            st.badge("Offline planning · no AI request", color="violet")
    if generate:
        st.session_state.pop("roadmap_preview", None)
        with storage.database(path) as connection:
            preview = plans.preview(connection, role, skills, hours, comparison_id=comparison_id)
        st.session_state["roadmap_preview"] = {"plan": preview, "role": role, "skills": skills, "hours": hours,
                                               "title": title.strip() or "Skills roadmap", "comparison_id": comparison_id}
    draft = st.session_state.get("roadmap_preview")
    if draft:
        with st.expander("Review generated roadmap", expanded=True):
            st.text(draft["title"])
            st.text(draft["plan"]["source_notice"])
            st.text(draft["plan"]["rules"])
            show_gaps(draft["plan"])
            preview_cards, preview_table = st.tabs(["Milestone preview", "Detailed plan"])
            with preview_cards:
                milestone_cards(draft["plan"]["milestones"], "preview")
            with preview_table:
                st.dataframe([{k: m[k] for k in ("week", "skill", "objective", "exercise", "project", "study_hours")} for m in draft["plan"]["milestones"]], hide_index=True, width="stretch")
            st.caption("Relative weeks, not calendar deadlines. Every milestone also recommends recording an artifact, checks, outcome and limitation. You can edit tasks after saving. Changing target role or weekly budget requires a new plan; existing progress is retained.")
            if st.button("Save new roadmap", key="roadmap_save"):
                with storage.database(path) as connection:
                    roadmap_id = plans.create_roadmap(connection, draft["role"], draft["skills"], draft["hours"],
                        title=draft["title"], comparison_id=draft["comparison_id"], expected_plan_digest=plans.plan_digest(draft["plan"]))
                st.session_state.pop("roadmap_preview", None)
                st.session_state.pop("roadmap_snapshot", None)
                st.session_state["roadmap_selected"] = roadmap_id
                st.session_state["notice"] = "Skills roadmap saved."
                st.rerun()
    with storage.database(path) as connection:
        rows = plans.list_roadmaps(connection, limit=1000)
    if not rows:
        st.info("No roadmaps yet. Choose a role and a realistic weekly study budget, preview the plan, then save it to track progress.")
        return
    labels = {r["id"]: f"#{r['id']} · {r['title']}" for r in rows}
    if st.session_state.get("roadmap_selected") not in labels:
        st.session_state["roadmap_selected"] = rows[0]["id"]
    st.caption("Showing the newest 1,000 roadmaps.")
    selected = st.selectbox("Open roadmap", list(labels), format_func=labels.get, key="roadmap_selected")
    with storage.database(path) as connection:
        current = plans.get_roadmap(connection, selected)
    snapshot = st.session_state.get("roadmap_snapshot")
    if snapshot is None or snapshot["id"] != selected:
        snapshot = current
        st.session_state["roadmap_snapshot"] = snapshot
    if snapshot["revision"] != current["revision"]:
        st.warning("This roadmap changed elsewhere. Your draft is preserved; reload before saving or deleting.")
    if st.button("Reload roadmap", key="roadmap_reload"):
        st.session_state.pop("roadmap_snapshot", None)
        for key in list(st.session_state):
            if key.startswith(f"roadmap_edit_{selected}_"):
                del st.session_state[key]
        st.rerun()
    st.divider()
    with st.container(key="roadmap_progress", border=True):
        st.subheader("Your learning progress")
        st.text(snapshot["title"])
        st.caption(f"{ROLES[snapshot['role_id']]} · up to {snapshot['weekly_hours']} hours per week · rules {snapshot['rules_version']}")
        st.text(snapshot["plan"]["source_notice"])
        if snapshot["comparison_original_id"] and not current["comparison_id"]:
            st.caption("Linked comparison was deleted. Historical roadmap metadata remains; no replacement source was used.")
        stats = plans.progress(snapshot)
        with st.container(key="roadmap_metrics"):
            for column, label, value in zip(st.columns(3),
                    ("Weekly study budget", "Completed milestones", "In progress"),
                    (f"{snapshot['weekly_hours']} hours", f"{stats['completed']} / {stats['total']}", stats["in_progress"])):
                column.metric(label, value)
        st.progress(stats["fraction"], text=f"{stats['completed']} of {stats['total']} milestones completed · {stats['in_progress']} in progress (self-reported)")
    st.subheader("Your weekly milestones")
    st.caption("Your saved learning path. Choose a weekly milestone below to edit tasks or record evidence.")
    milestone_cards(snapshot["milestones"], "saved")
    with st.expander("Skill evidence and planning rules"):
        show_gaps(snapshot["plan"])
        st.text(snapshot["plan"]["rules"])
        st.caption("Evidence status is a historical snapshot. Marking a milestone completed does not change it or update your CV.")
    prefix = f"roadmap_edit_{selected}_{snapshot['revision']}_"
    with st.expander("Roadmap title settings"):
        with st.form(prefix + "rename"):
            new_title = st.text_input("Edit roadmap title", value=snapshot["title"], max_chars=120, key=prefix + "title")
            rename = st.form_submit_button("Save roadmap title")
    if rename:
        with storage.database(path) as connection:
            plans.rename_roadmap(connection, selected, new_title, expected_revision=snapshot["revision"])
        st.session_state.pop("roadmap_snapshot", None)
        st.rerun()
    milestones = snapshot["milestones"]
    labels = {m["id"]: f"Week {m['week']} · {m['skill']} · {m['status'].title()}" for m in milestones}
    milestone_id = st.selectbox("Weekly milestone", list(labels), format_func=labels.get, key=prefix + "milestone")
    milestone = next(m for m in milestones if m["id"] == milestone_id)
    with st.container(border=True, key="milestone_detail"):
        st.markdown(f"#### Week {milestone['week']}")
        st.text(milestone["skill"].title() + " · " + milestone["status"].title())
        st.caption(f"{milestone['study_hours']} planned hours · weekly budget {snapshot['weekly_hours']} hours")
        st.text(milestone["objective"])
        if milestone["completed_at"]:
            st.caption("Marked completed (UTC): " + milestone["completed_at"])
        with st.expander("Recorded completion evidence", expanded=bool(milestone["completion_evidence"])):
            st.text(milestone["completion_evidence"] or "No completion evidence recorded yet. Add a local artifact description and the checks you performed when ready.")
            st.caption("Self-reported evidence. Paths and URLs are stored as text and never opened.")
    key = prefix + str(milestone_id) + "_"
    with st.form(key + "form"):
        st.markdown("#### Edit this week’s plan")
        learn, build = st.columns(2)
        with learn:
            objective = st.text_area("Learning objective", value=milestone["objective"], max_chars=1000, key=key + "objective")
            exercise = st.text_area("Suggested exercise", value=milestone["exercise"], max_chars=2000, key=key + "exercise")
        with build:
            project = st.text_area("Mini-project", value=milestone["project"], max_chars=2000, key=key + "project")
            expected = st.text_area("Suggested evidence of completion", value=milestone["expected_evidence"], max_chars=2000, key=key + "expected_evidence")
        study_hours = st.number_input("Planned hours this week", min_value=1, max_value=snapshot["weekly_hours"], value=milestone["study_hours"], step=1, key=key + "hours")
        st.markdown("#### Record progress")
        status = st.selectbox("Milestone status", plans.STATUSES, format_func=str.title, index=plans.STATUSES.index(milestone["status"]), key=key + "status")
        evidence = st.text_area("Your completion evidence", value=milestone["completion_evidence"], max_chars=4000, key=key + "evidence", help="Required for completion. A local path or description is enough; it is stored as text, never opened or fetched. Avoid secrets.")
        save = st.form_submit_button("Save milestone progress", type="primary")
    if save:
        with storage.database(path) as connection:
            plans.update_milestone(connection, selected, milestone_id, dict(objective=objective, exercise=exercise,
                project=project, expected_evidence=expected, study_hours=study_hours, status=status, completion_evidence=evidence), expected_revision=snapshot["revision"])
        st.session_state.pop("roadmap_snapshot", None)
        st.session_state["notice"] = "Milestone progress saved."
        st.rerun()
    with st.expander("Delete skills roadmap"):
        st.caption("Cannot be undone in the app. Deletes this roadmap and all its milestones. CVs, comparisons, interviews, applications and reports remain.")
        acknowledged = st.checkbox("I understand this removes the roadmap and its progress", key=prefix + "delete_ack")
        if st.button("Confirm roadmap deletion", disabled=not acknowledged, key=prefix + "delete"):
            with storage.database(path) as connection:
                plans.delete_roadmap(connection, selected, expected_revision=snapshot["revision"])
            st.session_state.pop("roadmap_snapshot", None)
            st.rerun()


def show_gaps(plan):
    labels = {"supported_wording": "Confirmed CV wording · not verified proficiency", "self_reported": "Self-reported skill · not corroborated", "missing_evidence": "Missing evidence · not confirmed absence", "uncertain": "Uncertain · clarify requirement/evidence"}
    st.dataframe([{"Skill": g["skill"], "Evidence state": labels[g["state"]], "Basis": g["basis"],
                   "Requirement numbers": ", ".join(str(s["number"]) for s in g["requirements"])} for g in plan["gaps"]], hide_index=True, width="stretch")
    if plan["unrecognised_requirements"]:
        st.warning("Unrecognised requirements need manual review; they were not turned into invented skills: " + ", ".join(map(str, plan["unrecognised_requirements"])))


def milestone_cards(milestones, namespace):
    """Presentation only: cards show the actual saved or previewed milestone values."""
    with st.container(key=f"{namespace}_milestone_grid"):
        for start in range(0, len(milestones), 3):
            for column, item in zip(st.columns(3), milestones[start:start + 3]):
                with column.container(border=True, key=f"{namespace}_milestone_card_{item['week']}"):
                    st.caption(f"◈  WEEK {item['week']:02d}")
                    with st.container(key=f"{namespace}_milestone_title_{item['week']}"):
                        st.text(item["skill"].title())
                    st.badge(item.get("status", "Preview · not saved").title(), color="violet")
                    st.caption(f"{item['study_hours']} planned study hours")
                    st.divider()
                    st.caption("LEARNING OBJECTIVE")
                    st.text(item["objective"])
                    with st.expander("Exercise & mini-project"):
                        st.caption("PRACTISE")
                        st.text(item["exercise"])
                        st.caption("BUILD")
                        st.text(item["project"])
                        st.caption("EVIDENCE TO RECORD")
                        st.text(item["expected_evidence"])
