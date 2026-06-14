"""Logique applicative du module jobs : création (idempotente) + lecture.

Ces fonctions sont l'interface consommée par les autres modules (simulation,
documents) ET par le routeur HTTP du module — une seule porte, pas de court-circuit
vers le repo. `jobs/__init__.py` les ré-exporte comme interface publique.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.jobs.models import Job
from augura_api.modules.jobs.repo import JobRepo


async def create_job(
    session: AsyncSession,
    tenant_id: TenantId,
    *,
    type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> Job:
    return await JobRepo(session).create(
        tenant_id, type=type, payload=payload, idempotency_key=idempotency_key
    )


async def get_job(session: AsyncSession, tenant_id: TenantId, job_id: UUID) -> Job | None:
    return await JobRepo(session).get(tenant_id, job_id)
