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


# ── gap-detection ──────────────────────────────────────────────────────────


class MeasuredVariable(BaseModel):
    column: str
    role: str | None = None


class GapRequest(BaseModel):
    intervention: str
    outcome: str
    population: str | None = None
    selected_outcome: str | None = None
    measured_variables: list[MeasuredVariable] = []


class MissingVariable(BaseModel):
    name: str
    column_hint: str | None = None
    role: str
    category: str
    rationale: str
    severity: str


class GapResponse(BaseModel):
    missing_variables: list[MissingVariable]


# ── variable-check (1b) ────────────────────────────────────────────────────


class ColumnStat(BaseModel):
    column: str
    n_total: int | None = None
    n_non_null: int | None = None
    null_pct: float | None = None
    value_kind: str | None = None
    n_distinct: int | None = None
    min: float | None = None
    max: float | None = None
    top_values: list[Any] | None = None


class Sheet(BaseModel):
    name: str
    headers: list[str] = []
    sample: list[list[Any]] = []
    column_stats: list[ColumnStat] = []


class VariableCheckRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str | None = Field(default=None, validation_alias="projectId")
    product_description: str = ""
    sheets: list[Sheet]


class ColumnMatch(BaseModel):
    sheet: str
    column: str
    proposed_role: str
    proposed_group: str
    proposed_canonical_id: str | None = None
    confidence: float
    rationale: str
    alternatives: list[str] = []


class ClassifyColumnsResponse(BaseModel):
    columns: list[ColumnMatch]


class DatasetQuestion(BaseModel):
    question_code: str
    answer: str
    options: list[str] = []
    rationale: str | None = None
    confidence: float
    evidence_columns: list[str] = []


class DatasetQuestionsResponse(BaseModel):
    questions: list[DatasetQuestion]


class VariableCheckResponse(BaseModel):
    clinical_domain: str | None = None
    matches: list[ColumnMatch]
    dataset_questions: list[DatasetQuestion] | None = None
