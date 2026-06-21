"""Adaptateur HTTP du module corpus."""

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.core.errors import BadRequestError
from augura_api.core.llm.embeddings import Embedder, get_embedder
from augura_api.core.llm.runtime import AgentUpstreamError, get_anthropic_client
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.ctgov import CTGovApiClient
from augura_api.modules.corpus.filters import (
    VALID_DATE_RANGES,
    VALID_STUDY_TYPES,
    SearchFilters,
)
from augura_api.modules.corpus.live_repo import LiveRepo
from augura_api.modules.corpus.pubmed import NCBIPubMedClient
from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.corpus.retrieval import LiteratureRetriever
from augura_api.modules.corpus.service import (
    CorpusService,
    LiteratureService,
    expand_pubmed_query,
)
from augura_api.modules.corpus.snapshot_service import (
    LiteratureSnapshotService,
    to_retrieve_response,
)

router = APIRouter(prefix="/corpus", tags=["corpus"])

log = structlog.get_logger(__name__)

# User-Agent explicite pour les appels sortants live (PubMed/CT.gov) : identifie
# l'app (bonne citoyenneté NLM) et évite les WAF qui filtrent l'UA httpx par défaut.
_RETRIEVE_HEADERS = {
    "User-Agent": "Augura/1.0 (clinical-evidence-platform; +https://augura.health)",
    "Accept": "application/json",
}


def _ndjson(event_type: str, **data: Any) -> str:
    return json.dumps({"type": event_type, **data}) + "\n"


def _validate_sources(sources: list[str] | None) -> None:
    if not sources:
        return
    unknown = [s for s in sources if s not in schemas.VALID_RETRIEVE_SOURCES]
    if unknown:
        raise BadRequestError("source inconnue", value=unknown)


def build_filters(date_range: str, study_types: list[str]) -> SearchFilters:
    """Valide et construit les SearchFilters depuis les champs de la requête."""
    if date_range not in VALID_DATE_RANGES:
        raise BadRequestError("date_range invalide", value=date_range)
    unknown = [t for t in study_types if t not in VALID_STUDY_TYPES]
    if unknown:
        raise BadRequestError("study_type inconnu", value=unknown)
    return SearchFilters(date_range=date_range, study_types=tuple(study_types))


def _live_service(session: SessionDep) -> LiteratureSnapshotService:
    return LiteratureSnapshotService(LiveRepo(session))


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


@router.get("/source-coverage", response_model=schemas.SourceCoverageResponse)
async def source_coverage(
    tenant: CurrentTenantDep, session: SessionDep
) -> schemas.SourceCoverageResponse:
    return await _service(session).source_coverage()


