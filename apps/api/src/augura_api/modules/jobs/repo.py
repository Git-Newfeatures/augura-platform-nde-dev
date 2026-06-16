"""Accès base du module jobs — idempotence sur (org_id, idempotency_key)."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
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
        # Idempotence : une clé déjà vue renvoie le job existant (un double-clic
        # ne relance pas deux bootstraps — spec §8).
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
