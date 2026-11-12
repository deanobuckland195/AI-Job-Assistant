"""Local Streamlit interface using the same application services as the CLI."""

from datetime import date
import sqlite3

import streamlit as st

from . import applications as apps, comparison_records, storage
from . import dashboard_logic as logic
from .dashboard_theme import DARK_STYLE, style_application_table
from .cv_analysis import AnalysisError
from .migrations import STATUSES
from .interview_feedback import InterviewError

EXPECTED = (apps.ApplicationError, storage.StorageError, AnalysisError, InterviewError)
DATE_HELP = "Optional. Leave blank if unknown. Dates are never inferred from status."


def flash(message):
    st.session_state["notice"] = message
    st.rerun()


def date_widget(label, value, key, help=DATE_HELP):
    valid = apps.iso_date(value, label)
    initial = date.fromisoformat(valid) if valid else None
    selected = st.date_input(label, value=initial, min_value=min(date(1900, 1, 1), initial or date.today()),
                             max_value=max(date(2200, 12, 31), initial or date.today()), format="YYYY-MM-DD", key=key, help=help)
    return selected.isoformat() if selected else None


def link_fields(path, prefix):
    with storage.database(path) as connection:
        cvs, comparisons = logic.link_options(connection)
    cv_labels = {row["id"]: f"CV #{row['id']} · approved {row['reviewed_at'][:10]}" for row in cvs}
    comp_labels = {row["id"]: f"Comparison #{row['id']} · CV version #{row['cv_original_id']}" for row in comparisons}
    cv_id = st.selectbox("Approved CV version", [None, *cv_labels], format_func=lambda value: cv_labels.get(value, "No CV selected"), key=prefix + "cv")
    comparison_id = st.selectbox("Stored comparison", [None, *comp_labels], format_func=lambda value: comp_labels.get(value, "No comparison selected"), key=prefix + "comparison")
    st.caption("A stored comparison supplies its approved CV version. No CV text is displayed.")
    return {"cv_id": cv_id, "comparison_id": comparison_id}


def application_form(path, record=None):
    creating = record is None
    record = record or {"status": "saved"}
    token = st.session_state.get("create_version", 0) if creating else f"{record['id']}_{record['revision']}"
    prefix = f"{'create' if creating else 'edit'}_{token}_"
    with st.form(prefix + "form", clear_on_submit=False):
        st.subheader("New application" if creating else "Edit application")
        st.caption("Save deliberately. Changes stay in this form until you submit.")
        st.caption("01 / ROLE DETAILS")
        left, right = st.columns(2)
        with left:
            company = st.text_input("Company *", record.get("company", ""), max_chars=200, key=prefix + "company")
            status = st.selectbox("Status", STATUSES, index=STATUSES.index(record["status"]), format_func=str.title, key=prefix + "status")
            application_date = date_widget("Application date", record.get("application_date"), prefix + "application_date")
        with right:
            role = st.text_input("Role *", record.get("role", ""), max_chars=200, key=prefix + "role")
            url = st.text_input("Job URL", record.get("job_url") or "", max_chars=2048, key=prefix + "job_url", help="Optional HTTP(S) link. It will not be fetched.")
            deadline = date_widget("Application deadline", record.get("deadline"), prefix + "deadline")
        st.divider()
        st.markdown("#### Next step")
        st.caption("02 / PLAN YOUR FOLLOW-UP")
        next_action = st.text_area("Next action", record.get("next_action", ""), max_chars=1000, height=80, key=prefix + "next_action")
        follow_up = date_widget("Follow-up date", record.get("follow_up_date"), prefix + "follow_up", help="A date for this next action, independent of the application deadline.")
        completed = st.checkbox("This action is already completed", value=False, key=prefix + "completed") if creating else None
        if not creating:
            st.caption("Editing the next action reopens it. Use the completion button in the detail view after saving.")
        st.divider()
        st.caption("03 / NOTES & OPTIONAL LINKS")
        notes = st.text_area("Private notes", record.get("notes", ""), max_chars=10000, height=100, key=prefix + "notes", help="Local application notes. Avoid unnecessary sensitive information.")
        links = None
        if creating:
            with st.expander("Optional CV and comparison links"):
                links = link_fields(path, prefix)
        else:
            with st.expander("CV and comparison links"):
                link_mode = st.selectbox("CV/comparison links", ["Keep current links", "Replace links", "Clear links"], key=prefix + "link_mode")
                selected_links = link_fields(path, prefix)
                links = selected_links if link_mode == "Replace links" else {} if link_mode == "Clear links" else None
                st.caption("Keep ignores the selectors. Replace updates both links; Clear removes both and their provenance.")
        submitted = st.form_submit_button("Create application" if creating else "Save changes", type="primary")
    if submitted:
        values = dict(company=company, role=role, status=status, job_url=url, application_date=application_date,
                      deadline=deadline, next_action=next_action, follow_up_date=follow_up, notes=notes)
        try:
            with storage.database(path) as connection:
                if creating:
                    app_id = apps.create_application(connection, **values, **(links or {}), action_completed=completed)
                    st.session_state["create_version"] = token + 1
                    flash(f"Application #{app_id} created.")
                else:
                    changed = apps.update_application(connection, record["id"], values, links=links, expected_revision=record["revision"])
                    st.session_state.pop("detail_snapshot", None)
                    flash("Application updated." if changed else "No changes to save.")
        except EXPECTED as error:
            st.error(str(error))
        except (OSError, sqlite3.Error):
            st.error("Could not save locally. Check database permissions, space or another open write. No partial application was saved.")


