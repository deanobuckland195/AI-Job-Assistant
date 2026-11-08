"""Explicit, transactional SQLite migrations. Never reset existing user data."""

APPLICATION_ID = 0x414A4131
SCHEMA_VERSION = 5
STATUSES = ("saved", "applied", "interviewing", "offered", "rejected", "withdrawn")


class SchemaError(ValueError):
    pass


def create_v1(connection):
    """Original schema, retained to test real v1 -> v2 upgrades."""
    connection.execute("""CREATE TABLE profiles (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        skills_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE cvs (
        id INTEGER PRIMARY KEY,
        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        title TEXT NOT NULL, filename TEXT NOT NULL,
        file_type TEXT NOT NULL CHECK(file_type IN ('pdf', 'docx', 'txt')),
        size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
        sha256 TEXT NOT NULL, extractor TEXT NOT NULL,
        warnings_json TEXT NOT NULL, reviewed_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE cv_segments (
        cv_id INTEGER NOT NULL REFERENCES cvs(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, reference TEXT NOT NULL,
        source_text TEXT NOT NULL, reviewed_text TEXT NOT NULL,
        PRIMARY KEY (cv_id, position))""")
    connection.execute("CREATE INDEX cvs_profile ON cvs(profile_id)")


def migrate_v1_to_v2(connection):
    connection.execute("""CREATE TABLE job_comparisons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cv_id INTEGER REFERENCES cvs(id) ON DELETE SET NULL,
        cv_original_id INTEGER NOT NULL, cv_reviewed_at TEXT NOT NULL,
        cv_digest TEXT NOT NULL, job_digest TEXT NOT NULL,
        rules_version TEXT NOT NULL, counts_json TEXT NOT NULL,
        ai_attempted INTEGER NOT NULL CHECK(ai_attempted IN (0, 1)),
        ai_model TEXT, ai_item_count INTEGER NOT NULL,
        created_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL CHECK(length(trim(company)) BETWEEN 1 AND 200),
        role TEXT NOT NULL CHECK(length(trim(role)) BETWEEN 1 AND 200),
        job_url TEXT, application_date TEXT,
        status TEXT NOT NULL CHECK(status IN ('saved','applied','interviewing','offered','rejected','withdrawn')),
        deadline TEXT, notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 10000),
        next_action TEXT NOT NULL DEFAULT '' CHECK(length(next_action) <= 1000),
        cv_id INTEGER REFERENCES cvs(id) ON DELETE SET NULL,
        cv_original_id INTEGER, cv_reviewed_at TEXT, cv_digest TEXT,
        comparison_id INTEGER REFERENCES job_comparisons(id) ON DELETE SET NULL,
        comparison_original_id INTEGER, comparison_job_digest TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0))""")
    connection.execute("""CREATE TABLE application_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
        from_status TEXT CHECK(from_status IS NULL OR from_status IN ('saved','applied','interviewing','offered','rejected','withdrawn')),
        to_status TEXT NOT NULL CHECK(to_status IN ('saved','applied','interviewing','offered','rejected','withdrawn')),
        changed_at TEXT NOT NULL,
        CHECK(from_status IS NULL OR from_status != to_status))""")
    connection.execute("CREATE INDEX applications_status ON applications(status)")
    connection.execute("CREATE INDEX applications_deadline ON applications(deadline)")
    connection.execute("CREATE INDEX application_history_order ON application_status_history(application_id, id)")
    connection.execute("CREATE UNIQUE INDEX application_initial_event ON application_status_history(application_id) WHERE from_status IS NULL")


def migrate_v2_to_v3(connection):
    connection.execute("ALTER TABLE applications ADD COLUMN follow_up_date TEXT")
    connection.execute("ALTER TABLE applications ADD COLUMN action_completed INTEGER NOT NULL DEFAULT 0 CHECK(action_completed IN (0, 1))")
    connection.execute("ALTER TABLE applications ADD COLUMN action_completed_at TEXT")


def migrate_v3_to_v4(connection):
    connection.execute("""CREATE TABLE interview_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, role_id TEXT NOT NULL,
        title TEXT NOT NULL, bank_version TEXT NOT NULL, created_at TEXT NOT NULL,
        cv_id INTEGER REFERENCES cvs(id) ON DELETE SET NULL,
        cv_original_id INTEGER, cv_reviewed_at TEXT, cv_digest TEXT)""")
    connection.execute("""CREATE TABLE interview_questions (
        session_id INTEGER NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
        number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 10), code TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('behavioural','technical','motivation','reflection')),
        prompt TEXT NOT NULL, guidance_json TEXT NOT NULL, topics_json TEXT NOT NULL,
        next_attempt INTEGER NOT NULL DEFAULT 1 CHECK(next_attempt > 0),
        PRIMARY KEY(session_id, number))""")
    connection.execute("""CREATE TABLE interview_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL, question_number INTEGER NOT NULL,
        attempt INTEGER NOT NULL CHECK(attempt > 0), answer TEXT NOT NULL CHECK(length(answer) BETWEEN 1 AND 8000),
        answer_digest TEXT NOT NULL, feedback_json TEXT NOT NULL,
        feedback_version TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(session_id, question_number) REFERENCES interview_questions(session_id, number) ON DELETE CASCADE,
        UNIQUE(session_id, question_number, attempt))""")
    connection.execute("CREATE INDEX interview_answers_session ON interview_answers(session_id, question_number, attempt)")


