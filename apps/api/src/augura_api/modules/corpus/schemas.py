"""Public contract of the corpus module (mapped to pulse-feed / coverage-map / sources)."""

from datetime import date, datetime
from typing import Any
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
    # The client provides EITHER a `query` text (embedded server-side), OR a
    # pre-computed `query_embedding` (dim 1536). At least one of the two is required.
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
    # Expands the query into PubMed syntax (MeSH) via the LLM before searching.
    # Without an Anthropic key, we fall back to the raw query.
    expand: bool = False


class LiteratureSearchResult(BaseModel):
    query: str
    effective_query: str
    found: int
    ingested: int
    embedded: bool
    documents: list[FeedDocument]


class LiteratureIngestRequest(BaseModel):
    pmids: list[str] = Field(min_length=1, max_length=50)


# ── Live search (retrieve-and-freeze) — distinct from the ingestion above ──
# New verb: retrieves + freezes an evidence set (content hash), WITHOUT
# ingesting into the corpus, WITHOUT embedding, WITHOUT DATA_CHANGED_EVENT.

VALID_RETRIEVE_SOURCES = ("pubmed", "ctgov")


class LiteratureRetrieveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    # Default: both sources. Validated on the service side (unknown source → 400).
    sources: list[str] | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    # v0 filters: date window + study types. Validated on the router side (_build_filters).
    date_range: str = "any"
    study_types: list[str] = Field(default_factory=list)


class RetrievedItemOut(BaseModel):
    source: str
    id: str
    title: str
    query_string: str
    retrieval_date: date
    record: dict[str, Any]
    annotation: str | None = None
    rationale: str | None = None  # curation justification (None if not curated)


class SourceGroupOut(BaseModel):
    source: str
    query_string: str
    items: list[RetrievedItemOut]
    note: str | None = None


class LiteratureRetrieveResponse(BaseModel):
    query: str
    sources: list[str]
    known_item: bool
    kind: str | None = None
    groups: list[SourceGroupOut]


# ── Canonical frozen-evidence schema (snapshot) ───────────────────────────────


class FrozenResult(BaseModel):
    """Per citation: the source, the id, the EXACT query_string (not the user
    question), the retrieval date, the frozen record and the annotation."""

    source: str
    id: str
    title: str
    query_string: str
    retrieval_date: date
    record: dict[str, Any]
    annotation: str | None = None  # kept / dismissed / null
    rationale: str | None = None  # frozen curation justification (provenance)


class SnapshotWriteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    sources: list[str]
    model_version: str
    prompt_version: str
    study_id: UUID | None = None  # None ⇒ standalone snapshot (creator only)
    results: list[FrozenResult]


class LiteratureSnapshot(BaseModel):
    """Per artifact: provenance metadata + frozen results + content_hash.
    `verified` is set on read after recomputing the hash."""

    id: UUID
    study_id: UUID | None = None
    query: str
    sources: list[str]
    model_version: str
    prompt_version: str
    results: list[FrozenResult]
    created_at: datetime
    created_by: UUID
    content_hash: str
    verified: bool = True


class SnapshotSummary(BaseModel):
    """Lightweight view for the "Saved evidence" list: no results, no hash."""

    id: UUID
    study_id: UUID | None = None
    query: str
    sources: list[str]
    result_count: int
    created_at: datetime


class SessionCreateRequest(BaseModel):
    query: str | None = Field(default=None, max_length=400)
    study_id: UUID | None = None


class SearchSession(BaseModel):
    id: UUID
    study_id: UUID | None = None
    query: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: UUID


class EventAppendRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = {}


class LiteratureEvent(BaseModel):
    id: UUID
    session_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    created_by: UUID
