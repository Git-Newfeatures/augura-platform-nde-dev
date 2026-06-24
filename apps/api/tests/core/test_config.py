import pytest
from pydantic import ValidationError

from augura_api.core.config import Settings, get_settings


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    s = Settings()  # pyright: ignore[reportCallIssue] -- fields injected from the environment
    assert s.env == "dev"
    assert s.app_name == "augura-api"
    assert s.version == "0.1.0"


def test_settings_fails_fast_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUGURA_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue] -- a missing env must raise


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_llm_keys_load_from_unprefixed_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """The .env sets ANTHROPIC_API_KEY / OPENAI_API_KEY / NCBI_API_KEY without a prefix:
    the alias must load them despite env_prefix=AUGURA_ (otherwise the keys are ignored)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-unprefixed")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-unprefixed")
    monkeypatch.setenv("NCBI_API_KEY", "ncbi-unprefixed")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key == "sk-ant-unprefixed"
    assert s.openai_api_key == "sk-openai-unprefixed"
    assert s.ncbi_api_key == "ncbi-unprefixed"


def test_llm_keys_prefer_prefixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The prefixed AUGURA_* name stays accepted and takes priority."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("AUGURA_ANTHROPIC_API_KEY", "sk-ant-prefixed")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-unprefixed")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key == "sk-ant-prefixed"


def test_blank_llm_key_normalised_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty/whitespace key (`ANTHROPIC_API_KEY=`) must be None — otherwise the LLM
    constructors build a client with an empty key instead of raising 503 (wiring bug)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.anthropic_api_key is None
    assert s.openai_api_key is None


def test_ctgov_proxy_url_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUGURA_CTGOV_PROXY_URL: not set ⇒ None (direct call); set ⇒ loaded;
    empty ⇒ None (the blank→None validator covers this field too)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.delenv("AUGURA_CTGOV_PROXY_URL", raising=False)
    assert Settings().ctgov_proxy_url is None  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_PROXY_URL", "http://user:pass@proxy.example:8080")
    assert Settings().ctgov_proxy_url == "http://user:pass@proxy.example:8080"  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_PROXY_URL", "  ")
    assert Settings().ctgov_proxy_url is None  # pyright: ignore[reportCallIssue]


def test_ctgov_relay_url_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUGURA_CTGOV_RELAY_URL: not set ⇒ None (direct call); set ⇒ loaded;
    empty ⇒ None (covered by the blank→None validator)."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.delenv("AUGURA_CTGOV_RELAY_URL", raising=False)
    assert Settings().ctgov_relay_url is None  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_RELAY_URL", "https://front.vercel.app/api/ctgov")
    assert Settings().ctgov_relay_url == "https://front.vercel.app/api/ctgov"  # pyright: ignore[reportCallIssue]

    monkeypatch.setenv("AUGURA_CTGOV_RELAY_URL", "   ")
    assert Settings().ctgov_relay_url is None  # pyright: ignore[reportCallIssue]


def test_prod_requires_tls_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """In prod a DB URL without sslmode/ssl must fail fast at boot."""
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv(
        "AUGURA_DATABASE_URL", "postgresql://u:p@db.example.supabase.co:5432/postgres"
    )
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_prod_accepts_tls_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv(
        "AUGURA_DATABASE_URL",
        "postgresql://u:p@db.example.supabase.co:5432/postgres?sslmode=require",
    )
    monkeypatch.setenv("AUGURA_SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("AUGURA_SUPABASE_SERVICE_ROLE_KEY", "svc")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.database_url is not None
