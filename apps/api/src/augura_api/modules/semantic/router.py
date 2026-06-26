"""HTTP adapter of the semantic module."""

import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import Response

from augura_api.core.deps import (
    CurrentTenantDep,
    SessionDep,
    SettingsDep,
    WriteTenantDep,
    require_role,
)
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
    """Causal ontology (B1). `?concept_id=` → subgraph (subject or object = id)."""
    return await SemanticService(SemanticRepo(session)).relations(concept_id=concept_id)


@router.get("/bundle", response_model=schemas.SemanticBundle)
async def bundle(
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.SemanticBundle:
    """Governed semantic layer (14 tables) as a single block — hydrates the frontend store."""
    return await SemanticService(SemanticRepo(session)).bundle()


@router.get("/release", response_model=schemas.ReleaseStatus)
async def release(
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.ReleaseStatus:
    """Current semantic release + per-table count (Versions tab)."""
    return await SemanticService(SemanticRepo(session)).release()


@router.post("/enrich/apply", response_model=enrich_schemas.EnrichApplyResponse)
async def enrich_apply(
    req: enrich_schemas.EnrichApplyRequest,
    tenant: OwnerTenantDep,
    session: SessionDep,
) -> enrich_schemas.EnrichApplyResponse:
    """Persists an enrichment into the GLOBAL ontology (owner-gated). Version bump."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    return await EnrichApplyService(SemanticRepo(session)).apply(req, today=today)


@router.post(
    "/enrich/propose",
    response_model=enrich_schemas.EnrichProposeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enrich_propose(
    req: enrich_schemas.EnrichProposeRequest,
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> enrich_schemas.EnrichProposeAccepted:
    """Runs coverage analysis + LLM proposal as a background job (tracked via polling)."""
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
) -> Response:
    """Serves the proposals of a successful job (tenant-scoped). Read FROM THE DB
    (jobs.result_json), not from disk — re-readable from any Modal container."""
    job = await jobs_iface.get_job(session, tenant.tenant_id, job_id)
    if job is None or job.result_json is None:
        raise NotFoundError("proposals not available", job_id=str(job_id))
    return Response(content=json.dumps(job.result_json), media_type="application/json")
