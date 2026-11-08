import sqlite3

import pytest

from job_assistant import migrations, roadmap_store as plans, storage


def legacy_v4(path):
    with sqlite3.connect(path) as connection:
        migrations.create_v1(connection)
        migrations.migrate_v1_to_v2(connection)
        migrations.migrate_v2_to_v3(connection)
        migrations.migrate_v3_to_v4(connection)
        connection.execute(f"PRAGMA application_id={migrations.APPLICATION_ID}")
        connection.execute("PRAGMA user_version=4")
        connection.execute("INSERT INTO profiles VALUES (1,'Synthetic','[]','2026-01-01')")
        connection.execute("INSERT INTO cvs VALUES (1,1,'Synthetic','synthetic.txt','txt',20,'synthetic','fixture','[]','2026-01-01')")
        connection.execute("INSERT INTO cv_segments VALUES (1,1,'page 1','Synthetic original','Synthetic reviewed')")
        connection.execute("""INSERT INTO job_comparisons
            (id,cv_id,cv_original_id,cv_reviewed_at,cv_digest,job_digest,rules_version,counts_json,ai_attempted,ai_item_count,created_at)
            VALUES (1,1,1,'2026-01-01','synthetic','synthetic','1.0','{"matched":1}',0,0,'2026-01-01')""")
        connection.execute("""INSERT INTO applications(company,role,status,created_at,updated_at,next_action,follow_up_date)
            VALUES ('Synthetic','Apprentice','interviewing','2026-01-01','2026-01-01','Practise','2026-01-10')""")
        connection.execute("INSERT INTO application_status_history(application_id,to_status,changed_at) VALUES (1,'interviewing','2026-01-01')")
        connection.execute("INSERT INTO interview_sessions(id,role_id,title,bank_version,created_at) VALUES (1,'general','Synthetic','1.0','2026-01-01')")
        connection.execute("""INSERT INTO interview_questions(session_id,number,code,kind,prompt,guidance_json,topics_json)
            VALUES (1,1,'synthetic','behavioural','Synthetic question','[]','[]')""")
        connection.execute("""INSERT INTO interview_answers(session_id,question_number,attempt,answer,answer_digest,feedback_json,feedback_version,created_at)
            VALUES (1,1,1,'Synthetic answer','synthetic','{"version":"1.0"}','1.0','2026-01-01')""")


def snapshot(connection):
    return {t: [tuple(row) for row in connection.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in migrations.V4_COLUMNS}


def test_v4_upgrade_preserves_every_legacy_record_and_reopen_is_byte_identical(tmp_path):
    path = tmp_path / "synthetic-v4.sqlite3"
    legacy_v4(path)
    with sqlite3.connect(path) as connection:
        original = snapshot(connection)
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert snapshot(connection) == original
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        plan = plans.preview(connection, "general", comparison_id=1)
        assert "counts only" in plan["source_notice"]
    before = path.read_bytes()
    with storage.database(path):
        pass
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", [sqlite3.OperationalError, KeyboardInterrupt])
def test_upgrade_failure_rolls_back_schema_and_data(tmp_path, monkeypatch, failure):
    path = tmp_path / "synthetic-v4.sqlite3"
    legacy_v4(path)
    with sqlite3.connect(path) as connection:
        before = snapshot(connection)
    migrate = migrations.migrate_v4_to_v5
    def fail(connection):
        migrate(connection)
        raise failure("Synthetic failure")
    monkeypatch.setattr(migrations, "migrate_v4_to_v5", fail)
    with pytest.raises(failure):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert snapshot(connection) == before
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name='roadmaps'").fetchone() is None


def test_conflicting_table_never_replaced(tmp_path):
    path = tmp_path / "synthetic-v4.sqlite3"
    legacy_v4(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE roadmap_milestones(sentinel TEXT)")
        connection.execute("INSERT INTO roadmap_milestones VALUES ('synthetic unrelated data')")
    with pytest.raises(sqlite3.Error):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert connection.execute("SELECT sentinel FROM roadmap_milestones").fetchone()[0] == 'synthetic unrelated data'
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name='roadmaps'").fetchone() is None
