"""Corpus module logic: paginated feed, coverage heatmap, sources, search.

Choice: we validate the enumerable filters (jurisdiction, lifecycle) but leave
`evidence_type`/`source_id` free (exact match, bounded length) so as not to reject
legitimate stored values. age_label and gap_score are computed on the service side.
"""

from datetime import UTC, date, datetime

from pydantic import BaseModel

from augura_api.core.errors import BadRequestError
from augura_api.core.llm.embeddings import Embedder
from augura_api.core.llm.runtime import (
    AgentInvalidOutput,
    AgentUpstreamError,
    LLMClient,
    run_structured_agent,
)
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.models import Document
from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient
from augura_api.modules.corpus.repo import CorpusFilters, CorpusRepo

VALID_JURISDICTIONS = {
    "fda",
    "ema",
    "mhra",
    "health_ca",
    "tga",
    "imdrf",
    "global",
    "unknown",
}
VALID_LIFECYCLES = {"pre_market", "post_market", "policy", "unknown"}

# Heatmap dimensions (zero-fill on these cells).
COVERAGE_JURISDICTIONS = ["fda", "ema", "imdrf", "global"]
COVERAGE_EVIDENCE_TYPES = [
    "guidance",
    "rwe_study",
    "rct",
    "preprint",
    "trial_record",
    "meta_analysis",
]

MAX_LIMIT = 50
EMBEDDING_DIM = 1536


def _age_label(published: date | None, today: date) -> str | None:
    if published is None:
        return None
    days = (today - published).days
    if days < 0:
        return "0d"
    if days < 7:
        return f"{days}d"
    if days < 30:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


def _gap(doc_count: int) -> tuple[float, str]:
    if doc_count == 0:
        return 1.0, "high"
    if doc_count < 5:
        return 0.6, "medium"
    if doc_count < 20:
        return 0.3, "low"
    return 0.0, "low"


class CorpusService:
    def __init__(self, repo: CorpusRepo) -> None:
        self.repo = repo

    async def feed(
        self,
        *,
        jurisdiction: str | None,
        evidence_type: str | None,
        source_id: str | None,
        lifecycle: str | None,
        limit: int,
        offset: int,
    ) -> schemas.FeedResponse:
        if jurisdiction and jurisdiction not in VALID_JURISDICTIONS:
            raise BadRequestError("invalid jurisdiction", value=jurisdiction)
        if lifecycle and lifecycle not in VALID_LIFECYCLES:
            raise BadRequestError("invalid lifecycle", value=lifecycle)
        if source_id and len(source_id) > 100:
            raise BadRequestError("source_id too long")

        limit = min(max(1, limit), MAX_LIMIT)
        offset = max(0, offset)
        filters = CorpusFilters(
            jurisdiction=jurisdiction,
            evidence_type=evidence_type,
            source_id=source_id,
            lifecycle=lifecycle,
        )
        docs, total = await self.repo.feed(filters, limit=limit, offset=offset)
        today = datetime.now(UTC).date()
        items = [
            schemas.FeedDocument(
                id=d.id,
                source_id=d.source_id,
                evidence_type=d.evidence_type,
                jurisdiction=d.jurisdiction,
                lifecycle=d.lifecycle,
                title=d.title,
                summary=d.summary,
                url=d.url,
                published_at=d.published_at,
                is_new=d.is_new,
                age_label=_age_label(d.published_at, today),
            )
            for d in docs
        ]
        return schemas.FeedResponse(meta=schemas.FeedMeta(total=total), documents=items)

    async def coverage(self) -> schemas.CoverageResponse:
        counts = {(j, e): n for j, e, n in await self.repo.coverage_counts()}
        matrix: list[schemas.CoverageCell] = []
        pills: list[schemas.GapPill] = []
        for jur in COVERAGE_JURISDICTIONS:
            for ev in COVERAGE_EVIDENCE_TYPES:
                n = counts.get((jur, ev), 0)
                gap_score, severity = _gap(n)
                matrix.append(
                    schemas.CoverageCell(
                        jurisdiction=jur,
                        evidence_type=ev,
                        doc_count=n,
                        gap_score=gap_score,
                        gap_severity=severity,
                    )
                )
                if severity in ("high", "medium"):
                    pills.append(
                        schemas.GapPill(
                            jurisdiction=jur,
                            evidence_type=ev,
                            gap_severity=severity,
                            gap_score=gap_score,
                            doc_count=n,
                        )
                    )
        pills.sort(key=lambda p: p.gap_score, reverse=True)
        total = await self.repo.total_docs()
        return schemas.CoverageResponse(
            meta=schemas.CoverageMeta(
                total_docs=total,
                jurisdictions=COVERAGE_JURISDICTIONS,
                evidence_types=COVERAGE_EVIDENCE_TYPES,
            ),
            matrix=matrix,
            gap_pills=pills,
        )

    async def sources(self) -> schemas.SourcesResponse:
        counts = await self.repo.source_counts()
        return schemas.SourcesResponse(
            total=sum(c for _, c in counts),
            sources=[schemas.SourceCount(source_id=s, count=c) for s, c in counts],
        )

    async def source_coverage(self) -> schemas.SourceCoverageResponse:
        cells = await self.repo.source_coverage_counts()
        matrix = [
            schemas.SourceCoverageCell(
                source_id=s or "unknown",
                evidence_type=e or "unknown",
                doc_count=n,
            )
            for s, e, n in cells
        ]
        evidence_types = sorted({e or "unknown" for _, e, _ in cells})
        total = await self.repo.total_docs()
        return schemas.SourceCoverageResponse(
            meta=schemas.SourceCoverageMeta(total_docs=total, evidence_types=evidence_types),
            matrix=matrix,
        )

    async def search(
        self, req: schemas.SearchRequest, *, embedder: Embedder | None = None
    ) -> list[schemas.SearchHit]:
        embedding = req.query_embedding
        if not embedding:
            if not req.query:
                raise BadRequestError("query or query_embedding required")
            if embedder is None:
                # No embedder (OpenAI key absent) → explicit 503 rather than 400.
                raise AgentUpstreamError(
                    "semantic search unavailable: embedder required (OpenAI key missing)"
                )
            embedding = await embedder.embed(req.query)
        if len(embedding) != EMBEDDING_DIM:
            raise BadRequestError(
                "query_embedding of unexpected dimension",
                expected=EMBEDDING_DIM,
                got=len(embedding),
            )
        rows = await self.repo.search(embedding, req.match_count, req.filter)
        return [schemas.SearchHit.model_validate(r) for r in rows]


