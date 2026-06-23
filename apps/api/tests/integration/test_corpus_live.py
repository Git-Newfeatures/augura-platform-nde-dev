"""Tier 2 (integration) — verified freeze/re-read of snapshots, sessions, events.

Runs against AUGURA_DATABASE_URL (skipped otherwise). Verifies: freeze→read roundtrip
with content_hash, tamper detection (gate 6 at the database level), pure re-read
without live calls (gate 8), and the sessions/events log.

NB: no `set role augura_app` here (per-study RLS enforcement is tested in
Tier 3) — these gates do not depend on RLS.
"""

import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus.freeze import ContentIntegrityError
from augura_api.modules.corpus.live_repo import LiveRepo
from augura_api.modules.corpus.schemas import (
    EventAppendRequest,
    FrozenResult,
    SessionCreateRequest,
    SnapshotWriteRequest,
)
from augura_api.modules.corpus.snapshot_service import LiteratureSnapshotService

pytestmark = pytest.mark.integration

TENANT = TenantId(UUID("aaaaaaaa-0000-4000-8000-000000000001"))
USER = UserId(UUID("bbbbbbbb-0000-4000-8000-000000000002"))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s, s.begin():
            await s.execute(set_user_stmt(USER))
            await s.execute(set_tenant_stmt(TENANT))
            yield s
    finally:
        await engine.dispose()


def _tenant() -> CurrentTenant:
    return CurrentTenant(tenant_id=TENANT, user_id=USER, role="member")


def _req(study_id: UUID | None = None) -> SnapshotWriteRequest:
    # query = the user question; query_string = the exact call (efetch by id):
    # the two DIFFER on purpose (gate 7 at freeze level).
    return SnapshotWriteRequest(
        query="35319473",
        sources=["pubmed"],
        model_version="claude-sonnet-4",
        prompt_version="v1",
        study_id=study_id,
        results=[
            FrozenResult(
                source="pubmed",
                id="35319473",
                title="Exact known-item paper",
                query_string="efetch:id=35319473",
                retrieval_date=date(2026, 6, 16),
                record={"pmid": "35319473", "doi": "10.2196/34946"},
                annotation="kept",
            )
        ],
    )


async def test_freeze_then_read_roundtrip(session: AsyncSession) -> None:
    svc = LiteratureSnapshotService(LiveRepo(session))
    snap = await svc.freeze(_tenant(), _req())
    assert len(snap.content_hash) == 64

    got = await svc.read_snapshot(_tenant(), snap.id)
    assert got.id == snap.id
    assert got.content_hash == snap.content_hash
    assert got.verified is True
    # gate 7: the frozen query_string is the exact call, not the user question.
    assert got.query == "35319473"
    assert got.results[0].query_string == "efetch:id=35319473"


async def test_read_verifies_hash_and_tamper_raises(session: AsyncSession) -> None:
    svc = LiteratureSnapshotService(LiveRepo(session))
    snap = await svc.freeze(_tenant(), _req())
    # Alter one byte of the stored payload without recomputing the hash → mismatch.
    await session.execute(
        text(
            "update literature_snapshots "
            "set payload = jsonb_set(payload, '{query}', '\"TAMPERED\"'::jsonb) "
            "where id = cast(:id as uuid)"
        ).bindparams(id=str(snap.id))
    )
    await session.flush()
    with pytest.raises(ContentIntegrityError):
        await svc.read_snapshot(_tenant(), snap.id)


async def test_read_is_pure_db_no_live_calls(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = LiteratureSnapshotService(LiveRepo(session))
    snap = await svc.freeze(_tenant(), _req())

    # Any live HTTP call would blow up: proves the re-read is a pure database
    # read (zero PubMed/CT.gov calls). The DB engine uses asyncpg, not httpx.
    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("live HTTP call during snapshot re-read")

    monkeypatch.setattr(httpx.AsyncClient, "get", _boom)
    got = await svc.read_snapshot(_tenant(), snap.id)
    assert got.verified is True


async def test_session_and_event_roundtrip(session: AsyncSession) -> None:
    svc = LiteratureSnapshotService(LiveRepo(session))
    sess = await svc.create_session(_tenant(), SessionCreateRequest(query="q", study_id=None))
    assert sess.status == "active"

    listed = await svc.list_sessions(_tenant())
    assert any(s.id == sess.id for s in listed)

    fetched = await svc.get_session(_tenant(), sess.id)
    assert fetched.id == sess.id

    ev = await svc.append_event(
        _tenant(), sess.id, EventAppendRequest(event_type="keep", payload={"pmid": "35319473"})
    )
    assert ev.session_id == sess.id
    assert ev.event_type == "keep"
