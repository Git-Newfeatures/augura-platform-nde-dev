"""Schémas Pydantic du module causal — contrat de POST /causal/dag.

Port fidèle de `reference/data-intake-nde/src/causal/{dag-generator,dag-llm-schema}.js`.
Le DAG est ancré dans l'ontologie B1 (`ontology_relations`) ; le LLM ne fait que
contextualiser (sélectionner / écarter / assigner les rôles), jamais inventer.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Entrée ──────────────────────────────────────────────────────────────────


class MappedConcept(BaseModel):
    """Un concept issu du mapping (POST /datasets/{id}/map) présent dans la donnée."""

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


# ── Sortie LLM (port permissif de DAG_FILTER_TOOL — cf. normalizeLLMResult) ──

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
    polarity: str = "unknown"
    default_strength: str = "moderate"
    mechanism_summary: str = ""


class DagFilterResult(BaseModel):
    """Sortie de l'outil `filter_dag_relations`. Champs permissifs + défauts sûrs."""

    selected_relations: list[SelectedRelation] = []
    excluded_relations: list[ExcludedRelation] = []
    node_roles: dict[str, NodeRole] = {}
    missing_variables: list[str] = []
    proposed_concepts: list[ProposedConcept] = []
    proposed_relations: list[ProposedRelation] = []
    llm_reasoning: str = ""


# ── Sortie HTTP (port de generateDAG return) ────────────────────────────────


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
    # 'from' est un mot-clé Python → champ `source`, alias entrée/sortie "from".
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