# ── Literature search agent (PubMed → corpus) ────────────────────────────────


class _PubMedQuery(BaseModel):
    query: str


_QUERY_TOOL = {
    "name": "pubmed_query",
    "description": "Returns ONE optimized PubMed query (boolean operators + MeSH terms "
    "if useful) for the provided research question.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "PubMed query string"}},
        "required": ["query"],
    },
}


async def expand_pubmed_query(client: LLMClient, model: str, raw: str) -> str:
    """Expands a natural-language question into a PubMed query via the LLM.
    Degrades to the raw query if the agent fails."""
    try:
        result = await run_structured_agent(
            client,
            model=model,
            system=(
                "You are a biomedical information specialist. Turn the research "
                "question into ONE precise PubMed query (booleans + MeSH if relevant). "
                "Stay focused; no explanation, just the query."
            ),
            tool=_QUERY_TOOL,  # pyright: ignore[reportArgumentType]
            messages=[{"role": "user", "content": raw}],
            output_model=_PubMedQuery,
        )
        return result.output.query.strip() or raw
    except (AgentUpstreamError, AgentInvalidOutput):
        return raw


class LiteratureService:
    """Searches PubMed (E-utilities) and ingests the articles into the corpus
    (Document + Chunk). Optional embedder: without an OpenAI key, we ingest without a
    vector (the Literature view shows them; the semantic search ignores them)."""

    def __init__(
        self, repo: CorpusRepo, pubmed: PubMedClient, *, embedder: Embedder | None = None
    ) -> None:
        self.repo = repo
        self.pubmed = pubmed
        self.embedder = embedder

    async def search_and_ingest(
        self,
        tenant: CurrentTenant,
        *,
        query: str,
        max_results: int,
        effective_query: str | None = None,
    ) -> schemas.LiteratureSearchResult:
        eq = (effective_query or query).strip()
        articles = await self.pubmed.search(eq, max_results)
        return await self._ingest_articles(tenant, articles, query=query, effective_query=eq)

    async def ingest_by_ids(
        self, tenant: CurrentTenant, *, pmids: list[str]
    ) -> schemas.LiteratureSearchResult:
        """Ingests specific PubMed records (efetch by PMID), without searching.
        Serves "Add to corpus" on already-selected retrieve results."""
        articles = await self.pubmed.fetch_by_ids(pmids)
        return await self._ingest_articles(
            tenant, articles, query=",".join(pmids), effective_query=",".join(pmids)
        )

    async def _ingest_articles(
        self,
        tenant: CurrentTenant,
        articles: list[PubMedArticle],
        *,
        query: str,
        effective_query: str,
    ) -> schemas.LiteratureSearchResult:
        today = datetime.now(UTC).date()
        ingested: list[Document] = []
        embedded_any = False
        for art in articles:
            if art.url and await self.repo.find_document_by_url(tenant.tenant_id, art.url):
                continue  # already ingested for this tenant
            doc = await self.repo.insert_document(
                tenant.tenant_id,
                source_id="pubmed",
                title=art.title,
                summary=art.abstract or None,
                url=art.url,
                evidence_type=art.evidence_type,
                published_at=art.published_at,
                is_new=True,
            )
            content = (art.title + (f"\n\n{art.abstract}" if art.abstract else "")).strip()
            embedding: list[float] | None = None
            if self.embedder is not None:
                try:
                    embedding = await self.embedder.embed(content)
                    embedded_any = True
                except (AgentUpstreamError, AgentInvalidOutput):
                    embedding = None
            await self.repo.add_chunk(
                doc.id, tenant.tenant_id, content=content, embedding=embedding
            )
            ingested.append(doc)
        documents = [
            schemas.FeedDocument(
                id=d.id,
                source_id=d.source_id,
                evidence_type=d.evidence_type,
                jurisdiction=d.jurisdiction,
                lifecycle=d.lifecycle,
                title=d.title,
                summary=d.summary,
                url=d.url,
                published_at=d.published_at,
                is_new=d.is_new,
                age_label=_age_label(d.published_at, today),
            )
            for d in ingested
        ]
        return schemas.LiteratureSearchResult(
            query=query,
            effective_query=effective_query,
            found=len(articles),
            ingested=len(ingested),
            embedded=embedded_any,
            documents=documents,
        )
