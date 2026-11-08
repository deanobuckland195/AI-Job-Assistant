"""Transactional roadmap persistence, optimistic edits and local progress evidence."""

import hashlib
import json

from . import comparison_records, storage
from .applications import ApplicationError, positive_id, text_field, write_transaction
from .roadmap_rules import generate_plan

STATUSES = ("not started", "in progress", "completed")
EDIT_FIELDS = ("objective", "exercise", "project", "expected_evidence", "study_hours", "status", "completion_evidence")


def preview(connection, role_id, skills="", weekly_hours=4, *, comparison_id=None):
    comparison = snapshot = None
    if comparison_id is not None:
        comparison, snapshot = comparison_records.get_skill_snapshot(connection, comparison_id)
    plan = generate_plan(role_id, skills, weekly_hours, snapshot=snapshot)
    plan["comparison"] = ({k: comparison[k] for k in ("id", "cv_original_id", "cv_reviewed_at", "cv_digest", "job_digest", "rules_version")}
                          if comparison else None)
    plan["source_notice"] = ("Older comparison has counts only; individual gaps cannot be recovered. Using curated role recommendations and self-reported skills. Re-run job-compare --store for per-skill evidence."
                             if comparison and snapshot is None else
                             "Historical comparison snapshot, not current verification. Deleted or changed CV sources are not silently substituted."
                             if comparison else "No CV required. Skills are self-reported; remaining gaps mean missing evidence, not confirmed lack of ability.")
    return plan


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def create_roadmap(connection, role_id, skills="", weekly_hours=4, *, title=None, comparison_id=None, expected_plan_digest=None):
    title = text_field("Skills roadmap" if title is None else title, "Roadmap title", 120, required=True)
    with write_transaction(connection):
        plan = preview(connection, role_id, skills, weekly_hours, comparison_id=comparison_id)
        if expected_plan_digest is not None and expected_plan_digest != plan_digest(plan):
            raise ApplicationError("Roadmap inputs or comparison changed since preview. Preview again before saving.")
        milestones = plan.pop("milestones")
        when = storage.timestamp()
        cursor = connection.execute("""INSERT INTO roadmaps
            (title,role_id,weekly_hours,rules_version,plan_json,comparison_id,comparison_original_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (title, role_id, weekly_hours, plan["rules_version"],
                json.dumps(plan, sort_keys=True), comparison_id, comparison_id, when, when))
        roadmap_id = cursor.lastrowid
        connection.executemany("""INSERT INTO roadmap_milestones
            (roadmap_id,week,skill,objective,exercise,project,expected_evidence,study_hours,updated_at)
            VALUES (:roadmap_id,:week,:skill,:objective,:exercise,:project,:expected_evidence,:study_hours,:updated_at)""",
            [dict(m, roadmap_id=roadmap_id, updated_at=when) for m in milestones])
    return roadmap_id


def list_roadmaps(connection, limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 9223372036854775807:
        raise ApplicationError("Use a roadmap limit from 1 to 1,000 and a non-negative offset.")
    return [dict(row) for row in connection.execute("SELECT id,title,role_id,weekly_hours,revision FROM roadmaps ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))]


def get_roadmap(connection, roadmap_id):
    positive_id(roadmap_id, "Roadmap")
    row = connection.execute("SELECT * FROM roadmaps WHERE id = ?", (roadmap_id,)).fetchone()
    if row is None:
        raise ApplicationError("Roadmap not found. Refresh the roadmap list.")
    result = dict(row)
    result["plan"] = storage.decode_json(result.pop("plan_json"))
    result["milestones"] = [dict(m) for m in connection.execute("SELECT * FROM roadmap_milestones WHERE roadmap_id = ? ORDER BY week", (roadmap_id,))]
    return result


def progress(roadmap):
    milestones = roadmap["milestones"]
    total = len(milestones)
    completed = sum(m["status"] == "completed" for m in milestones)
    return {"completed": completed, "total": total, "in_progress": sum(m["status"] == "in progress" for m in milestones),
            "fraction": completed / total if total else 0.0}


def check_revision(roadmap, expected_revision):
    if type(expected_revision) is not int or expected_revision != roadmap["revision"]:
        raise ApplicationError("Roadmap changed since review. Reload it before saving or deleting; your draft was not saved.")


def update_milestone(connection, roadmap_id, milestone_id, changes, *, expected_revision):
    positive_id(milestone_id, "Milestone")
    if not isinstance(changes, dict) or set(changes) - set(EDIT_FIELDS):
        raise ApplicationError("Unknown milestone fields.")
    with write_transaction(connection):
        roadmap = get_roadmap(connection, roadmap_id)
        check_revision(roadmap, expected_revision)
        milestone = next((m for m in roadmap["milestones"] if m["id"] == milestone_id), None)
        if milestone is None:
            raise ApplicationError("Milestone not found in this roadmap.")
        values = {key: changes.get(key, milestone[key]) for key in EDIT_FIELDS}
        for key, maximum in (("objective", 1000), ("exercise", 2000), ("project", 2000), ("expected_evidence", 2000), ("completion_evidence", 4000)):
            values[key] = text_field(values[key], key.replace("_", " ").title(), maximum, required=key != "completion_evidence", multiline=True)
        if type(values["study_hours"]) is not int or not 1 <= values["study_hours"] <= roadmap["weekly_hours"]:
            raise ApplicationError("Milestone hours must fit the roadmap's weekly study budget.")
        if not isinstance(values["status"], str) or values["status"] not in STATUSES:
            raise ApplicationError("Choose not started, in progress or completed.")
        if values["status"] == "completed" and not values["completion_evidence"]:
            raise ApplicationError("Describe your completion evidence before marking the milestone completed. This remains self-reported.")
        if all(values[k] == milestone[k] for k in EDIT_FIELDS):
            return False
        when = storage.timestamp()
        completed_at = (milestone["completed_at"] or when) if values["status"] == "completed" else None
        connection.execute("""UPDATE roadmap_milestones SET objective=:objective,exercise=:exercise,project=:project,
            expected_evidence=:expected_evidence,study_hours=:study_hours,status=:status,
            completion_evidence=:completion_evidence,completed_at=:completed_at,updated_at=:updated_at WHERE id=:id""",
            dict(values, completed_at=completed_at, updated_at=when, id=milestone_id))
        connection.execute("UPDATE roadmaps SET revision=revision+1,updated_at=? WHERE id=?", (when, roadmap_id))
    return True


def rename_roadmap(connection, roadmap_id, title, *, expected_revision):
    title = text_field(title, "Roadmap title", 120, required=True)
    with write_transaction(connection):
        roadmap = get_roadmap(connection, roadmap_id)
        check_revision(roadmap, expected_revision)
        if roadmap["title"] == title:
            return False
        connection.execute("UPDATE roadmaps SET title=?,revision=revision+1,updated_at=? WHERE id=?", (title, storage.timestamp(), roadmap_id))
    return True


def delete_roadmap(connection, roadmap_id, *, expected_revision):
    with write_transaction(connection):
        roadmap = get_roadmap(connection, roadmap_id)
        check_revision(roadmap, expected_revision)
        connection.execute("DELETE FROM roadmaps WHERE id=?", (roadmap_id,))
