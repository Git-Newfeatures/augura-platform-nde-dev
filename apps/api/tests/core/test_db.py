from uuid import uuid4

import pytest

from augura_api.core.config import Settings
from augura_api.core.db import get_engine, set_tenant_stmt, to_asyncpg_url
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
