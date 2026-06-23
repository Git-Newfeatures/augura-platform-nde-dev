"""Database access for the jobs module — idempotency on (org_id, idempotency_key)."""

from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.jobs.models import Job


class JobRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: TenantId, job_id: UUID) -> Job | None:
        res = await self.session.execute(
            select(Job).where(Job.org_id == tenant_id, Job.id == job_id)
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        tenant_id: TenantId,
        *,
        type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> Job:
        # Idempotency: a key already seen returns the existing job (a double-click
        # does not launch two bootstraps — spec §8).
        if idempotency_key is not None:
            res = await self.session.execute(
                select(Job).where(Job.org_id == tenant_id, Job.idempotency_key == idempotency_key)
            )
            existing = res.scalar_one_or_none()
            if existing is not None:
                return existing
        job = Job(org_id=tenant_id, type=type, payload=payload, idempotency_key=idempotency_key)
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update(
        self,
        tenant_id: TenantId,
        job_id: UUID,
        *,
        status: str | None = None,
        progress: float | None = None,
        result_ref: str | None = None,
        result_json: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update a job's tracking fields (written by the runner). Tenant-scoped
        (defense in depth on top of RLS). `updated_at` is always refreshed."""
        values: dict[str, Any] = {"updated_at": text("now()")}
        if status is not None:
            values["status"] = status
        if progress is not None:
            values["progress"] = progress
        if result_ref is not None:
            values["result_ref"] = result_ref
        if result_json is not None:
            values["result_json"] = result_json
        if error is not None:
            values["error"] = error
        await self.session.execute(
            update(Job).where(Job.org_id == tenant_id, Job.id == job_id).values(**values)
        )
        await self.session.flush()
