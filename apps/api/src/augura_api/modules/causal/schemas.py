"""Pydantic schemas for the causal module — contract of POST /causal/dag.

Faithful port of `reference/data-intake-nde/src/causal/{dag-generator,dag-llm-schema}.js`.
The DAG is anchored in the B1 ontology (`ontology_relations`); the LLM only
contextualizes (select / discard / assign roles), it never invents.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Input ─────────────────────────────────────────────────────────────────────


class MappedConcept(BaseModel):
    """A concept from the mapping (POST /datasets/{id}/map) present in the data."""

    concept_id: str
    concept_label: str = ""
    concept_domain: str = "unknown"
    concept_layer: int = 0
    confidence: float | None = None


class PicotOutcome(BaseModel):
    concept_id: str | None = None
    label: str | None = None


class Picot(BaseModel):
    intervention: str | None = None
    comparator: str | None = None
    outcomes: list[PicotOutcome] = []
    timeframe: str | None = None
    population: str | None = None
    therapeutic_area: str | None = None
    intervention_concept_id: str | None = None


class CausalDagRequest(BaseModel):
    mapped_concepts: list[MappedConcept] = []
    picot: Picot | None = None
    clinical_question: str | None = None


# ── LLM output (permissive port of DAG_FILTER_TOOL — cf. normalizeLLMResult) ──

Role = Literal[
    "exposure", "outcome", "confounder", "mediator", "effect_modifier", "collider", "other"
]
NodeSource = Literal["mapping", "ontology_inferred", "llm_proposed"]


class SelectedRelation(BaseModel):
    relation_id: str
    dag_role_subject: str = "other"
    dag_role_object: str = "other"
    inclusion_reason: str = ""


class ExcludedRelation(BaseModel):
    relation_id: str
    exclusion_reason: str = ""


class NodeRole(BaseModel):
    role: str = "other"
    reasoning: str = ""


class ProposedConcept(BaseModel):
    provisional_id: str
    label: str = ""
    domain: str = "other"
    layer: int = 0
    rationale: str = ""


class ProposedRelation(BaseModel):
    subject_concept_id: str
    object_concept_id: str
    predicate: str = "causally_influences"
    polarity: str = "neutral"
    default_strength: str = "moderate"
    mechanism_summary: str = ""


class DagFilterResult(BaseModel):
    """Output of the `filter_dag_relations` tool. Permissive fields + safe defaults."""

    selected_relations: list[SelectedRelation] = []
    excluded_relations: list[ExcludedRelation] = []
    node_roles: dict[str, NodeRole] = {}
    missing_variables: list[str] = []
    proposed_concepts: list[ProposedConcept] = []
    proposed_relations: list[ProposedRelation] = []
    llm_reasoning: str = ""


# ── HTTP output (port of generateDAG return) ────────────────────────────────


class DagNode(BaseModel):
    id: str
    label: str
    domain: str
    layer: int
    role: Role
    source: NodeSource
    observed: bool
    adjusted: bool
    confidence: float | None = None
    standard_codes: dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class DagEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    # 'from' is a Python keyword → field `source`, input/output alias "from".
    source: str = Field(validation_alias="from", serialization_alias="from")
    to: str
    type: Literal["causal", "associative", "temporal"]
    strength: str
    direction: Literal["forward", "inhibitory"]
    polarity: str
    temporal_lag: str
    predicate: str
    dag_role_from: str
    dag_role_to: str
    provenance: str
    notes: str
    supported_by_data: bool
    has_qualifier: bool
    qualifiers: list[dict[str, Any]] = []


class Graph(BaseModel):
    type: Literal["dag"] = "dag"
    exposure_ids: list[str] = []
    outcome_ids: list[str] = []
    adjusted_ids: list[str] = []
    latent_ids: list[str] = []


class MissingVariable(BaseModel):
    concept_id: str
    label: str
    importance: str = "llm_identified"


class Quality(BaseModel):
    score: float
    label: Literal["High", "Medium", "Low"]
    has_exposure: bool
    has_outcome: bool
    has_confounder: bool
    data_backing_rate: float
    node_data_coverage: float
    data_backed_edges: int
    total_edges: int
    issues: list[str] = []


class CausalDagResponse(BaseModel):
    format: str = "augura.intake.dag/1"
    generation_mode: str = "ontology_llm"
    clinical_question: str | None = None
    graph: Graph
    nodes: list[DagNode]
    edges: list[DagEdge]
    missing_variables: list[MissingVariable] = []
    warnings: list[str] = []
    quality: Quality
    llm_context: dict[str, Any] = {}
    proposed_relations: list[ProposedRelation] = []