def migrate_v4_to_v5(connection):
    connection.execute("""CREATE TABLE comparison_skill_snapshots (
        comparison_id INTEGER PRIMARY KEY REFERENCES job_comparisons(id) ON DELETE CASCADE,
        snapshot_json TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE roadmaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
        role_id TEXT NOT NULL, weekly_hours INTEGER NOT NULL CHECK(weekly_hours BETWEEN 1 AND 20),
        rules_version TEXT NOT NULL, plan_json TEXT NOT NULL,
        comparison_id INTEGER REFERENCES job_comparisons(id) ON DELETE SET NULL,
        comparison_original_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0))""")
    connection.execute("""CREATE TABLE roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, roadmap_id INTEGER NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE,
        week INTEGER NOT NULL CHECK(week BETWEEN 1 AND 208), skill TEXT NOT NULL,
        objective TEXT NOT NULL CHECK(length(trim(objective)) BETWEEN 1 AND 1000),
        exercise TEXT NOT NULL CHECK(length(trim(exercise)) BETWEEN 1 AND 2000),
        project TEXT NOT NULL CHECK(length(trim(project)) BETWEEN 1 AND 2000),
        expected_evidence TEXT NOT NULL CHECK(length(trim(expected_evidence)) BETWEEN 1 AND 2000),
        study_hours INTEGER NOT NULL CHECK(study_hours BETWEEN 1 AND 20),
        status TEXT NOT NULL DEFAULT 'not started' CHECK(status IN ('not started','in progress','completed')),
        completion_evidence TEXT NOT NULL DEFAULT '' CHECK(length(completion_evidence) <= 4000),
        completed_at TEXT, updated_at TEXT NOT NULL,
        UNIQUE(roadmap_id, week), CHECK(status != 'completed' OR length(trim(completion_evidence)) > 0))""")
    connection.execute("CREATE INDEX roadmap_milestones_parent ON roadmap_milestones(roadmap_id, week)")


V1_COLUMNS = {
    "profiles": {"id", "name", "skills_json", "created_at"},
    "cvs": {"id", "profile_id", "title", "filename", "file_type", "size_bytes", "sha256", "extractor", "warnings_json", "reviewed_at"},
    "cv_segments": {"cv_id", "position", "reference", "source_text", "reviewed_text"},
}
V2_COLUMNS = {
    **V1_COLUMNS,
    "job_comparisons": {"id", "cv_id", "cv_original_id", "cv_reviewed_at", "cv_digest", "job_digest", "rules_version", "counts_json", "ai_attempted", "ai_model", "ai_item_count", "created_at"},
    "applications": {"id", "company", "role", "job_url", "application_date", "status", "deadline", "notes", "next_action", "cv_id", "cv_original_id", "cv_reviewed_at", "cv_digest", "comparison_id", "comparison_original_id", "comparison_job_digest", "created_at", "updated_at", "revision"},
    "application_status_history": {"id", "application_id", "from_status", "to_status", "changed_at"},
}
V3_COLUMNS = {**V2_COLUMNS, "applications": V2_COLUMNS["applications"] | {"follow_up_date", "action_completed", "action_completed_at"}}
V4_COLUMNS = {**V3_COLUMNS,
    "interview_sessions": {"id", "role_id", "title", "bank_version", "created_at", "cv_id", "cv_original_id", "cv_reviewed_at", "cv_digest"},
    "interview_questions": {"session_id", "number", "code", "kind", "prompt", "guidance_json", "topics_json", "next_attempt"},
    "interview_answers": {"id", "session_id", "question_number", "attempt", "answer", "answer_digest", "feedback_json", "feedback_version", "created_at"}}

V5_COLUMNS = {**V4_COLUMNS,
    "comparison_skill_snapshots": {"comparison_id", "snapshot_json"},
    "roadmaps": {"id", "title", "role_id", "weekly_hours", "rules_version", "plan_json", "comparison_id", "comparison_original_id", "created_at", "updated_at", "revision"},
    "roadmap_milestones": {"id", "roadmap_id", "week", "skill", "objective", "exercise", "project", "expected_evidence", "study_hours", "status", "completion_evidence", "completed_at", "updated_at"}}


def check_schema(connection, columns):
    for table, required in columns.items():
        # Identifiers are fixed application constants, never user input.
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not required <= actual:
            raise SchemaError("Database schema is incomplete; restore a known-good backup.")


def initialise(connection):
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        if version == 0 and app_id == 0:
            if connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone():
                raise SchemaError("Refusing to initialise an unrelated, non-empty database.")
            create_v1(connection)
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            version = 1
        elif app_id != APPLICATION_ID or version not in (1, 2, 3, 4, SCHEMA_VERSION):
            raise SchemaError("Unsupported database schema/version. No migration was performed.")
        check_schema(connection, {1: V1_COLUMNS, 2: V2_COLUMNS, 3: V3_COLUMNS, 4: V4_COLUMNS, 5: V5_COLUMNS}[version])
        if version == 1:
            migrate_v1_to_v2(connection)
            version = 2
        if version == 2:
            migrate_v2_to_v3(connection)
            version = 3
        if version == 3:
            migrate_v3_to_v4(connection)
            version = 4
        if version == 4:
            migrate_v4_to_v5(connection)
        if version != SCHEMA_VERSION:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        check_schema(connection, V5_COLUMNS)
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise SchemaError("Database has inconsistent references; restore a known-good backup.")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
