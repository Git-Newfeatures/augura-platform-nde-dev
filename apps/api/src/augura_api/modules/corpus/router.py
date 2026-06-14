"""Adaptateur HTTP du module corpus."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.corpus.service import CorpusService

router = APIRouter(prefix="/corpus", tags=["corpus"])


def _service(session: SessionDep) -> CorpusService:
    return CorpusService(CorpusRepo(session))


@router.get("/feed", response_model=schemas.FeedResponse)
async def feed(
    tenant: CurrentTenantDep,
    session: SessionDep,
    jurisdiction: str | None = None,
    evidence_type: str | None = None,
    source_id: str | None = None,
    lifecycle: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> schemas.FeedResponse:
    return await _service(session).feed(
        jurisdiction=jurisdiction,
        evidence_type=evidence_type,
        source_id=source_id,
        lifecycle=lifecycle,
        limit=limit,
        offset=offset,
    )


@router.get("/coverage", response_model=schemas.CoverageResponse)
async def coverage(tenant: CurrentTenantDep, session: SessionDep) -> schemas.CoverageResponse:
    return await _service(session).coverage()


@router.get("/sources", response_model=schemas.SourcesResponse)
async def sources(tenant: CurrentTenantDep, session: SessionDep) -> schemas.SourcesResponse:
    return await _service(session).sources()


@router.post("/search", response_model=list[schemas.SearchHit])
async def search(
    req: schemas.SearchRequest, tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.SearchHit]:
    return await _service(session).search(req)
