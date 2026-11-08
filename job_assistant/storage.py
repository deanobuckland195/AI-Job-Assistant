"""Small versioned SQLite store. All user values use bound parameters."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from .documents import MAX_FILE_BYTES, validate_segments
from .migrations import APPLICATION_ID, SCHEMA_VERSION, SchemaError, initialise as migrate_schema

DEFAULT_DATABASE = Path(__file__).resolve().parent.parent / "local_data" / "assistant.sqlite3"


class StorageError(ValueError):
    """A storage validation error safe to display without private content."""


def initialise(connection):
    """Initialise or migrate atomically; errors never reset existing records."""
    try:
        migrate_schema(connection)
    except SchemaError as error:
        raise StorageError(str(error)) from None


@contextmanager
def database(path=DEFAULT_DATABASE):
    path = Path(path)
    if path.is_symlink():
        raise StorageError("Database paths must not be symbolic links.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        initialise(connection)
        yield connection
    finally:
        connection.close()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def decode_json(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        raise StorageError("Stored metadata is invalid; restore a known-good database backup.") from None


def create_profile(connection, name, skills):
    name = name.strip()
    if not name or len(name) > 200:
        raise StorageError("Profile name must contain 1 to 200 characters.")
    if len(skills) > 100 or any(not isinstance(s, str) or not s.strip() or len(s) > 100 for s in skills):
        raise StorageError("Use at most 100 skills, each containing 1 to 100 characters.")
    with connection:
        cursor = connection.execute(
            "INSERT INTO profiles(name, skills_json, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(skills), timestamp()),
        )
    return cursor.lastrowid


def list_profiles(connection):
    return [dict(row) for row in connection.execute("SELECT id, name, created_at FROM profiles ORDER BY id")]


def get_profile(connection, profile_id):
    row = connection.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        raise StorageError("Profile not found. Use profile-list to find an existing ID.")
    result = dict(row)
    result["skills"] = decode_json(result.pop("skills_json"))
    return result


def save_cv(connection, profile_id, title, document):
    get_profile(connection, profile_id)
    title = title.strip()
    if not title or len(title) > 200:
        raise StorageError("CV title must contain 1 to 200 characters.")
    validate_segments(document.segments)
    if not 0 < document.size_bytes <= MAX_FILE_BYTES:
        raise StorageError("Invalid document file size.")
    with connection:
        cursor = connection.execute("""INSERT INTO cvs
            (profile_id, title, filename, file_type, size_bytes, sha256, extractor, warnings_json, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile_id, title, document.filename, document.file_type, document.size_bytes,
             document.sha256, document.extractor, json.dumps(document.warnings), timestamp()))
        cv_id = cursor.lastrowid
        connection.executemany("""INSERT INTO cv_segments
            (cv_id, position, reference, source_text, reviewed_text) VALUES (?, ?, ?, ?, ?)""",
            [(cv_id, index, s.reference, s.source_text, s.reviewed_text)
             for index, s in enumerate(document.segments, 1)])
    return cv_id


def list_cvs(connection, profile_id=None):
    sql = "SELECT id, profile_id, title, filename, file_type, reviewed_at FROM cvs"
    if profile_id is None:
        rows = connection.execute(sql + " ORDER BY id")
    else:
        rows = connection.execute(sql + " WHERE profile_id = ? ORDER BY id", (profile_id,))
    return [dict(row) for row in rows]


def get_cv(connection, cv_id):
    row = connection.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()
    if row is None:
        raise StorageError("CV not found. Use cv-list to find an existing ID.")
    result = dict(row)
    result["warnings"] = decode_json(result.pop("warnings_json"))
    result["segments"] = [dict(segment) for segment in connection.execute(
        "SELECT position, reference, source_text, reviewed_text FROM cv_segments WHERE cv_id = ? ORDER BY position",
        (cv_id,))]
    return result


def delete_cv(connection, cv_id):
    with connection:
        cursor = connection.execute("DELETE FROM cvs WHERE id = ?", (cv_id,))
        if cursor.rowcount == 0:
            raise StorageError("CV not found. No data was deleted.")
