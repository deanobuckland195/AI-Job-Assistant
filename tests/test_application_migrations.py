import sqlite3

import pytest

from job_assistant import migrations, storage


def create_legacy(path):
    with sqlite3.connect(path) as connection:
        migrations.create_v1(connection)
        connection.execute(f"PRAGMA application_id = {storage.APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO profiles VALUES (7, 'Synthetic Profile', '[\"python\"]', '2020-01-01')")
        connection.execute("""INSERT INTO cvs VALUES (11, 7, 'Synthetic CV', 'synthetic.txt', 'txt', 20,
                           'synthetic-digest', 'fixture', '[]', '2020-01-01')""")
        connection.execute("INSERT INTO cv_segments VALUES (11, 1, 'page 1', 'ORIGINAL_SYNTHETIC_TEXT', 'REVIEWED_SYNTHETIC_TEXT')")


def snapshot(connection):
    return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in ("profiles", "cvs", "cv_segments")}


def test_real_v1_migration_preserves_ids_text_and_metadata(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy(path)
    with sqlite3.connect(path) as connection:
        before = snapshot(connection)
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION
        assert snapshot(connection) == before
        assert storage.get_cv(connection, 11)["segments"][0]["reviewed_text"] == "REVIEWED_SYNTHETIC_TEXT"
        assert connection.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with storage.database(path) as connection:
        assert snapshot(connection) == before


@pytest.mark.parametrize("failure", [sqlite3.OperationalError, KeyboardInterrupt])
def test_failed_upgrade_rolls_back_all_ddl_and_version(tmp_path, monkeypatch, failure):
    path = tmp_path / "legacy.sqlite3"
    create_legacy(path)
    original = migrations.migrate_v1_to_v2
    def fail(connection):
        original(connection)
        raise failure("Synthetic migration interruption")
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", fail)
    with pytest.raises(failure):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'applications'").fetchone() is None
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'job_comparisons'").fetchone() is None
        assert connection.execute("SELECT reviewed_text FROM cv_segments").fetchone()[0] == "REVIEWED_SYNTHETIC_TEXT"
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", original)
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION


def test_upgrade_name_conflict_does_not_destroy_unrelated_table(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    create_legacy(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE applications(sentinel TEXT)")
        connection.execute("INSERT INTO applications VALUES ('synthetic extra data')")
    with pytest.raises(sqlite3.Error):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT sentinel FROM applications").fetchone()[0] == "synthetic extra data"


def test_migration_rejects_missing_v1_columns_without_mutation(tmp_path):
    path = tmp_path / "broken.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA application_id = {storage.APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE profiles(id INTEGER)")
    original = path.read_bytes()
    with pytest.raises(storage.StorageError, match="incomplete"):
        with storage.database(path):
            pass
    assert path.read_bytes() == original


def test_migration_foreign_key_violation_rolls_back(tmp_path):
    path = tmp_path / "broken.sqlite3"
    create_legacy(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE cvs SET profile_id = 999")
    with pytest.raises(storage.StorageError, match="inconsistent references"):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'applications'").fetchone() is None


def test_new_database_and_idempotent_reopen(tmp_path):
    path = tmp_path / "fresh.sqlite3"
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"applications", "application_status_history", "job_comparisons", "profiles", "cvs", "cv_segments"} <= tables
    first = path.read_bytes()
    with storage.database(path):
        pass
    assert path.read_bytes() == first


def test_failed_fresh_initialisation_rolls_back_application_id_and_all_tables(tmp_path, monkeypatch):
    path = tmp_path / "failed-new.sqlite3"
    def fail(connection):
        connection.execute("CREATE TABLE temporary_sentinel(value TEXT)")
        raise sqlite3.OperationalError("Synthetic failure")
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", fail)
    with pytest.raises(sqlite3.Error):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
