"""In-process job runner (local equivalent of the Modal worker).

`enqueue_job` schedules execution after the HTTP response (FastAPI BackgroundTasks);
`execute_job` opens a tenant-scoped transaction (RLS), marks the job `running`,
dispatches to a per-type handler, persists the result, then marks `succeeded`/`failed`.

Heavy computation (numpy) runs in a thread (`anyio.to_thread`) so as not to block
the loop. In prod, `enqueue_job` can switch to `modal.Function.spawn(job_id)` without
changing either the handlers or the callers — this is the single switch point.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import structlog
from anyio.to_thread import run_sync
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.config import Settings, get_settings
from augura_api.core.db import get_sessionmaker, set_tenant_stmt, set_user_stmt
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules import jobs as jobs_iface
from augura_api.modules.jobs.models import Job

log = structlog.get_logger(__name__)


@dataclass
class JobContext:
    session: AsyncSession
    settings: Settings
    tenant_id: TenantId
    user_id: UserId
    job: Job


# A handler receives the context (session already tenant-scoped) and returns an optional
# result_ref (e.g. storage_path of the generated document). Any exception ⇒ job `failed`.
JobHandler = Callable[[JobContext], Awaitable[str | None]]


def _handlers() -> dict[str, JobHandler]:
    # Lazy import: avoids any load-time cycle (the modules import jobs).
    from augura_api.jobs.handlers import build_handlers

    return build_handlers()


async def execute_job(
    settings: Settings, tenant_id: TenantId, user_id: UserId, job_id: UUID
) -> None:
    """Executes a job end to end. Robust: any error is caught and written
    to job.error (the front-end polling sees `failed` instead of staying stuck)."""
    sessionmaker = get_sessionmaker(settings)

    # 1) Short transaction: job → running (immediately visible to polling).
    async with sessionmaker() as session, session.begin():
        await session.execute(set_user_stmt(user_id))
        await session.execute(set_tenant_stmt(tenant_id))
        job = await jobs_iface.get_job(session, tenant_id, job_id)
        if job is None:
            log.warning("job.missing", job_id=str(job_id))
            return
        if job.status in ("succeeded", "running"):
            return  # idempotence: don't re-run a job already processed/in progress
        await jobs_iface.mark_running(session, tenant_id, job_id)
        job_type = job.type

    handler = _handlers().get(job_type)
    if handler is None:
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(user_id))
            await session.execute(set_tenant_stmt(tenant_id))
            await jobs_iface.mark_failed(
                session, tenant_id, job_id, error=f"no handler for type '{job_type}'"
            )
        return

    # 2) Work transaction: handler + finalization.
    try:
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(user_id))
            await session.execute(set_tenant_stmt(tenant_id))
            job = await jobs_iface.get_job(session, tenant_id, job_id)
            assert job is not None
            ctx = JobContext(
                session=session,
                settings=settings,
                tenant_id=tenant_id,
                user_id=user_id,
                job=job,
            )
            result_ref = await handler(ctx)
            await jobs_iface.mark_succeeded(session, tenant_id, job_id, result_ref=result_ref)
        log.info("job.succeeded", job_id=str(job_id), type=job_type)
    except Exception as exc:  # noqa: BLE001 — catch EVERYTHING so the job never stays stuck
        log.exception("job.failed", job_id=str(job_id), type=job_type)
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(user_id))
            await session.execute(set_tenant_stmt(tenant_id))
            await jobs_iface.mark_failed(
                session, tenant_id, job_id, error=f"{type(exc).__name__}: {exc}"
            )


def enqueue_job(
    background_tasks: BackgroundTasks,
    tenant: CurrentTenant,
    job_id: UUID,
    *,
    settings: Settings | None = None,
) -> None:
    """Schedules a job's execution outside the request/response cycle.

    Two runners, chosen by environment — SINGLE switch point:
    - On Modal (remote container): `modal.Function.spawn` launches the dedicated
      `run_job` worker in another container. Indispensable because Starlette
      `BackgroundTasks` do NOT run reliably on Modal (the container can be frozen
      as soon as the HTTP response is returned → the job would stay stuck in `queued`).
    - Locally (`modal.is_local()`): `BackgroundTasks` runs the job in-process
      after the response, with no Modal dependency.
    """
    cfg = settings or get_settings()

    try:
        import modal

        on_modal = not modal.is_local()
    except Exception:  # noqa: BLE001 — modal absent/uninitialized ⇒ local path
        on_modal = False

    if on_modal:
        from augura_api.jobs.modal_spawn import spawn_run_job

        spawn_run_job(str(tenant.tenant_id), str(tenant.user_id), str(job_id))
        return

    background_tasks.add_task(execute_job, cfg, tenant.tenant_id, tenant.user_id, job_id)


# Small utility for off-loop heavy computation, for the handlers.
async def run_in_thread[T](fn: Callable[[], T]) -> T:
    return await run_sync(fn)
