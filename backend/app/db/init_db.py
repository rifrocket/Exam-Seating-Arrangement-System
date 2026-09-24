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
"""

from sqlalchemy import inspect
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


def init_db(engine: Engine | None = None) -> Engine:
    """Create any missing tables. Idempotent — safe to call on every app
    startup, since create_all() skips tables that already exist.

    Defaults to the process-wide cached engine (get_engine()) rather than
    building a brand new one, so this always targets the same database the
    rest of the app's request handling uses.
    """
    engine = engine or get_engine()
    check_schema_compatibility(engine)
    Base.metadata.create_all(bind=engine)
    return engine


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