def detail(path, selected):
    with storage.database(path) as connection:
        current = apps.get_application(connection, selected)
    snapshot = st.session_state.get("detail_snapshot")
    if snapshot is None or snapshot["id"] != selected:
        snapshot = current
        st.session_state["detail_snapshot"] = snapshot
        st.session_state.pop("pending_delete", None)
    st.divider()
    st.subheader("Application detail")
    st.text(f"{snapshot['company']} · {snapshot['role']}")
    st.caption(f"Application #{selected} · {snapshot['status'].title()} · updated {snapshot['updated_at']}")
    if current["revision"] != snapshot["revision"]:
        st.warning("This record changed elsewhere. Your draft is preserved; reload before saving or deleting.")
    if st.button("Reload record", key="reload_record", help="Discard the displayed draft and load the latest saved record."):
        st.session_state.pop("detail_snapshot", None)
        for key in list(st.session_state):
            if key.startswith(f"edit_{selected}_"):
                del st.session_state[key]
        st.session_state.pop("pending_delete", None)
        st.rerun()
    info_left, info_right = st.columns(2)
    with info_left:
        st.markdown("**Next action**")
        st.text(snapshot["next_action"] or "No next action recorded")
        st.caption(f"{logic.action_timing(snapshot)} · follow-up {snapshot.get('follow_up_date') or 'not set'}")
        if snapshot.get("action_completed_at"):
            st.caption("Completed: " + snapshot["action_completed_at"])
        label = "Reopen action" if snapshot.get("action_completed") else "Mark action complete"
        if st.button(label, key="complete_action", disabled=not bool(snapshot["next_action"])):
            try:
                with storage.database(path) as connection:
                    apps.update_application(connection, selected, {"action_completed": not bool(snapshot.get("action_completed"))}, expected_revision=snapshot["revision"])
                st.session_state.pop("detail_snapshot", None)
                flash("Next action updated.")
            except EXPECTED as error:
                st.error(str(error))
    with info_right:
        st.markdown("**Application deadline**")
        st.text(snapshot["deadline"] or "Not recorded")
        st.caption(logic.deadline_timing(snapshot))
        for note in apps.date_notes(snapshot):
            st.caption(note)
    with st.expander("Status history", expanded=True):
        st.dataframe([{"Changed (UTC)": e["changed_at"], "From": (e["from_status"] or "Created").title(), "To": e["to_status"].title()} for e in snapshot["history"]], hide_index=True, width="stretch")
    with st.expander("Linked CV and comparison · metadata only"):
        if snapshot.get("cv_original_id"):
            st.text(f"CV version #{snapshot['cv_original_id']} · live link: {snapshot.get('cv_id') or 'deleted/detached'}")
            st.text("Approved: " + str(snapshot.get("cv_reviewed_at")))
            st.code(snapshot.get("cv_digest") or "No digest", language=None)
        else:
            st.caption("No CV linked. Import and approve a CV through the CLI when you need one.")
        if snapshot.get("comparison_original_id"):
            st.text(f"Comparison #{snapshot['comparison_original_id']} · live link: {snapshot.get('comparison_id') or 'deleted/detached'}")
            if snapshot.get("comparison_id"):
                with storage.database(path) as connection:
                    metadata = comparison_records.get_comparison(connection, snapshot["comparison_id"])
                st.json({"Recorded": metadata["created_at"], "Rules": metadata["rules_version"], "Offline outcomes": metadata["counts"]})
        else:
            st.caption("No comparison linked. Use job-compare --store in the CLI to record comparison metadata.")
    application_form(path, snapshot)
    with st.expander("Delete application"):
        st.caption("Deletion removes this application and status history. CVs, comparisons and report files are retained.")
        if st.button("Review deletion", key="review_delete"):
            st.session_state["pending_delete"] = {"id": selected, "revision": snapshot["revision"]}
            st.session_state[f"confirm_delete_{selected}"] = False
        pending = st.session_state.get("pending_delete")
        if pending and pending["id"] == selected:
            st.warning(f"Delete application #{selected}? This cannot be undone in the app.")
            acknowledge = st.checkbox("I understand this removes the application and its history", key=f"confirm_delete_{selected}")
            cancel, delete = st.columns(2)
            if cancel.button("Cancel deletion", key="cancel_delete"):
                st.session_state.pop("pending_delete", None)
                st.rerun()
            if delete.button("Confirm deletion", key="confirm_delete", disabled=not acknowledge, type="primary"):
                try:
                    with storage.database(path) as connection:
                        apps.delete_application(connection, selected, expected_revision=pending["revision"])
                    st.session_state.pop("pending_delete", None)
                    st.session_state.pop("detail_snapshot", None)
                    flash("Application deleted. Linked records and reports were retained.")
                except EXPECTED as error:
                    st.error(str(error))


