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


class RelationOut(BaseModel):
    """Relation causale de l'ontologie (B1) — sortie de GET /semantic/relations."""

    model_config = ConfigDict(from_attributes=True)

    relation_id: str
    subject_concept_id: str
    predicate: str
    object_concept_id: str
    polarity: str
    default_strength: str
    mechanism_summary: str
    active: bool
