"""Schémas Pydantic — contrat public du module semantic."""

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


class SemanticBundle(BaseModel):
    """Réponse de GET /semantic/bundle — la couche sémantique gouvernée en bloc.

    14 tables, lignes laissées en `dict` brut : le front les indexe lui-même
    (semantic-store → taxonomy/ontology loaders). Typer chaque table n'apporterait
    rien au contrat de lecture. Les 14 champs sont toujours présents (coalesce à []).
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
    """Réponse de GET /semantic/release — release courante + compte par table."""

    release: dict[str, Any] | None = None
    counts: dict[str, int]