def application_list(path, rows):
    st.subheader("Your applications")
    if not rows:
        st.info("Your next opportunity starts here. Choose Add application to save a role and plan your next step.")
        return
    search_col, status_col, timing_col = st.columns([2, 1.4, 1.4])
    search = search_col.text_input("Search applications", placeholder="Company, role or next action", max_chars=200, key="search")
    statuses = status_col.multiselect("Status filter", STATUSES, format_func=str.title, key="status_filter")
    timing = timing_col.selectbox("Follow-up filter", ["All actions", "Overdue", "Due today", "Upcoming (7 days)", "Later", "Completed", "Unscheduled", "No action", "Closed"], key="timing_filter")
    filtered = logic.filter_records(rows, search, statuses, timing)
    if not filtered:
        st.info("No applications match these filters. Clear the search or adjust the filters to see more.")
        return
    page_size_col, page_col = st.columns([1, 1])
    with page_size_col:
        size = st.selectbox("Rows per page", [25, 50, 100], key="page_size")
    pages = (len(filtered) + size - 1) // size
    page_key = f"page_{search}_{','.join(statuses)}_{timing}_{size}"
    if page_key in st.session_state and not 1 <= st.session_state[page_key] <= pages:
        st.session_state[page_key] = 1
    with page_col:
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=page_key)
    visible = filtered[(page - 1) * size:page * size]
    st.caption(f"{len(filtered)} matching applications · page {page} of {pages}. Deadline and follow-up states use text, not colour alone.")
    cards_tab, table_tab = st.tabs(["Application cards", "Table view"])
    with cards_tab:
        with st.container(key="application_grid"):
            for start in range(0, len(visible), 3):
                for column, row in zip(st.columns(3), visible[start:start + 3]):
                    with column.container(border=True, key=f"application_card_{row['id']}"):
                        st.caption(f"APPLICATION #{row['id']}")
                        st.text(row["company"])
                        st.text(row["role"])
                        st.badge(row["status"].title(), color="violet")
                        st.divider()
                        st.caption("NEXT ACTION")
                        st.text(row["next_action"] or "No next action recorded")
                        st.caption(logic.action_timing(row))
                        st.divider()
                        st.caption(f"Applied · {row['application_date'] or 'Not recorded'}")
                        st.caption(f"Deadline · {row['deadline'] or 'Not set'}")
                        st.caption(f"Follow-up · {row.get('follow_up_date') or 'Not set'}")
                        if st.button("View & manage", key=f"manage_application_{row['id']}", width="stretch"):
                            st.session_state["open_application"] = row["id"]
                            st.rerun()
    with table_tab:
        st.dataframe(style_application_table(logic.table_records(visible)), hide_index=True, width="stretch", key="applications_table")
    options = [None, *[row["id"] for row in visible]]
    if st.session_state.get("open_application") not in options:
        st.session_state["open_application"] = None
    labels = {row["id"]: f"#{row['id']} · {row['company']} — {row['role']}" for row in visible}
    selected = st.selectbox("Open application", options, format_func=lambda value: labels.get(value, "Choose an application to view or edit"), key="open_application")
    if selected:
        detail(path, selected)


