"""Contrat public du module mapping."""

from uuid import UUID

from pydantic import BaseModel


class ColumnProposal(BaseModel):
    column: str
    proposed_canonical_id: str | None = None
    proposed_role: str | None = None
    confidence: float | None = None
    confidence_label: str


class MapResult(BaseModel):
    dataset_id: UUID
    mapped_count: int
    total_count: int
    avg_confidence: float | None = None
    columns: list[ColumnProposal]
