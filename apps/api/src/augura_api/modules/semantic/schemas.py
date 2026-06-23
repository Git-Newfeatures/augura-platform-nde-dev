"""Pydantic schemas — public contract of the semantic module."""

from typing import Any

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
    """Causal relation of the ontology (B1) — output of GET /semantic/relations."""

    model_config = ConfigDict(from_attributes=True)

    relation_id: str
    subject_concept_id: str
    predicate: str
    object_concept_id: str
    polarity: str
    default_strength: str
    mechanism_summary: str
    active: bool


class SemanticBundle(BaseModel):
    """Response of GET /semantic/bundle — the governed semantic layer as a single block.

    14 tables, rows left as raw `dict`: the frontend indexes them itself
    (semantic-store → taxonomy/ontology loaders). Typing each table would add
    nothing to the read contract. All 14 fields are always present (coalesce to []).
    """

    taxonomy_concepts: list[dict[str, Any]]
    taxonomy_synonyms: list[dict[str, Any]]
    taxonomy_standard_codes: list[dict[str, Any]]
    taxonomy_therapeutic_areas: list[dict[str, Any]]
    taxonomy_relationships: list[dict[str, Any]]
    taxonomy_dq_valid_values: list[dict[str, Any]]
    taxonomy_measurement_units: list[dict[str, Any]]
    unit_conversions: list[dict[str, Any]]
    causal_predicates: list[dict[str, Any]]
    ontology_relations: list[dict[str, Any]]
    ontology_relation_evidence: list[dict[str, Any]]
    ontology_relation_qualifiers: list[dict[str, Any]]
    dq_constraints: list[dict[str, Any]]
    table_archetypes: list[dict[str, Any]]


class ReleaseStatus(BaseModel):
    """Response of GET /semantic/release — current release + per-table count."""

    release: dict[str, Any] | None = None
    counts: dict[str, int]
