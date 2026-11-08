"""Offline practice demo using only temporary synthetic records and stdin answers."""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from job_assistant import migrations

CLAIM = "I reduced processing time by 25% during the project"
ANSWER = ("Situation: During college our parser rejected valid rows.\n"
          "Task: My task was to make the import reliable for classmates.\n"
          "Action: I tested the parser using synthetic records.\n"
          "Result: " + CLAIM + ".")
TABLES = ("profiles", "cvs", "cv_segments", "applications", "application_status_history", "job_comparisons")


def snapshot(connection):
    return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in TABLES}


def main():
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="aija-interview-demo-") as folder:
        root = Path(folder)
        database = root / "synthetic.sqlite3"
        text = CLAIM + "\nOTHER_SYNTHETIC_PRIVATE_CV_TEXT"
        with sqlite3.connect(database) as connection:
            migrations.create_v1(connection)
            migrations.migrate_v1_to_v2(connection)
            migrations.migrate_v2_to_v3(connection)
            connection.execute(f"PRAGMA application_id = {migrations.APPLICATION_ID}")
            connection.execute("PRAGMA user_version = 3")
            connection.execute("INSERT INTO profiles VALUES (?, ?, ?, ?)", (1, "Synthetic Candidate", "[]", "2020-01-01"))
            connection.execute("INSERT INTO cvs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (1, 1, "Synthetic CV", "synthetic.txt", "txt", len(text.encode()), hashlib.sha256(text.encode()).hexdigest(),
                                "synthetic fixture", "[]", "2020-01-01T00:00:00+00:00"))
            connection.execute("INSERT INTO cv_segments VALUES (?, ?, ?, ?, ?)", (1, 1, "page 1", text, text))
            connection.execute("INSERT INTO applications(company,role,status,created_at,updated_at,next_action) VALUES (?,?,?,?,?,?)",
                               ("Synthetic Ltd", "AI Apprentice", "interviewing", "2020-01-01", "2020-01-01", "Practise interview"))
            original = snapshot(connection)
        report = root / "existing-synthetic-report.txt"
        report.write_text("Existing synthetic report: retain me", encoding="utf-8")
        base = [sys.executable, "-B", str(project / "main.py"), "--database", str(database)]

        def run(arguments, answers=""):
            result = subprocess.run(base + arguments, input=answers, text=True, capture_output=True, cwd=root)
            if result.returncode:
                raise RuntimeError("Synthetic practice demo failed: " + " ".join(arguments) + "\n" + result.stdout + result.stderr)
            return result.stdout

        run(["interview-start", "--role", "ai-engineering-apprentice", "--count", "2", "--cv", "1"], "yes\n")
        run(["interview-answer", "1", "--question", "1"], "I helped with things during a college project.\n/done\nyes\n")
        run(["interview-answer", "1", "--question", "1"], ANSWER + "\n/done\nyes\n")
        shown = run(["interview-show", "1"])
        assert "attempt 1" in shown and "attempt 2" in shown
        feedback = run(["interview-feedback", "2"])
        assert "CV-SUPPORTED WORDING" in feedback and "CV unit 1: page 1" in feedback
        assert "OTHER_SYNTHETIC_PRIVATE_CV_TEXT" not in feedback
        with sqlite3.connect(database) as connection:
            stored = json.loads(connection.execute("SELECT feedback_json FROM interview_answers WHERE id = 2").fetchone()[0])
            assert all(part["state"] == "explicit_detail" for part in stored["star"].values())
            assert any(claim["state"] == "supported_wording" for claim in stored["claims"])
            assert snapshot(connection) == original
            assert connection.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
        print("PASS: schema 3 -> 4 migration preserved CVs, applications and original records.")
        print("PASS: AI apprenticeship questions and two answer attempts survived CLI restarts.")
        print("PASS: STAR/clarity coaching and exact CV references; no invented metrics or copied CV passages.")
        run(["interview-answer-delete", "1"], "yes\n")
        run(["interview-delete", "1"], "yes\n")
        with sqlite3.connect(database) as connection:
            for table in ("interview_sessions", "interview_questions", "interview_answers"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            assert snapshot(connection) == original
        assert report.read_text(encoding="utf-8") == "Existing synthetic report: retain me"
        print("PASS: confirmed practice deletion retained CVs, applications and existing reports.")
    print("Temporary files removed. No private documents, live AI calls or network access used.")


if __name__ == "__main__":
    main()
