"""Database access layer: async engine, sessions, per-transaction tenant scoping.

Tenant scoping is applied via `set_config('app.tenant_id', …, true)` (transaction-local);
the RLS policies (supabase/policies.sql) rely on it. The API connects with a Postgres
role that is NOT exempt from RLS (spec §7).
"""

import ssl
from collections.abc import AsyncIterator

from sqlalchemy import MetaData, TextClause, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from augura_api.core.config import Settings
from augura_api.core.ids import TenantId, UserId

# Naming convention for constraints/indexes → deterministic Alembic migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base. The models live in each module."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Process-wide caches, indexed by URL (one engine/sessionmaker per database).
_engines: dict[str, AsyncEngine] = {}
_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


def clear_engine_cache() -> None:
    """Evict all cached engines (test seam — lets tests swap create_async_engine)."""
    _engines.clear()
    _sessionmakers.clear()


def to_asyncpg_url(database_url: str) -> str:
    """Force the asyncpg driver (Supabase provides a `postgresql://` URL)."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def get_engine(settings: Settings) -> AsyncEngine:
    if settings.database_url is None:
        raise RuntimeError("AUGURA_DATABASE_URL missing — required for database access.")
    url = to_asyncpg_url(settings.database_url)
    engine = _engines.get(url)
    if engine is None:
        ctx = ssl.create_default_context()  # check_hostname=True, verify_mode=CERT_REQUIRED
        engine = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": ctx})
        _engines[url] = engine
    return engine


def get_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(settings)
    key = str(engine.url)
    sessionmaker = _sessionmakers.get(key)
    if sessionmaker is None:
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        _sessionmakers[key] = sessionmaker
    return sessionmaker


def set_tenant_stmt(tenant_id: TenantId) -> TextClause:
    """Statement that sets the current tenant, transaction-local."""
    return text("SELECT set_config('app.tenant_id', :tid, true)").bindparams(tid=str(tenant_id))


def set_user_stmt(user_id: UserId) -> TextClause:
    """Statement that sets the current user (bootstrap RLS on memberships)."""
    return text("SELECT set_config('app.user_id', :uid, true)").bindparams(uid=str(user_id))


async def tenant_session(tenant_id: TenantId, settings: Settings) -> AsyncIterator[AsyncSession]:
    """Opens a tenant-scoped transaction (RLS active via app.tenant_id)."""
    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session, session.begin():
        await session.execute(set_tenant_stmt(tenant_id))
        yield session


async def request_session(
    settings: Settings, tenant_id: TenantId, user_id: UserId
) -> AsyncIterator[AsyncSession]:
    """Request transaction: sets user_id AND tenant_id (full RLS)."""
    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session, session.begin():
        await session.execute(set_user_stmt(user_id))
        await session.execute(set_tenant_stmt(tenant_id))
        yield session
