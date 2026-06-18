"""Adaptateur HTTP du module semantic."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.repo import SemanticRepo
from augura_api.modules.semantic.service import SemanticService

router = APIRouter(prefix="/semantic", tags=["semantic"])


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
