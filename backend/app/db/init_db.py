"""Database initialization mechanism for SQLite.

For this stage a single `create_all` is the appropriate mechanism for
*new* tables: there is no schema history to reconcile yet and no other
environment to keep in sync. If/when the schema needs versioned,
reviewable migrations (multiple environments, data already in place),
introduce Alembic then — deferring it now avoids an empty migrations
directory with no real migration in it.

`create_all()` cannot alter a table that already exists, though — it
silently does nothing to it. Milestone 3 adds required columns and a new
unique constraint to the already-shipped `exams` table, which is exactly
the case `create_all()` can't handle safely: if an existing `data/app.db`
were left with the pre-Milestone-3 `exams` schema, every read/write would
break with a confusing "no such column" error instead of a clear one. So
before creating anything, check_schema_compatibility() inspects whatever
`exams` table already exists and refuses to proceed — loudly, with no
attempt to alter or drop it — if it's missing a column this milestone
requires. It never deletes or migrates data on its own.

Milestone 8 adds `rooms.rows`/`rooms.columns` and takes the opposite,
auto-migrating approach for that one specific case:
`_ensure_room_topology_columns()` runs a plain `ALTER TABLE ... ADD
COLUMN` for either column if it's missing from an existing `rooms` table.
This is safe in a way the `exams` case above is not: both new columns are
nullable and purely additive — every existing room row simply gets
`rows=NULL, columns=NULL` ("topology not configured yet"), no existing
data changes meaning, and no row becomes invalid. The `exams` columns
above couldn't be handled this way because their *absence* would have
left ambiguous, silently-wrong data (a schema requirement, not an
optional extension); these two are the opposite case, so a loud
`SchemaCompatibilityError` would only be friction, not a safety benefit.

Milestone 9 needs a third kind of change: `seating_generations.exam_id`
must become nullable (a session generation has a `session_id` instead).
Relaxing an existing NOT NULL constraint isn't a plain `ADD COLUMN` —
SQLite has no `ALTER COLUMN`, so `_relax_seating_generation_exam_id_nullability()`
does the standard SQLite dance instead: build a new table with the
current schema, copy every existing row across unchanged (each keeps its
real `exam_id`; `session_id` is simply new and starts NULL for all of
them), drop the old table, and rename. No existing generation or its
assignments (which reference it by `seating_generation_id`, never
altered) are touched or invalidated.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db import models  # noqa: F401  (ensures models are registered on Base.metadata)
from app.db.base import Base
from app.db.session import get_engine


class SchemaCompatibilityError(RuntimeError):
    """Raised instead of silently leaving a stale table schema in place."""


def check_schema_compatibility(engine: Engine) -> None:
    inspector = inspect(engine)
    if "exams" not in inspector.get_table_names():
        return  # Fresh database — create_all() will create it correctly.

    existing_columns = {col["name"] for col in inspector.get_columns("exams")}
    required_columns = {"expected_student_count", "day_label"}
    missing = required_columns - existing_columns
    if missing:
        raise SchemaCompatibilityError(
            "The existing 'exams' table is missing column(s) "
            f"{sorted(missing)} required as of Milestone 3, and create_all() "
            "cannot add columns to a table that already exists. Nothing has "
            "been altered or deleted. If this database holds no data worth "
            "keeping, delete the file (or its 'exams'/'exam_rooms' tables) "
            "and re-run initialization. Otherwise, a real migration "
            "(e.g. introducing Alembic) is needed before this app can run "
            "against this database."
        )


def _ensure_room_topology_columns(engine: Engine) -> None:
    """Adds `rows`/`columns` to an existing `rooms` table if either is
    missing. See this module's docstring for why this case (unlike
    `check_schema_compatibility` above) auto-migrates instead of failing:
    both columns are nullable and purely additive, so no existing row's
    meaning changes and nothing can become invalid."""
    inspector = inspect(engine)
    if "rooms" not in inspector.get_table_names():
        return  # Fresh database — create_all() will create the current schema directly.

    existing_columns = {col["name"] for col in inspector.get_columns("rooms")}
    missing = {"rows", "columns"} - existing_columns
    if not missing:
        return

    with engine.begin() as connection:
        if "rows" in missing:
            connection.execute(text("ALTER TABLE rooms ADD COLUMN rows INTEGER"))
        if "columns" in missing:
            connection.execute(text('ALTER TABLE rooms ADD COLUMN "columns" INTEGER'))


def _relax_seating_generation_exam_id_nullability(engine: Engine) -> None:
    """Rebuilds `seating_generations` with `exam_id` nullable and a new
    `session_id` column, if the existing table still has the old,
    pre-Milestone-9 NOT NULL `exam_id`. A no-op for a fresh database
    (`Base.metadata.create_all()`, which must run before this, already
    creates the current schema directly) and a no-op once already
    migrated. Must run after `create_all()` so `examination_sessions`
    (session_id's foreign key target) already exists."""
    inspector = inspect(engine)
    if "seating_generations" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("seating_generations")}
    exam_id_column = columns.get("exam_id")
    if exam_id_column is None or exam_id_column["nullable"]:
        return  # already nullable (either migrated already, or a fresh create_all())

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE seating_generations RENAME TO seating_generations_pre_m9"))
        connection.execute(
            text(
                """
                CREATE TABLE seating_generations (
                    id INTEGER NOT NULL PRIMARY KEY,
                    exam_id INTEGER REFERENCES exams (id),
                    session_id INTEGER REFERENCES examination_sessions (id),
                    strategy_name VARCHAR(64) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    total_registered INTEGER NOT NULL,
                    total_assigned INTEGER NOT NULL,
                    total_unassigned INTEGER NOT NULL,
                    capacity_shortage BOOLEAN NOT NULL,
                    warnings JSON NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CHECK ((exam_id IS NOT NULL AND session_id IS NULL)
                        OR (exam_id IS NULL AND session_id IS NOT NULL))
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO seating_generations
                    (id, exam_id, session_id, strategy_name, status, total_registered,
                     total_assigned, total_unassigned, capacity_shortage, warnings, created_at)
                SELECT id, exam_id, NULL, strategy_name, status, total_registered,
                       total_assigned, total_unassigned, capacity_shortage, warnings, created_at
                FROM seating_generations_pre_m9
                """
            )
        )
        connection.execute(text("DROP TABLE seating_generations_pre_m9"))
        connection.execute(text("CREATE INDEX ix_seating_generations_exam_id ON seating_generations (exam_id)"))
        connection.execute(
            text("CREATE INDEX ix_seating_generations_session_id ON seating_generations (session_id)")
        )


def init_db(engine: Engine | None = None) -> Engine:
    """Create any missing tables. Idempotent — safe to call on every app
    startup, since create_all() skips tables that already exist.

    Defaults to the process-wide cached engine (get_engine()) rather than
    building a brand new one, so this always targets the same database the
    rest of the app's request handling uses.
    """
    engine = engine or get_engine()
    check_schema_compatibility(engine)
    _ensure_room_topology_columns(engine)
    Base.metadata.create_all(bind=engine)
    _relax_seating_generation_exam_id_nullability(engine)
    return engine


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
