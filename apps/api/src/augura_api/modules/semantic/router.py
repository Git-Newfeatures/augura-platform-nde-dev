"""Adaptateur HTTP du module semantic."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import Response

from augura_api.core import storage
from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep, require_role
from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.jobs.runner import enqueue_job
from augura_api.modules import jobs as jobs_iface
from augura_api.modules.semantic import enrich_schemas, schemas
from augura_api.modules.semantic.enrich_apply import EnrichApplyService
from augura_api.modules.semantic.repo import SemanticRepo
from augura_api.modules.semantic.service import SemanticService

router = APIRouter(prefix="/semantic", tags=["semantic"])

OwnerTenantDep = Annotated[CurrentTenant, Depends(require_role("owner"))]


@router.get("/concepts", response_model=list[schemas.ConceptOut])
async def concepts(
    tenant: CurrentTenantDep,
    session: SessionDep,
    domain: str | None = None,
    active: bool = True,
) -> list[schemas.ConceptOut]:
    return await SemanticService(SemanticRepo(session)).concepts(domain=domain, active=active)


@router.get("/relations", response_model=list[schemas.RelationOut])
async def relations(
    tenant: CurrentTenantDep,
    session: SessionDep,
    concept_id: str | None = None,
) -> list[schemas.RelationOut]:
    """Ontologie causale (B1). `?concept_id=` → sous-graphe (sujet ou objet = id)."""
    return await SemanticService(SemanticRepo(session)).relations(concept_id=concept_id)


@router.get("/bundle", response_model=schemas.SemanticBundle)
async def bundle(
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.SemanticBundle:
    """Couche sémantique gouvernée (14 tables) en un bloc — hydrate le store front."""
    return await SemanticService(SemanticRepo(session)).bundle()


@router.get("/release", response_model=schemas.ReleaseStatus)
async def release(
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.ReleaseStatus:
    """Release sémantique courante + compte par table (onglet Versions)."""
    return await SemanticService(SemanticRepo(session)).release()


@router.post("/enrich/apply", response_model=enrich_schemas.EnrichApplyResponse)
async def enrich_apply(
    req: enrich_schemas.EnrichApplyRequest,
    tenant: OwnerTenantDep,
    session: SessionDep,
) -> enrich_schemas.EnrichApplyResponse:
    """Persiste un enrichissement dans l'ontologie GLOBALE (gated owner). Bump de version."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    return await EnrichApplyService(SemanticRepo(session)).apply(req, today=today)


@router.post(
    "/enrich/propose",
    response_model=enrich_schemas.EnrichProposeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enrich_propose(
    req: enrich_schemas.EnrichProposeRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> enrich_schemas.EnrichProposeAccepted:
    """Lance l'analyse de couverture + proposition LLM en job background (suivi par polling)."""
    job = await jobs_iface.create_job(
        session,
        tenant.tenant_id,
        type="enrich_propose",
        payload={
            "questions": [q.model_dump() for q in req.questions],
            "selected_concepts": req.selected_concepts,
        },
    )
    enqueue_job(background_tasks, tenant, job.id, settings=settings)
    return enrich_schemas.EnrichProposeAccepted(job_id=str(job.id))


@router.get("/enrich/proposals/{job_id}")
async def enrich_proposals(
    job_id: UUID,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Sert l'artifact JSON des propositions d'un job réussi (scopé tenant)."""
    job = await jobs_iface.get_job(session, tenant.tenant_id, job_id)
    if job is None or not job.result_ref:
        raise NotFoundError("propositions non disponibles", job_id=str(job_id))
    try:
        data = storage.read_bytes(settings, job.result_ref)
    except FileNotFoundError as exc:
        raise NotFoundError("artifact introuvable", job_id=str(job_id)) from exc
    return Response(content=data, media_type="application/json")
