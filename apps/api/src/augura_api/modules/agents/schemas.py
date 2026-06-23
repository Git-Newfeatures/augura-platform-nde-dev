"""Agents module contracts. DagResponse is validated from the tool output AND
returned as-is to the frontend (edges emitted as {from, to} via alias)."""

from typing import Any, Literal

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

    # 'from' is a Python keyword → field `source`, input/output alias "from".
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


# ── trace / E1 profiling (SSE) ─────────────────────────────────────────────


class ProfilingRequest(BaseModel):
    # system + tools + messages are provided by the frontend (like api/trace.js).
    system: str
    tools: list[dict[str, Any]] = []
    messages: list[dict[str, Any]]
    product_description: str | None = None


# ── chat (inline assistant, LLM gateway) ───────────────────────────────────


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    system: str | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    text: str
    model: str
