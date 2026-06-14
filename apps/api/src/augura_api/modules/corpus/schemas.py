"""Contrat public du module corpus (mappé sur pulse-feed / coverage-map / sources)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel


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


class SearchRequest(BaseModel):
    query_embedding: list[float]
    match_count: int = 20
    filter: dict[str, str] = {}


class SearchHit(BaseModel):
    id: UUID
    document_id: UUID
    content: str
    similarity: float
    source_id: str | None = None
    title: str | None = None
