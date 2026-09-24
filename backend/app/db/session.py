"""Engine and session factory.

The engine is built from `Settings.database_url` rather than a hardcoded
URL, so tests can point it at an isolated in-memory database without
monkeypatching module state. The process-wide engine/session-factory are
memoized (not module-level globals) so the app reuses one connection pool
instead of opening a new one per request.
"""

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings


def _is_sqlite_memory(database_url: str) -> bool:
    return database_url in ("sqlite://", "sqlite:///:memory:")


def _ensure_sqlite_file_parent_dir(database_url: str) -> None:
    """SQLite won't create a missing parent directory for its file, so make
    sure it exists — using the path from the configured URL, never a
    hardcoded one."""
    database_path = make_url(database_url).database
    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite and not _is_sqlite_memory(settings.database_url):
        _ensure_sqlite_file_parent_dir(settings.database_url)
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    # An in-memory SQLite database only persists for the lifetime of a single
    # connection, so tests (which use `sqlite://`) must pin the engine to one
    # shared connection via StaticPool, or each session would see an empty DB.
    if _is_sqlite_memory(settings.database_url):
        return create_engine(
            settings.database_url,
            echo=settings.sql_echo,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    return create_engine(settings.database_url, echo=settings.sql_echo, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@lru_cache
def get_engine() -> Engine:
    return create_db_engine()


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_engine())


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
