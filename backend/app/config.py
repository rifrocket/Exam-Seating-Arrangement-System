"""Application configuration, sourced from environment variables / .env file.

Nothing in this module hardcodes a filesystem path or external URL; every
value has an overridable default so the same code runs unmodified across
local dev, tests, and future deployment targets.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    app_name: str = "Exam Seating Arrangement System"
    environment: str = "development"

    # SQLAlchemy connection URL. Defaults to a SQLite file under ./data,
    # relative to the process working directory (not an absolute path).
    database_url: str = "sqlite:///./data/app.db"

    # Emit SQL statements to stdout; useful in local dev only.
    sql_echo: bool = False

    # Origins allowed to call the API. Browsers treat "localhost" and
    # "127.0.0.1" as different origins even on the same port, and CORS
    # failures are silent from the app's point of view (fetch() just
    # rejects with a generic network error) — so both dev hostnames are
    # allowed by default rather than assuming which one a developer's
    # browser will actually show in its address bar. Override via
    # APP_CORS_ORIGINS (a JSON array, e.g. '["https://admin.example.com"]')
    # for any origin beyond local development.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached (not a module-level global) so tests can call
    ``get_settings.cache_clear()`` to force re-reading the environment.
    """
    return Settings()
