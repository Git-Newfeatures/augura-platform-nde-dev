"""Database access for live search: frozen snapshots, sessions, events.

Like `CorpusRepo`, writes are tenant-scoped (org_id = tenant) and reads
filter org_id == tenant — defensive tenant isolation on top of RLS.
Per-study visibility (study_members) is NOT implemented here: delegated to
RLS (Tier 3), not to application code.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId, UserId
from augura_api.modules.corpus.models import (
    LiteratureEvent,
    LiteratureSnapshot,
    SearchSession,
)


class LiveRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Snapshots ────────────────────────────────────────────────────────────
    async def insert_snapshot(
        self,
        tenant_id: TenantId,
        *,
        study_id: UUID | None,
        created_by: UserId,
        payload: dict[str, Any],
        content_hash: str,
    ) -> LiteratureSnapshot:
        row = LiteratureSnapshot(
            org_id=tenant_id,
            study_id=study_id,
            created_by=created_by,
            payload=payload,
            content_hash=content_hash,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_snapshot(
        self, tenant_id: TenantId, snapshot_id: UUID
    ) -> LiteratureSnapshot | None:
        res = await self.session.execute(
            select(LiteratureSnapshot)
            .where(
                LiteratureSnapshot.id == snapshot_id,
                LiteratureSnapshot.org_id == tenant_id,
            )
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def list_snapshots(
        self, tenant_id: TenantId, *, study_id: UUID | None = None
    ) -> list[LiteratureSnapshot]:
        stmt = select(LiteratureSnapshot).where(LiteratureSnapshot.org_id == tenant_id)
        if study_id is not None:
            stmt = stmt.where(LiteratureSnapshot.study_id == study_id)
        res = await self.session.execute(stmt.order_by(LiteratureSnapshot.created_at.desc()))
        return list(res.scalars().all())

    # ── Sessions ─────────────────────────────────────────────────────────────
    async def create_session(
        self,
        tenant_id: TenantId,
        *,
        created_by: UserId,
        study_id: UUID | None,
        query: str | None,
    ) -> SearchSession:
        row = SearchSession(org_id=tenant_id, study_id=study_id, query=query, created_by=created_by)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_session(self, tenant_id: TenantId, session_id: UUID) -> SearchSession | None:
        res = await self.session.execute(
            select(SearchSession)
            .where(SearchSession.id == session_id, SearchSession.org_id == tenant_id)
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def list_sessions(
        self, tenant_id: TenantId, *, status: str | None = None
    ) -> list[SearchSession]:
        stmt = select(SearchSession).where(SearchSession.org_id == tenant_id)
        if status is not None:
            stmt = stmt.where(SearchSession.status == status)
        res = await self.session.execute(stmt.order_by(SearchSession.created_at.desc()))
        return list(res.scalars().all())

    async def delete_session(self, tenant_id: TenantId, session_id: UUID) -> None:
        """Deletes a session (tenant-scoped). Idempotent: no effect if absent."""
        await self.session.execute(
            delete(SearchSession).where(
                SearchSession.id == session_id, SearchSession.org_id == tenant_id
            )
        )
        await self.session.flush()

    async def delete_all_sessions(self, tenant_id: TenantId) -> None:
        """Clears the tenant's search history."""
        await self.session.execute(delete(SearchSession).where(SearchSession.org_id == tenant_id))
        await self.session.flush()

    # ── Events ───────────────────────────────────────────────────────────────
    async def append_event(
        self,
        tenant_id: TenantId,
        *,
        session_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        created_by: UserId,
    ) -> LiteratureEvent:
        row = LiteratureEvent(
            session_id=session_id,
            org_id=tenant_id,
            event_type=event_type,
            payload=payload,
            created_by=created_by,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row
