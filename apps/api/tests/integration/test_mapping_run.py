"""Intégration : upload (A2) → map (A4) → propositions persistées sur dataset_columns.

Sauté si AUGURA_DATABASE_URL absent. CI : après seed (taxonomie A1), sous augura_app.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService
from augura_api.modules.mapping.repo import MappingRepo
from augura_api.modules.mapping.service import MappingService
from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(USER))
    await session.execute(set_tenant_stmt(tenant))


def _tenant(t: TenantId) -> CurrentTenant:
    return CurrentTenant(tenant_id=t, user_id=USER, role="owner")


async def test_upload_then_map_persists_proposals(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    monkeypatch.setenv("AUGURA_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("AUGURA_ENV", os.environ.get("AUGURA_ENV", "dev"))
    get_settings.cache_clear()
    settings = get_settings()

    csv = b"hba1c,sbp,age\n5.1,120,40\n6.2,130,55\n7.0,140,61\n"

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await session.execute(
            text(
                "insert into orgs (id, name, slug) values (cast(:i as uuid), 'IT', :s)"
            ).bindparams(i=str(tenant), s="it-" + uuid4().hex[:8])
        )
        up = await DatasetService(DatasetRepo(session)).upload_dataset(
            _tenant(tenant), settings, filename="c.csv", data=csv, name=None, study_id=None
        )
        result = await MappingService(
            MappingRepo(session), DatasetRepo(session), SemanticRepo(session)
        ).map_dataset(_tenant(tenant), up.dataset.id)

    # End-to-end path works: every column profiled + a confidence label returned.
    assert result.total_count == 3
    assert result.mapped_count >= 0
    assert len(result.columns) == 3
    assert all(c.confidence_label for c in result.columns)
    # Les colonnes appariées portent leur couche + domaine taxonomiques (colonnes du front).
    for c in result.columns:
        if c.proposed_canonical_id is not None:
            assert c.layer is not None and c.domain

    # Proposals (if any matched) are persisted on dataset_columns.
    async with sm() as session, session.begin():
        await _scope(session, tenant)
        cols = await DatasetRepo(session).list_columns(up.dataset.id)
    persisted = {c.name: c.proposed_canonical_id for c in cols}
    assert set(persisted) == {"hba1c", "sbp", "age"}
    # If the seeded taxonomy matched a column, its proposal + confidence were written.
    for c in cols:
        if c.proposed_canonical_id is not None:
            assert c.confidence is not None and 0.0 <= float(c.confidence) <= 1.0
