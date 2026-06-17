"""Tests d'intégration du module datasets — CRUD, colonnes, lecture cohortes.

Sous le rôle augura_app (RLS active). Le seed fournit la cohorte validation_v1
(6 membres, 12 lignes de biomarqueurs).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.repo import DatasetRepo

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s, s.begin():
            await s.execute(text("set local role augura_app"))
            await s.execute(set_user_stmt(USER))
            await s.execute(set_tenant_stmt(LUCIS))
            yield s
    finally:
        await engine.dispose()


async def test_dataset_crud_and_columns(session: AsyncSession) -> None:
    repo = DatasetRepo(session)
    dataset = await repo.create_dataset(
        LUCIS, name="cohorte test", study_id=None, storage_path=None, row_count=824
    )
    fetched = await repo.get_dataset(LUCIS, dataset.id)
    assert fetched is not None
    assert fetched.name == "cohorte test"

    await repo.replace_columns(
        dataset.id,
        [
            schemas.ColumnIn(sheet="cohort", name="age", value_kind="numeric", min=18, max=90),
            schemas.ColumnIn(sheet="cohort", name="hba1c_12m", proposed_role="outcome"),
        ],
    )
    listed = [schemas.ColumnOut.model_validate(c) for c in await repo.list_columns(dataset.id)]
    by_name = {c.name: c for c in listed}
    assert len(by_name) == 2
    assert by_name["age"].min == 18  # colonne "min" → champ min via alias value_min
    assert by_name["hba1c_12m"].proposed_role == "outcome"


async def test_cohort_reads(session: AsyncSession) -> None:
    repo = DatasetRepo(session)
    cohorts = {name: n for name, n in await repo.list_cohorts(LUCIS)}
    assert cohorts["validation_v1"] == 6
    assert len(await repo.cohort_members(LUCIS, "validation_v1")) == 6
    assert len(await repo.cohort_biomarkers(LUCIS, "validation_v1")) == 12


async def test_import_cohort_round_trip(session: AsyncSession) -> None:
    repo = DatasetRepo(session)
    name = "import_test_v1"
    n_m, n_b = await repo.import_cohort(
        LUCIS,
        cohort_name=name,
        dataset_id=None,
        members=[
            schemas.CohortMemberIn(member_id="m1", age=54, sex="F", engagement_group="HIGH"),
            schemas.CohortMemberIn(member_id="m2", age=61, sex="M", engagement_group="REST"),
        ],
        biomarkers=[
            schemas.CohortBiomarkerIn(member_id="m1", timepoint_months=0, hba1c_pct=8.1),
            schemas.CohortBiomarkerIn(member_id="m1", timepoint_months=12, hba1c_pct=7.2),
        ],
    )
    assert (n_m, n_b) == (2, 2)
    assert len(await repo.cohort_members(LUCIS, name)) == 2
    assert len(await repo.cohort_biomarkers(LUCIS, name)) == 2

    # Idempotence : ré-import remplace (pas de doublon).
    await repo.import_cohort(
        LUCIS,
        cohort_name=name,
        dataset_id=None,
        members=[schemas.CohortMemberIn(member_id="m1", age=54)],
        biomarkers=[],
    )
    assert len(await repo.cohort_members(LUCIS, name)) == 1
    assert len(await repo.cohort_biomarkers(LUCIS, name)) == 0
