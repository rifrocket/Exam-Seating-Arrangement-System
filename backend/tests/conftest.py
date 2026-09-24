from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import session as db_session_module
from app.db.init_db import init_db
from app.db.session import create_session_factory, get_db_session
from app.main import create_app


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Generator[Engine, None, None]:
    """A fresh in-memory SQLite database per test, never a shared file.

    Patches the process-wide get_engine()/get_settings() singletons (rather
    than building a disconnected engine object) so that the app's own
    startup hook — which calls init_db() with no arguments — initializes
    this same in-memory database instead of a real one on disk.
    """
    test_settings = Settings(database_url="sqlite://")
    monkeypatch.setattr(db_session_module, "get_settings", lambda: test_settings)
    db_session_module.get_engine.cache_clear()
    db_session_module.get_session_factory.cache_clear()

    db_engine = db_session_module.get_engine()
    init_db(db_engine)
    yield db_engine

    db_session_module.get_engine.cache_clear()
    db_session_module.get_session_factory.cache_clear()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    app = create_app()
    session_factory = create_session_factory(engine)

    def override_get_db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as test_client:
        yield test_client
