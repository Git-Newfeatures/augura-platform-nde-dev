"""Couche d'accès base : engine async, sessions, scoping tenant par transaction.

Le scoping tenant est appliqué via `set_config('app.tenant_id', …, true)` (local
à la transaction) ; les policies RLS (supabase/policies.sql) s'y adossent. L'API
se connecte avec un rôle Postgres NON exempt de RLS (spec §7).
"""

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
from augura_api.core.ids import TenantId

# Convention de nommage des contraintes/index → migrations Alembic déterministes.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base déclarative partagée. Les modèles vivent dans chaque module."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Caches process-wide, indexés par URL (un engine/sessionmaker par base).
_engines: dict[str, AsyncEngine] = {}
_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


def to_asyncpg_url(database_url: str) -> str:
    """Force le driver asyncpg (Supabase fournit une URL `postgresql://`)."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def get_engine(settings: Settings) -> AsyncEngine:
    if settings.database_url is None:
        raise RuntimeError("AUGURA_DATABASE_URL manquant — requis pour l'accès base.")
    url = to_asyncpg_url(settings.database_url)
    engine = _engines.get(url)
    if engine is None:
        engine = create_async_engine(url, pool_pre_ping=True)
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
    """Statement qui pose le tenant courant, local à la transaction."""
    return text("SELECT set_config('app.tenant_id', :tid, true)").bindparams(tid=str(tenant_id))


async def tenant_session(tenant_id: TenantId, settings: Settings) -> AsyncIterator[AsyncSession]:
    """Ouvre une transaction scopée au tenant (RLS active via app.tenant_id)."""
    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session, session.begin():
        await session.execute(set_tenant_stmt(tenant_id))
        yield session
