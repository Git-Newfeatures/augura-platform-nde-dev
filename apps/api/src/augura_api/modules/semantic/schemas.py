"""Schémas Pydantic — contrat public du module semantic."""

from pydantic import BaseModel, ConfigDict


class ConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    local_concept_id: str
    concept_name: str
    augura_domain: str
    layer: int
    value_type: str | None = None
    value_min: float | None = None
    value_max: float | None = None
    canonical_unit: str | None = None
    dq_column_role: str | None = None
    range_support_status: str | None = None
    active: bool
