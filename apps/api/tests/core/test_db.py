import ssl
from uuid import uuid4

import pytest

from augura_api.core import db as db_mod
from augura_api.core.config import Settings
from augura_api.core.db import clear_engine_cache, get_engine, set_tenant_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId


def test_set_tenant_stmt_uses_set_config_local() -> None:
    stmt = set_tenant_stmt(TenantId(uuid4()))
    assert str(stmt) == "SELECT set_config('app.tenant_id', :tid, true)"


def test_asyncpg_url_normalisation() -> None:
    assert to_asyncpg_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert to_asyncpg_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert to_asyncpg_url("postgresql+asyncpg://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"


def test_get_engine_fails_fast_without_url() -> None:
    settings = Settings(env="dev")  # pyright: ignore[reportCallIssue] -- env fields
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_engine(settings)


def test_engine_uses_verified_ssl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_engine must pass a hostname-checking, CERT_REQUIRED SSL context to asyncpg."""
    captured: dict[str, object] = {}

    def fake_create(url: object, **kwargs: object) -> object:
        captured["url"] = url
        captured["connect_args"] = kwargs.get("connect_args")
        return object()

    monkeypatch.setattr(db_mod, "create_async_engine", fake_create)
    clear_engine_cache()
    settings = Settings(  # pyright: ignore[reportCallIssue]
        env="dev",
        database_url="postgresql://u:p@host:5432/db?sslmode=require",
    )
    try:
        db_mod.get_engine(settings)
        ctx = (captured["connect_args"] or {}).get("ssl")  # type: ignore[union-attr]
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED
    finally:
        clear_engine_cache()  # don't leave the fake engine cached for other tests
