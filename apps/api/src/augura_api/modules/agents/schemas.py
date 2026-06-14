"""Contrats du module agents. DagResponse est validé depuis la sortie outil ET
renvoyé tel quel au front (edges émis en {from, to} via alias)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DagRequest(BaseModel):
    intervention: str
    outcome: str
    population: str | None = None
    study_type: str | None = None
    selected_outcome: str | None = None
    product_docs: str | None = None
    candidate_outcomes: list[str] = []
    dataset_variables: dict[str, Any] | None = None
    gap_variables: list[dict[str, Any]] = []


class DagNode(BaseModel):
    id: str
    label: str
    role: str
    measured: bool
    rationale: str | None = None


class DagEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 'from' est un mot-clé Python → champ `source`, alias entrée/sortie "from".
    source: str = Field(validation_alias="from", serialization_alias="from")
    to: str


class DagResponse(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]
    adjustment_set: list[str]
    collider_ids: list[str] = []
    rationale: str
