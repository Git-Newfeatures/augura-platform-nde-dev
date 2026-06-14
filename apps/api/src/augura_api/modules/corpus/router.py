"""Adaptateur HTTP du module corpus."""

import httpx
from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.core.llm.embeddings import Embedder, get_embedder
from augura_api.core.llm.runtime import AgentUpstreamError, get_anthropic_client
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.pubmed import NCBIPubMedClient
from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.corpus.service import (
    CorpusService,
    LiteratureService,
    expand_pubmed_query,
)

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


@router.post("/literature", response_model=schemas.LiteratureSearchResult)
async def literature(
    req: schemas.LiteratureSearchRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.LiteratureSearchResult:
    """Agent de recherche de littérature : cherche sur PubMed (E-utilities NCBI) et
    ingère les articles dans le corpus du tenant (Document + Chunk). Embedder/LLM
    optionnels (sans clé : ingestion sans vecteur, requête non élargie)."""
    embedder: Embedder | None = None
    try:
        embedder = get_embedder(settings)
    except AgentUpstreamError:
        embedder = None

    effective_query: str | None = None
    if req.expand:
        try:
            client = get_anthropic_client(settings)
            effective_query = await expand_pubmed_query(
                client, settings.agent_model_fast, req.query
            )
        except AgentUpstreamError:
            effective_query = None

    async with httpx.AsyncClient(timeout=20.0) as http:
        pubmed = NCBIPubMedClient(http, api_key=settings.ncbi_api_key)
        service = LiteratureService(CorpusRepo(session), pubmed, embedder=embedder)
        return await service.search_and_ingest(
            tenant,
            query=req.query,
            max_results=req.max_results,
            effective_query=effective_query,
        )
