"""Integration: enrichment write-path via upsert_semantic_release.

Writes a throwaway relation VIA the SECURITY DEFINER function (the app role has no
direct write) and verifies it is persisted + that the current release switches over.
Targets a throwaway database / the CI ephemeral Postgres (see conftest guard).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId, user: UserId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(user))
    await session.execute(set_tenant_stmt(tenant))


async def test_apply_release_writes_relation_and_bumps_current(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        repo = SemanticRepo(session)
        concepts = await repo.list_concepts()
        assert len(concepts) >= 2, "the semantic seed must be present"
        subj, obj = concepts[0].local_concept_id, concepts[1].local_concept_id
        pred = (await repo.list_causal_predicates())[0].predicate_id

        manifest = {"semantic_release_version": "test.0.1", "description": "test enrich B4"}
        payload = {
            "ontology_relations": [
                {
                    "relation_id": "TEST_REL_0001",
                    "subject_concept_id": subj,
                    "predicate": pred,
                    "object_concept_id": obj,
                    "polarity": "increases",
                    "default_strength": "moderate",
                    "default_temporal_lag": "unknown",
                    "mechanism_summary": "test",
                    "review_status": "approved",
                    "version": "test.0.1",
                    "active": True,
                }
            ],
            "ontology_relation_evidence": [
                {
                    "evidence_id": "TEST_EV_0001",
                    "relation_id": "TEST_REL_0001",
                    "source_type": "established_physiology",
                    "citation_or_url": "established physiology",
                    "evidence_summary": "test",
                    "population_notes": "test",
                    "evidence_strength": "established",
                    "review_status": "approved",
                }
            ],
        }
        result = await repo.apply_release(manifest, payload)
        assert result["version"] == "test.0.1"
        assert result["relations"] == 1

        active = (
            await session.execute(
                text("select active from ontology_relations where relation_id = 'TEST_REL_0001'")
            )
        ).scalar_one()
        assert active is True
        current = (
            await session.execute(
                text("select semantic_release_version from semantic_releases where is_current")
            )
        ).scalar_one()
        assert current == "test.0.1"
