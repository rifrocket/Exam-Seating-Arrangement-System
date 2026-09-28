"""Tests for app.config.Settings — specifically the admin credential
fields Milestone 15/16 added, since nothing else in the test suite
exercises Settings() construction directly."""

from app.config import Settings, get_settings


def test_admin_password_defaults_to_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().admin_password is None
    finally:
        get_settings.cache_clear()


def test_admin_password_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_ADMIN_PASSWORD", "a-configured-secret")
    get_settings.cache_clear()
    try:
        assert get_settings().admin_password == "a-configured-secret"
    finally:
        get_settings.cache_clear()


def test_admin_username_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_ADMIN_USERNAME", "an-admin")
    get_settings.cache_clear()
    try:
        assert get_settings().admin_username == "an-admin"
    finally:
        get_settings.cache_clear()


def test_admin_username_defaults_to_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_ADMIN_USERNAME", raising=False)
    get_settings.cache_clear()
    try:
        assert Settings().admin_username is None
    finally:
        get_settings.cache_clear()
