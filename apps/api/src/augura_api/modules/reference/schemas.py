"""Schémas Pydantic — contrat public du module reference."""

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
    sort_order: int


class StudyDesignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_name: str | None = None
    sort_order: int
