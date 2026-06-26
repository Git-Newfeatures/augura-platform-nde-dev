"""Public contract of the datasets module (+ cohorts read by the frontend)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    study_id: UUID | None = None
    storage_path: str | None = None
    row_count: int | None = None
    # Number of profiled columns (dataset_columns table, same module). The study
    # label is resolved on the frontend via study_id: the datasets↔studies
    # independence (import-linter) forbids a JOIN on studies here.
    column_count: int = 0
    file_count: int = 0
    created_at: datetime


class DatasetCreate(BaseModel):
    name: str
    study_id: UUID | None = None
    storage_path: str | None = None
    row_count: int | None = None


class DatasetFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    row_count: int | None = None
    column_count: int = 0
    position: int = 0
    created_at: datetime


class ColumnIn(BaseModel):
    sheet: str
    name: str
    value_kind: str | None = None
    n_total: int | None = None
    n_non_null: int | None = None
    null_pct: float | None = None
    n_distinct: int | None = None
    min: float | None = None
    max: float | None = None
    top_values: list[Any] | None = None
    proposed_role: str | None = None
    proposed_group: str | None = None
    proposed_canonical_id: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    user_decision: str = "pending"
    final_role: str | None = None
    final_canonical_id: str | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    sheet: str
    name: str
    value_kind: str | None = None
    n_total: int | None = None
    n_non_null: int | None = None
    null_pct: float | None = None
    n_distinct: int | None = None
    min: float | None = Field(default=None, validation_alias="value_min")
    max: float | None = Field(default=None, validation_alias="value_max")
    top_values: list[Any] | None = None
    proposed_role: str | None = None
    proposed_group: str | None = None
    proposed_canonical_id: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    user_decision: str
    final_role: str | None = None
    final_canonical_id: str | None = None


class ColumnsPut(BaseModel):
    columns: list[ColumnIn]


class UploadResult(BaseModel):
    dataset: DatasetOut
    columns: list[ColumnOut]
    files: list[DatasetFileOut] = []
    warnings: list[str] = []


class DataDictionaryEntry(BaseModel):
    """One variable described by a data dictionary."""

    name: str
    label: str | None = None
    value_type: str | None = None  # e.g. numeric, categorical, date, text, binary
    description: str | None = None
    allowed_values: list[str] = []


class DataDictionaryResult(BaseModel):
    format: str = "augura.intake.data_dictionary/1"
    # "structured" = parsed deterministically from a dictionary-shaped table;
    # "free_form_llm" = extracted from prose/loose layout by the LLM.
    source_kind: str
    entries: list[DataDictionaryEntry] = []
    warnings: list[str] = []


class CohortMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: str
    age: float | None = None
    sex: str | None = None
    bmi: float | None = None
    engagement_group: str | None = None
    country: str | None = None


class CohortBiomarkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: str
    timepoint_months: int
    hba1c_pct: float | None = None
    ldl_mgdl: float | None = None
    hs_crp_mgl: float | None = None
    adherence_pct: float | None = None


class CohortSummary(BaseModel):
    cohort_name: str
    n_members: int


class CohortMemberIn(BaseModel):
    member_id: str
    age: float | None = None
    sex: str | None = None
    bmi: float | None = None
    engagement_group: str | None = None
    country: str | None = None


class CohortBiomarkerIn(BaseModel):
    member_id: str
    timepoint_months: int
    hba1c_pct: float | None = None
    ldl_mgdl: float | None = None
    hs_crp_mgl: float | None = None
    adherence_pct: float | None = None


class CohortImportRequest(BaseModel):
    """Ingestion of a longitudinal cohort (members + biomarkers). Replaces any
    existing cohort with the same name for the tenant. This is the write path that was
    missing for the cohort_members / cohort_biomarkers tables (read by
    OutcomeSelection/Simulation)."""

    cohort_name: str = Field(min_length=1, max_length=120)
    dataset_id: UUID | None = None
    members: list[CohortMemberIn] = Field(min_length=1)
    biomarkers: list[CohortBiomarkerIn] = []


class CohortImportResult(BaseModel):
    cohort_name: str
    members: int
    biomarkers: int


class DatasetExport(BaseModel):
    """GDPR Art 15/20 portability bundle — metadata only, no raw bytes.

    Contains the dataset record, its profiled columns, and file metadata. Raw
    CSV bytes are NOT included; callers must fetch individual file contents
    separately if needed.
    """

    dataset: DatasetOut
    columns: list[ColumnOut]
    files: list[DatasetFileOut]
