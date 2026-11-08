import sqlite3

import pytest

from job_assistant import storage
from job_assistant.documents import DocumentError, ExtractedDocument, Segment


@pytest.fixture
def document():
    return ExtractedDocument("synthetic.txt", "txt", 20, "a" * 64, "test extractor",
                             [Segment("line 1", "Original Python", "Corrected Python"),
                              Segment("line 2", "SQL", "SQL")])


def test_initialisation_is_versioned_idempotent_and_persistent(tmp_path):
    path = tmp_path / "new" / "test.sqlite3"
    with storage.database(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION
        assert connection.execute("PRAGMA application_id").fetchone()[0] == storage.APPLICATION_ID
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        profile_id = storage.create_profile(connection, "Demo", ["python"])
    with storage.database(path) as connection:
        assert storage.get_profile(connection, profile_id)["skills"] == ["python"]
        assert len(storage.list_profiles(connection)) == 1


@pytest.mark.parametrize("version, app_id", [(storage.SCHEMA_VERSION + 1, storage.APPLICATION_ID), (1, 0), (0, 123)])
def test_unknown_versions_not_modified(tmp_path, version, app_id):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version = {version}")
        connection.execute(f"PRAGMA application_id = {app_id}")
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('synthetic')")
    original = path.read_bytes()
    with pytest.raises(storage.StorageError, match="Unsupported"):
        with storage.database(path):
            pass
    assert path.read_bytes() == original


def test_unrelated_unversioned_database_not_adopted(tmp_path):
    path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(storage.StorageError, match="non-empty"):
        with storage.database(path):
            pass
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == [("unrelated",)]


def test_initialisation_failure_rolls_back_schema():
    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql.startswith("CREATE TABLE cvs"):
                raise sqlite3.OperationalError("Synthetic DDL failure")
            return super().execute(sql, *args)
    connection = sqlite3.connect(":memory:", factory=FailingConnection)
    try:
        with pytest.raises(sqlite3.OperationalError):
            storage.initialise(connection)
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        connection.close()


def test_schema_missing_tables_is_rejected(tmp_path):
    path = tmp_path / "incomplete.sqlite3"
    with storage.database(path) as connection:
        connection.execute("DROP TABLE cv_segments")
    with pytest.raises(storage.StorageError, match="incomplete"):
        with storage.database(path):
            pass


def test_save_retrieve_filter_and_delete_cascades(tmp_path, document):
    path = tmp_path / "test.sqlite3"
    with storage.database(path) as connection:
        first = storage.create_profile(connection, "Demo One", ["python"])
        second = storage.create_profile(connection, "Demo Two", [])
        cv_id = storage.save_cv(connection, first, "Reviewed demo", document)
    with storage.database(path) as connection:
        result = storage.get_cv(connection, cv_id)
        assert result["sha256"] == document.sha256
        assert result["extractor"] == "test extractor"
        assert result["segments"][0]["source_text"] == "Original Python"
        assert result["segments"][0]["reviewed_text"] == "Corrected Python"
        assert result["segments"][0]["reference"] == "line 1"
        assert [s["position"] for s in result["segments"]] == [1, 2]
        assert len(storage.list_cvs(connection, first)) == 1
        assert storage.list_cvs(connection, second) == []
        assert "source_text" not in storage.list_cvs(connection)[0]
        storage.delete_cv(connection, cv_id)
        assert storage.list_cvs(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM cv_segments").fetchone()[0] == 0
        assert len(storage.list_profiles(connection)) == 2
        with pytest.raises(storage.StorageError, match="not found"):
            storage.get_cv(connection, cv_id)


def test_sql_values_are_parameterised(tmp_path, document):
    attack = "Robert'); DROP TABLE profiles; --"
    with storage.database(tmp_path / "test.sqlite3") as connection:
        profile_id = storage.create_profile(connection, attack, ["sql"])
        cv_id = storage.save_cv(connection, profile_id, attack, document)
        assert storage.get_profile(connection, profile_id)["name"] == attack
        assert storage.get_cv(connection, cv_id)["title"] == attack
        assert storage.list_cvs(connection, "1 OR 1=1") == []
        with pytest.raises(storage.StorageError):
            storage.get_cv(connection, "1 OR 1=1")
        assert len(storage.list_profiles(connection)) == 1


def test_save_failure_rolls_back_metadata_and_segments(tmp_path, document):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        profile_id = storage.create_profile(connection, "Demo", [])
        connection.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON cv_segments
            WHEN NEW.position = 2 BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        with pytest.raises(sqlite3.IntegrityError):
            storage.save_cv(connection, profile_id, "Demo", document)
        assert storage.list_cvs(connection) == []
        assert connection.execute("SELECT COUNT(*) FROM cv_segments").fetchone()[0] == 0


@pytest.mark.parametrize("name, skills", [("", []), ("x" * 201, []), ("Demo", [""]), ("Demo", ["x"] * 101)])
def test_profile_validation(tmp_path, name, skills):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        with pytest.raises(storage.StorageError):
            storage.create_profile(connection, name, skills)
        assert storage.list_profiles(connection) == []


def test_invalid_cv_cannot_be_saved(tmp_path, document):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        profile = storage.create_profile(connection, "Demo", [])
        with pytest.raises(storage.StorageError):
            storage.save_cv(connection, 999, "Demo", document)
        with pytest.raises(storage.StorageError):
            storage.save_cv(connection, profile, "", document)
        document.segments[0].reviewed_text = " "
        document.segments[1].reviewed_text = ""
        with pytest.raises(DocumentError):
            storage.save_cv(connection, profile, "Demo", document)
        assert storage.list_cvs(connection) == []


def test_missing_delete_has_clear_error(tmp_path):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        with pytest.raises(storage.StorageError, match="No data was deleted"):
            storage.delete_cv(connection, 999)


def test_database_symlink_rejected(tmp_path):
    target = tmp_path / "target.sqlite3"
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(storage.StorageError, match="symbolic"):
        with storage.database(link):
            pass
    assert not target.exists()


def test_foreign_key_enforcement(tmp_path):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("""INSERT INTO cv_segments VALUES (999, 1, 'line 1', 'demo', 'demo')""")


def test_invalid_metadata_has_safe_error(tmp_path):
    with storage.database(tmp_path / "test.sqlite3") as connection:
        profile = storage.create_profile(connection, "Demo", [])
        connection.execute("UPDATE profiles SET skills_json = ? WHERE id = ?", ("SYNTHETIC_PRIVATE_MARKER", profile))
        with pytest.raises(storage.StorageError, match="Stored metadata") as caught:
            storage.get_profile(connection, profile)
        assert "SYNTHETIC_PRIVATE_MARKER" not in str(caught.value)