@router.post("/search", response_model=list[schemas.SearchHit])
async def search(
    req: schemas.SearchRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> list[schemas.SearchHit]:
    # Embed-on-server si le client envoie un texte `query` sans embedding pré-calculé.
    embedder: Embedder | None = None
    if not req.query_embedding and req.query:
        embedder = get_embedder(settings)  # lève 503 si la clé OpenAI manque
    return await _service(session).search(req, embedder=embedder)


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


@router.post("/literature/ingest", response_model=schemas.LiteratureSearchResult)
async def literature_ingest(
    req: schemas.LiteratureIngestRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.LiteratureSearchResult:
    """Ingère des enregistrements PubMed précis (par PMID) dans le corpus du tenant.
    Sert « Add to corpus » sur des résultats de retrieve gardés (PubMed only)."""
    embedder: Embedder | None = None
    try:
        embedder = get_embedder(settings)
    except AgentUpstreamError:
        embedder = None
    async with httpx.AsyncClient(timeout=20.0) as http:
        pubmed = NCBIPubMedClient(http, api_key=settings.ncbi_api_key)
        service = LiteratureService(CorpusRepo(session), pubmed, embedder=embedder)
        return await service.ingest_by_ids(tenant, pmids=req.pmids)


# ── Recherche live (retrieve-and-freeze) — verbe distinct de l'ingestion ──────


@router.post("/literature/retrieve")
async def literature_retrieve(
    req: schemas.LiteratureRetrieveRequest,
    tenant: CurrentTenantDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Récupère en direct (PubMed + CT.gov), groupé par source, streamé en NDJSON.
    Ne touche PAS au corpus (aucune ingestion). known-item ⇒ source unique ; topique
    ⇒ fan-out parallèle. Le query_string exact par résultat est porté pour le gel."""
    _validate_sources(req.sources)  # 400 avant le stream si source inconnue
    filters = build_filters(req.date_range, req.study_types)
    sources = set(req.sources) if req.sources else None

    async def gen() -> AsyncIterator[str]:
        # Filet de sécurité : toute erreur (ex. known-item CT.gov 403) devient un event
        # `error` propre au lieu d'une connexion coupée que le front lit en « network error ».
        # Le fan-out topique isole déjà chaque source (cf. LiteratureRetriever._safe_group).
        try:
            # PubMed en direct ; CT.gov via proxy si AUGURA_CTGOV_PROXY_URL est défini
            # (contourne le 403 WAF sur les IP datacenter). proxy=None ⇒ appel direct.
            async with (
                httpx.AsyncClient(timeout=20.0, headers=_RETRIEVE_HEADERS) as http,
                httpx.AsyncClient(
                    timeout=20.0, headers=_RETRIEVE_HEADERS, proxy=settings.ctgov_proxy_url
                ) as ctgov_http,
            ):
                retriever = LiteratureRetriever(
                    NCBIPubMedClient(http, api_key=settings.ncbi_api_key),
                    CTGovApiClient(ctgov_http),
                )
                result = await retriever.retrieve(
                    req.query, sources=sources, max_results=req.max_results, filters=filters
                )
            resp = to_retrieve_response(result)
            yield _ndjson(
                "meta",
                query=resp.query,
                sources=resp.sources,
                known_item=resp.known_item,
                kind=resp.kind,
            )
            for group in resp.groups:
                yield _ndjson("group", **group.model_dump(mode="json"))
            yield _ndjson("done")
        except Exception as exc:
            log.exception("literature_retrieve.failed", query=req.query, error=str(exc))
            yield _ndjson(
                "error", message="La recherche a échoué — réessaie ou ajuste la question."
            )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/literature/snapshots", response_model=schemas.LiteratureSnapshot)
async def create_snapshot(
    req: schemas.SnapshotWriteRequest, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.LiteratureSnapshot:
    """Gèle le jeu de résultats + annotations : calcule le content_hash, épingle
    model/prompt version, persiste. La réponse porte le hash (auto-vérifiable)."""
    return await _live_service(session).freeze(tenant, req)


@router.get("/literature/snapshots", response_model=list[schemas.SnapshotSummary])
async def list_snapshots(
    tenant: CurrentTenantDep, session: SessionDep, study_id: UUID | None = None
) -> list[schemas.SnapshotSummary]:
    """Liste les preuves gelées du tenant (vue légère, sans results ni recalcul de hash)."""
    return await _live_service(session).list_snapshots(tenant, study_id=study_id)


@router.get("/literature/snapshots/{snapshot_id}", response_model=schemas.LiteratureSnapshot)
async def read_snapshot(
    snapshot_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.LiteratureSnapshot:
    """Relit un snapshot et VÉRIFIE le content_hash (erreur dure si divergence).
    Lecture base pure : zéro appel PubMed/CT.gov (rejeu reproductible)."""
    return await _live_service(session).read_snapshot(tenant, snapshot_id)


@router.post("/literature/sessions", response_model=schemas.SearchSession)
async def create_session(
    req: schemas.SessionCreateRequest, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.SearchSession:
    return await _live_service(session).create_session(tenant, req)


@router.get("/literature/sessions", response_model=list[schemas.SearchSession])
async def list_sessions(
    tenant: CurrentTenantDep, session: SessionDep, status: str | None = None
) -> list[schemas.SearchSession]:
    return await _live_service(session).list_sessions(tenant, status=status)


@router.get("/literature/sessions/{session_id}", response_model=schemas.SearchSession)
async def get_session(
    session_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.SearchSession:
    return await _live_service(session).get_session(tenant, session_id)


@router.post("/literature/sessions/{session_id}/events", response_model=schemas.LiteratureEvent)
async def append_event(
    session_id: UUID,
    req: schemas.EventAppendRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.LiteratureEvent:
    return await _live_service(session).append_event(tenant, session_id, req)
