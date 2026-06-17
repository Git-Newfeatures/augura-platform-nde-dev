"""Contrat public du module corpus (mappé sur pulse-feed / coverage-map / sources)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class FeedDocument(BaseModel):
    id: UUID
    source_id: str
    evidence_type: str | None = None
    jurisdiction: str | None = None
    lifecycle: str | None = None
    title: str
    summary: str | None = None
    url: str | None = None
    published_at: date | None = None
    is_new: bool = False
    age_label: str | None = None


class FeedMeta(BaseModel):
    total: int


class FeedResponse(BaseModel):
    meta: FeedMeta
    documents: list[FeedDocument]


class CoverageCell(BaseModel):
    jurisdiction: str
    evidence_type: str
    doc_count: int
    gap_score: float
    gap_severity: str


class GapPill(BaseModel):
    jurisdiction: str
    evidence_type: str
    gap_severity: str
    gap_score: float
    doc_count: int


class CoverageMeta(BaseModel):
    total_docs: int
    jurisdictions: list[str]
    evidence_types: list[str]


class CoverageResponse(BaseModel):
    meta: CoverageMeta
    matrix: list[CoverageCell]
    gap_pills: list[GapPill]


class SourceCount(BaseModel):
    source_id: str
    count: int


class SourcesResponse(BaseModel):
    total: int
    sources: list[SourceCount]


class SourceCoverageCell(BaseModel):
    source_id: str
    evidence_type: str
    doc_count: int


class SourceCoverageMeta(BaseModel):
    total_docs: int
    evidence_types: list[str]


class SourceCoverageResponse(BaseModel):
    meta: SourceCoverageMeta
    matrix: list[SourceCoverageCell]


class SearchRequest(BaseModel):
    # Le client fournit SOIT un texte `query` (embeddé côté serveur), SOIT un
    # `query_embedding` pré-calculé (dim 1536). Au moins l'un des deux est requis.
    query: str | None = Field(default=None, min_length=1, max_length=1000)
    query_embedding: list[float] | None = None
    match_count: int = 20
    filter: dict[str, str] = {}


class SearchHit(BaseModel):
    id: UUID
    document_id: UUID
    content: str
    similarity: float
    source_id: str | None = None
    title: str | None = None


class LiteratureSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    max_results: int = Field(default=10, ge=1, le=50)
    # Élargit la requête en syntaxe PubMed (MeSH) via le LLM avant la recherche.
    # Sans clé Anthropic, on retombe sur la requête brute.
    expand: bool = False


class LiteratureSearchResult(BaseModel):
    query: str
    effective_query: str
    found: int
    ingested: int
    embedded: bool
    documents: list[FeedDocument]
