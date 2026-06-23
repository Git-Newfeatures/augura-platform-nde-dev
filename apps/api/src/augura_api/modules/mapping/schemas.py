"""Public contract for the mapping module."""

from uuid import UUID

from pydantic import BaseModel


class ColumnProposal(BaseModel):
    column: str
    # Source table/sheet of the column — lets the frontend group the mapping by table
    # instead of showing one flat attribute list. CSV files share the sheet "data".
    sheet: str | None = None
    proposed_canonical_id: str | None = None
    proposed_role: str | None = None
    layer: int | None = None
    domain: str | None = None
    confidence: float | None = None
    confidence_label: str


class MapResult(BaseModel):
    dataset_id: UUID
    mapped_count: int
    total_count: int
    avg_confidence: float | None = None
    columns: list[ColumnProposal]
