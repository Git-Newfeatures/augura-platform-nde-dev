"""Adaptateur HTTP du module semantic."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from augura_api.core.deps import CurrentTenantDep, SessionDep, require_role
from augura_api.core.tenancy import CurrentTenant
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
