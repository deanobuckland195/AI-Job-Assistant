import sqlite3

import pytest

from job_assistant import migrations, storage


def legacy_v3(path):
    with sqlite3.connect(path) as connection:
        migrations.create_v1(connection)
        migrations.migrate_v1_to_v2(connection)
        migrations.migrate_v2_to_v3(connection)
        connection.execute(f"PRAGMA application_id = {storage.APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 3")
        connection.execute("INSERT INTO profiles VALUES (1,'Synthetic','[]','2020-01-01')")
        connection.execute("INSERT INTO cvs VALUES (1,1,'Synthetic','synthetic.txt','txt',20,'synthetic','fixture','[]','2020-01-01')")
        connection.execute("INSERT INTO cv_segments VALUES (1,1,'page 1','SYNTHETIC_ORIGINAL','SYNTHETIC_REVIEWED')")
        connection.execute("""INSERT INTO applications(id,company,role,status,next_action,created_at,updated_at,follow_up_date,action_completed)
                              VALUES (7,'Synthetic Company','Role','interviewing','Practise','2020-01-01','2020-01-01','2099-01-01',0)""")
        connection.execute("INSERT INTO application_status_history(application_id,from_status,to_status,changed_at) VALUES (7,NULL,'interviewing','2020-01-01')")


def snapshot(connection):
    return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("profiles", "cvs", "cv_segments", "applications", "application_status_history", "job_comparisons")}


def test_v3_to_v4_preserves_all_original_tables_rows_and_followups(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    legacy_v3(path)
    with sqlite3.connect(path) as connection:
        original = snapshot(connection)
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION
        assert snapshot(connection) == original
        assert connection.execute("SELECT COUNT(*) FROM interview_sessions").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with storage.database(path) as connection:
        assert snapshot(connection) == original


@pytest.mark.parametrize("failure", [sqlite3.OperationalError, KeyboardInterrupt])
def test_interview_migration_failure_and_interruption_are_atomic(tmp_path, monkeypatch, failure):
    path = tmp_path / "legacy.sqlite3"
    legacy_v3(path)
    original_migration = migrations.migrate_v3_to_v4
    def fail(connection):
        original_migration(connection)
        raise failure("Synthetic failure")
    monkeypatch.setattr(migrations, "migrate_v3_to_v4", fail)
    with pytest.raises(failure):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'interview_sessions'").fetchone() is None
        assert connection.execute("SELECT reviewed_text FROM cv_segments").fetchone()[0] == "SYNTHETIC_REVIEWED"


def test_conflicting_table_is_never_replaced(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    legacy_v3(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE interview_answers(sentinel TEXT)")
        connection.execute("INSERT INTO interview_answers VALUES ('synthetic unrelated data')")
    with pytest.raises(sqlite3.Error):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT sentinel FROM interview_answers").fetchone()[0] == "synthetic unrelated data"
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'interview_sessions'").fetchone() is None
