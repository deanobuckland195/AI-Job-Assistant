"""Synthetic-only end-to-end demo. All database/export files are temporary.

Run from the project root: python -m examples.application_tracking_demo
No default database, existing reports or personal documents are accessed.
"""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from job_assistant import migrations


def cv_snapshot(connection):
    return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in ("profiles", "cvs", "cv_segments")}


def main():
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="aija-application-demo-") as folder:
        root = Path(folder)
        database = root / "synthetic.sqlite3"
        text = "Skills: Python\nSYNTHETIC_PRIVATE_CV_MARKER"
        with sqlite3.connect(database) as connection:
            migrations.create_v1(connection)
            connection.execute(f"PRAGMA application_id = {migrations.APPLICATION_ID}")
            connection.execute("PRAGMA user_version = 1")
            connection.execute("INSERT INTO profiles VALUES (?, ?, ?, ?)", (1, "Synthetic Candidate", '["python"]', "2020-01-01"))
            connection.execute("INSERT INTO cvs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (1, 1, "Synthetic CV", "synthetic.txt", "txt", len(text.encode()),
                                hashlib.sha256(text.encode()).hexdigest(), "synthetic fixture", "[]", "2020-01-01T00:00:00+00:00"))
            connection.execute("INSERT INTO cv_segments VALUES (?, ?, ?, ?, ?)", (1, 1, "page 1", text, text))
            original = cv_snapshot(connection)
        base = [sys.executable, "-B", str(project / "main.py"), "--database", str(database)]

        def run(arguments, answers=""):
            result = subprocess.run(base + arguments, input=answers, text=True, capture_output=True, cwd=root)
            if result.returncode:
                raise RuntimeError("Synthetic demo command failed: " + " ".join(arguments) + "\n" + result.stdout + result.stderr)
            return result.stdout

        run(["application-list"])
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == migrations.SCHEMA_VERSION
            assert cv_snapshot(connection) == original
        print(f"PASS: schema 1 -> {migrations.SCHEMA_VERSION} migration preserved all synthetic CV/profile records.")
        job = root / "synthetic-job.txt"
        job.write_text("Essential: Python", encoding="utf-8")
        run(["job-compare", "1", "--job-file", str(job), "--store"], "yes\n")
        run(["application-create", "--company", "Synthetic Ltd", "--role", "AI Engineering Apprentice",
             "--comparison", "1", "--deadline", "2099-12-31", "--notes", "SYNTHETIC_PRIVATE_NOTE"], "yes\n")
        run(["application-update", "1", "--status", "applied", "--application-date", "2020-01-02"], "yes\n")
        run(["application-update", "1", "--status", "interviewing", "--next-action", "Practise interview answers"], "yes\n")
        listing = run(["application-list", "--status", "interviewing", "--company", "Synthetic"])
        assert "Synthetic Ltd" in listing
        shown = run(["application-show", "1"])
        assert "saved -> applied" in shown and "applied -> interviewing" in shown
        print("PASS: stored comparison/CV links and saved -> applied -> interviewing history survived CLI restarts.")
        export = root / "applications.json"
        run(["application-export", "--output", str(export), "--include-history"], "yes\n")
        exported = export.read_text(encoding="utf-8")
        items = json.loads(exported)["applications"]
        assert len(items) == 1 and len(items[0]["history"]) == 3
        assert "SYNTHETIC_PRIVATE_CV_MARKER" not in exported and "SYNTHETIC_PRIVATE_NOTE" not in exported
        print("PASS: filtered listing and confirmed JSON export; no CV text or private notes exported by default.")
        run(["application-delete", "1"], "yes\n")
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM application_status_history").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM job_comparisons").fetchone()[0] == 1
            assert cv_snapshot(connection) == original
        print("PASS: deletion removed the application/history and retained CVs/comparison metadata.")
    print("Temporary demo files removed. No private data or network/API access was used.")


if __name__ == "__main__":
    main()
