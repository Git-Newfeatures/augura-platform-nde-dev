"""Pydantic schemas — public contract for the reference module."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    cesl_profile: dict[str, Any]


class CeslSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    doc_type: str | None = None
    description: str | None = None
    base_url: str | None = None
    result_unit: str | None = None
    default_evidence_type: str | None = None
    sort_order: int


class StudyDesignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_name: str | None = None
    description: str | None = None
    tags: list[Any] = []
    estimands: list[str] = []
    sort_order: int


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_key: str
    label: str
    unit: str | None = None
    is_primary: bool = False
    description: str | None = None
    regulatory_tags: list[Any] = []
    verdict: str | None = None
    verdict_label: str | None = None
    sort_order: int


class EstimandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str | None = None
    regulatory: str | None = None
    recommended: bool = False
    tag: str | None = None
    sort_order: int


class EstimatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    short: str
    recommended: bool = False
    bootstrap_pending: bool = False
    interpretability: int = 0
    stability: bool = True
    tooltip: str | None = None
    eligible_study_types: list[str] = []
    sort_order: int


class FrameworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    sort_order: int


class CodeLabelOut(BaseModel):
    """Shared shape for evidence-types, domains, jurisdictions, literature designs."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    description: str | None = None
    sort_order: int


class PiiPatternOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    pattern: str


class BiomarkerRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    pattern: str
    value_min: float | None = None
    value_max: float | None = None
    unit: str | None = None


class DqRulesOut(BaseModel):
    pii_patterns: list[PiiPatternOut]
    biomarker_ranges: list[BiomarkerRangeOut]


class VariableGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str | None = None
    description: str | None = None


class VariableRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_code: str | None = None
    selectable: bool = True


class VariableRolesOut(BaseModel):
    groups: list[VariableGroupOut]
    roles: list[VariableRoleOut]
    group_aliases: dict[str, str]