def run():
    st.set_page_config(page_title="AI Job Assistant", page_icon="💼", layout="wide", initial_sidebar_state="expanded")
    # Static CSS only: no user text or database values enter this HTML.
    st.markdown(DARK_STYLE, unsafe_allow_html=True)
    path = logic.database_path()
    scope = str(path.resolve())
    if st.session_state.get("database_scope") not in (None, scope):
        st.session_state.clear()
    st.session_state["database_scope"] = scope
    with st.sidebar:
        with st.container(key="brand"):
            st.title("AI Job Assistant")
            st.caption("CAREER WORKSPACE")
        st.caption("MAIN MENU")
        view = st.radio("Workspace", ["Applications", "Add application", "Interview Practice", "Skills Roadmap"], key="workspace")
        st.divider()
        st.caption("Local by default. Interview AI coaching sends only a question and answer after explicit consent. CV passages are never sent for coaching.")
        if st.button("Refresh list", key="refresh"):
            st.rerun()
    descriptions = {
        "Applications": "Keep your search moving, one clear next step at a time.",
        "Add application": "Save a role and plan the next action. Required fields are marked *.",
        "Interview Practice": "Practise, review evidence and save an attempt. Offline feedback is always available.",
        "Skills Roadmap": "Plan manageable weekly learning and record honest evidence of progress.",
    }
    with st.container(key="workspace_bar"):
        location, welcome = st.columns([1.5, 1])
        location.caption("AI JOB ASSISTANT  /  " + view.upper())
        welcome.text("Your next chapter starts here.")
    titles = {"Applications": "Your Career Dashboard", "Add application": "Add Your Next Opportunity",
              "Interview Practice": "Prepare for Your Next Interview", "Skills Roadmap": "Build Your Career Roadmap"}
    with st.container(key="page_intro"):
        st.title(titles[view])
        st.caption(descriptions[view])
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    try:
        if view == "Skills Roadmap":
            from .roadmap_dashboard import render
            render(path)
            return
        if view == "Interview Practice":
            from .interview_dashboard import render
            render(path)
            return
        with storage.database(path) as connection:
            counts = logic.overview(connection)
            rows, capped = logic.load_rows(connection)
        if capped:
            st.warning("The table searches the newest 10,000 applications. Overview totals include all records; use the CLI for older entries.")
        if view == "Add application":
            form_panel, summary_panel = st.columns([3, 1], gap="large")
            with form_panel:
                application_form(path)
            with summary_panel.container(border=True, key="application_summary"):
                st.markdown("#### Your search at a glance")
                for label, value in counts.items():
                    st.metric(label, value)
                st.caption("All saved records. Active includes interviews and offers.")
        else:
            with st.container(key="overview"):
                for column, (label, value) in zip(st.columns(5), counts.items()):
                    with column:
                        st.metric(label, value)
            st.caption("Overview covers all records. Active = applied, interviewing and offered; interviews/offers are subsets.")
            with st.container(key="application_listing", border=True):
                application_list(path, rows)
    except EXPECTED as error:
        st.error(str(error) + " Refresh the list or reload the record before trying again.")
    except (OSError, sqlite3.Error):
        st.error("The local database is unavailable or locked. Check its path, permissions and available space, then refresh. No incomplete write was committed.")
