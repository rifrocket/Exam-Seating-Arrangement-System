"""Database initialization mechanism for SQLite.

For this stage a single `create_all` is the appropriate mechanism: there is
no schema history to reconcile yet and no other environment to keep in
sync. If/when the schema needs versioned, reviewable migrations (multiple
environments, data already in place), introduce Alembic then — deferring
it now avoids an empty migrations directory with no real migration in it.
"""

from sqlalchemy.engine import Engine

from app.db import models  # noqa: F401  (ensures models are registered on Base.metadata)
from app.db.base import Base
from app.db.session import get_engine


def init_db(engine: Engine | None = None) -> Engine:
    """Create any missing tables. Idempotent — safe to call on every app
    startup, since create_all() skips tables that already exist.

    Defaults to the process-wide cached engine (get_engine()) rather than
    building a brand new one, so this always targets the same database the
    rest of the app's request handling uses.
    """
    engine = engine or get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
