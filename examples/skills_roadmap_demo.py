"""End-to-end offline roadmap demo; temporary synthetic data and no external calls."""

from pathlib import Path
import sqlite3
import tempfile

from job_assistant import applications, comparison_records, interview_store, migrations, roadmap_store as plans, storage
from job_assistant.documents import ExtractedDocument, Segment
from job_assistant.job_matching import compare_job
from job_assistant.job_requirements import job_from_text


def main():
    with tempfile.TemporaryDirectory(prefix="aija-roadmap-demo-") as directory:
        path = Path(directory) / "synthetic.sqlite3"
        report = Path(directory) / "existing-synthetic-report.txt"
        report.write_text("Retain this synthetic report", encoding="utf-8")
        with sqlite3.connect(path) as connection:
            migrations.create_v1(connection)
            migrations.migrate_v1_to_v2(connection)
            migrations.migrate_v2_to_v3(connection)
            migrations.migrate_v3_to_v4(connection)
            connection.execute(f"PRAGMA application_id={migrations.APPLICATION_ID}")
            connection.execute("PRAGMA user_version=4")
            connection.execute("INSERT INTO profiles VALUES (1,'Synthetic candidate','[]','2026-01-01')")
        with storage.database(path) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
            assert storage.get_profile(connection, 1)["name"] == "Synthetic candidate"
            print(f"PASS: schema 4 -> {migrations.SCHEMA_VERSION} upgrade retained the synthetic profile.")
            text = "Built a Python CSV validator.\nCurrently learning SQL."
            document = ExtractedDocument("synthetic.txt", "txt", len(text), "a" * 64, "fixture", [Segment("page 1", text, text)])
            cv_id = storage.save_cv(connection, 1, "Synthetic approved CV", document)
            comparison = compare_job(storage.get_cv(connection, cv_id), job_from_text("Essential:\nPython required\nSQL required\nGit required"))
            comparison_id = comparison_records.save_comparison(connection, comparison)
            app_id = applications.create_application(connection, company="Synthetic Ltd", role="AI Apprentice")
            session_id = interview_store.start_session(connection, "ai-engineering-apprentice")
            preview = plans.preview(connection, "ai-engineering-apprentice", "Git", 2, comparison_id=comparison_id)
            roadmap_id = plans.create_roadmap(connection, "ai-engineering-apprentice", "Git", 2,
                title="Synthetic apprenticeship plan", comparison_id=comparison_id, expected_plan_digest=plans.plan_digest(preview))
            roadmap = plans.get_roadmap(connection, roadmap_id)
            states = {g["skill"]: g["state"] for g in roadmap["plan"]["gaps"]}
            assert states["python"] == "supported_wording" and states["sql"] == "uncertain" and states["git"] == "self_reported"
            print("PASS: CV-supported Python, uncertain SQL and self-reported Git stay distinct.")
            first = roadmap["milestones"][0]
            plans.update_milestone(connection, roadmap_id, first["id"],
                {"objective": "Practise one local mock endpoint", "status": "in progress"}, expected_revision=1)
            plans.update_milestone(connection, roadmap_id, first["id"],
                {"status": "completed", "completion_evidence": "mock_endpoint.py: invalid-input and happy-path checks passed; local demonstration only"}, expected_revision=2)
        with storage.database(path) as connection:
            roadmap = plans.get_roadmap(connection, roadmap_id)
            assert plans.progress(roadmap)["completed"] == 1
            print(f"PASS: edited objectives and completed progress survived reopening ({len(roadmap['milestones'])} budgeted weekly milestones).")
            free_plan = plans.create_roadmap(connection, "general", "Communication", 1, title="No CV needed")
            assert plans.get_roadmap(connection, free_plan)["comparison_id"] is None
            plans.delete_roadmap(connection, roadmap_id, expected_revision=roadmap["revision"])
            assert applications.get_application(connection, app_id) and interview_store.get_session(connection, session_id)
            assert storage.get_cv(connection, cv_id) and comparison_records.get_comparison(connection, comparison_id)
            assert plans.get_roadmap(connection, free_plan)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            print("PASS: scoped deletion retained CV, comparison, application, interview and other roadmap.")
        assert report.read_text(encoding="utf-8") == "Retain this synthetic report"
        print("PASS: existing synthetic report retained. No API key, private data or network used.")
        print(preview["notice"])


if __name__ == "__main__":
    main()
