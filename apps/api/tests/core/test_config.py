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


def test_llm_keys_load_from_unprefixed_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le .env pose ANTHROPIC_API_KEY / OPENAI_API_KEY / NCBI_API_KEY sans préfixe :
    l'alias doit les charger malgré env_prefix=AUGURA_ (sinon les clés sont ignorées)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-unprefixed")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-unprefixed")
    monkeypatch.setenv("NCBI_API_KEY", "ncbi-unprefixed")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key == "sk-ant-unprefixed"
    assert s.openai_api_key == "sk-openai-unprefixed"
    assert s.ncbi_api_key == "ncbi-unprefixed"


def test_llm_keys_prefer_prefixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le nom préfixé AUGURA_* reste accepté et prioritaire."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("AUGURA_ANTHROPIC_API_KEY", "sk-ant-prefixed")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-unprefixed")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key == "sk-ant-prefixed"


def test_blank_llm_key_normalised_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une clé vide/whitespace (`ANTHROPIC_API_KEY=`) doit valoir None — sinon les
    constructeurs LLM bâtissent un client à clé vide au lieu de lever 503 (bug wiring)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key is None
    assert s.openai_api_key is None


def test_ctgov_proxy_url_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUGURA_CTGOV_PROXY_URL : absent ⇒ None (appel direct) ; posé ⇒ chargé ;
    vide ⇒ None (le validateur blank→None couvre aussi ce champ)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.delenv("AUGURA_CTGOV_PROXY_URL", raising=False)
    assert Settings().ctgov_proxy_url is None  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_PROXY_URL", "http://user:pass@proxy.example:8080")
    assert Settings().ctgov_proxy_url == "http://user:pass@proxy.example:8080"  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_PROXY_URL", "  ")
    assert Settings().ctgov_proxy_url is None  # pyright: ignore[reportCallIssue]
