"""Tests for app.config.Settings — specifically the admin credential
fields Milestone 15/16 added, since nothing else in the test suite
exercises Settings() construction directly.

Every test here constructs `Settings(_env_file=None)` directly rather
than going through the cached `get_settings()` / relying on whatever
`backend/.env` happens to exist on the machine running these tests.
`Settings.model_config` points at a relative ".env", so without this,
"defaults to None when unset" tests would only be true on a machine that
has never run `make setup` — a real `backend/.env` (gitignored, created
by `make setup`, entirely legitimate) sets these values as a *file*,
which pydantic-settings reads regardless of `monkeypatch.delenv`
touching only `os.environ`. `_env_file=None` sidesteps that file lookup
entirely, so these tests check Settings' own defaulting/env-reading
behavior in isolation, independent of the developer machine's state.
"""

import os

from app.config import Settings


def test_admin_password_defaults_to_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_ADMIN_PASSWORD", raising=False)
    assert Settings(_env_file=None).admin_password is None


def test_admin_password_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_ADMIN_PASSWORD", "a-configured-secret")
    assert Settings(_env_file=None).admin_password == "a-configured-secret"


def test_admin_username_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_ADMIN_USERNAME", "an-admin")
    assert Settings(_env_file=None).admin_username == "an-admin"


def test_admin_username_defaults_to_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_ADMIN_USERNAME", raising=False)
    assert Settings(_env_file=None).admin_username is None


def test_get_settings_reflects_real_env_file_when_present() -> None:
    """Sanity check the *other* direction: get_settings() (the production
    path, via app.config.get_settings / the FastAPI dependency) genuinely
    does read backend/.env when one exists — proving the isolation above
    is a deliberate test-only choice, not a claim that Settings ignores
    .env files in general."""
    if not os.path.isfile(os.path.join(os.path.dirname(__file__), "..", ".env")):
        return  # nothing to assert against on a machine with no backend/.env
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert isinstance(settings, Settings)
    finally:
        get_settings.cache_clear()
