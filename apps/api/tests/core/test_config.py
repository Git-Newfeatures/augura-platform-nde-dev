import pytest
from pydantic import ValidationError

from augura_api.core.config import Settings, get_settings


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    s = Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
    assert s.env == "dev"
    assert s.app_name == "augura-api"
    assert s.version == "0.1.0"


def test_settings_fails_fast_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUGURA_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue] -- l'absence d'env doit lever


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
