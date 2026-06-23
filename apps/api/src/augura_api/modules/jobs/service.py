"""Application logic for the jobs module: creation (idempotent) + read.

These functions are the interface consumed by other modules (simulation,
documents) AND by the module's HTTP router — a single gate, no shortcut to
the repo. `jobs/__init__.py` re-exports them as the public interface.
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


async def mark_running(session: AsyncSession, tenant_id: TenantId, job_id: UUID) -> None:
    await JobRepo(session).update(tenant_id, job_id, status="running", progress=0.0)


async def set_progress(
    session: AsyncSession, tenant_id: TenantId, job_id: UUID, progress: float
) -> None:
    await JobRepo(session).update(tenant_id, job_id, progress=max(0.0, min(1.0, progress)))


async def mark_succeeded(
    session: AsyncSession,
    tenant_id: TenantId,
    job_id: UUID,
    *,
    result_ref: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> None:
    await JobRepo(session).update(
        tenant_id,
        job_id,
        status="succeeded",
        progress=1.0,
        result_ref=result_ref,
        result_json=result_json,
    )


async def set_result_json(
    session: AsyncSession, tenant_id: TenantId, job_id: UUID, result_json: dict[str, Any]
) -> None:
    """Persist the job's structured result IN THE DB (readable cross-container on Modal)."""
    await JobRepo(session).update(tenant_id, job_id, result_json=result_json)


async def mark_failed(
    session: AsyncSession, tenant_id: TenantId, job_id: UUID, *, error: str
) -> None:
    await JobRepo(session).update(tenant_id, job_id, status="failed", error=error[:2000])
