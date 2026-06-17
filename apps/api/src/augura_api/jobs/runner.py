"""Exécuteur de jobs in-process (équivalent local du worker Modal).

`enqueue_job` planifie l'exécution après la réponse HTTP (FastAPI BackgroundTasks) ;
`execute_job` ouvre une transaction scopée tenant (RLS), marque le job `running`,
dispatche sur un handler par type, persiste le résultat, puis marque `succeeded`/`failed`.

Le calcul lourd (numpy) tourne dans un thread (`anyio.to_thread`) pour ne pas bloquer
la boucle. En prod, `enqueue_job` peut basculer sur `modal.Function.spawn(job_id)` sans
changer ni les handlers ni les appelants — c'est le point de bascule unique.
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


# Un handler reçoit le contexte (session déjà scopée tenant) et renvoie un result_ref
# optionnel (ex. storage_path du dossier généré). Toute exception ⇒ job `failed`.
JobHandler = Callable[[JobContext], Awaitable[str | None]]


def _handlers() -> dict[str, JobHandler]:
    # Import paresseux : évite tout cycle au chargement (les modules importent jobs).
    from augura_api.jobs.handlers import build_handlers

    return build_handlers()


async def execute_job(
    settings: Settings, tenant_id: TenantId, user_id: UserId, job_id: UUID
) -> None:
    """Exécute un job de bout en bout. Robuste : toute erreur est capturée et écrite
    dans job.error (le polling front voit `failed` au lieu de rester bloqué)."""
    sessionmaker = get_sessionmaker(settings)

    # 1) Transaction courte : job → running (visible immédiatement par le polling).
    async with sessionmaker() as session, session.begin():
        await session.execute(set_user_stmt(user_id))
        await session.execute(set_tenant_stmt(tenant_id))
        job = await jobs_iface.get_job(session, tenant_id, job_id)
        if job is None:
            log.warning("job.missing", job_id=str(job_id))
            return
        if job.status in ("succeeded", "running"):
            return  # idempotence : ne pas ré-exécuter un job déjà traité/en cours
        await jobs_iface.mark_running(session, tenant_id, job_id)
        job_type = job.type

    handler = _handlers().get(job_type)
    if handler is None:
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(user_id))
            await session.execute(set_tenant_stmt(tenant_id))
            await jobs_iface.mark_failed(
                session, tenant_id, job_id, error=f"aucun handler pour le type '{job_type}'"
            )
        return

    # 2) Transaction de travail : handler + finalisation.
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
    except Exception as exc:  # noqa: BLE001 — on veut TOUT capturer pour ne pas bloquer le job
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
    """Planifie l'exécution d'un job après la réponse HTTP. Point de bascule unique
    vers Modal (`modal.Function.spawn`) le jour venu."""
    cfg = settings or get_settings()
    background_tasks.add_task(execute_job, cfg, tenant.tenant_id, tenant.user_id, job_id)


# Petit utilitaire de calcul lourd hors-boucle, pour les handlers.
async def run_in_thread[T](fn: Callable[[], T]) -> T:
    return await run_sync(fn)
