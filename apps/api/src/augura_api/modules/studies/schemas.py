"""Pydantic schemas — the module's public contract (inter-module boundaries)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    tagline: str | None = None
    category: str | None = None
    framework: str | None = None
    n_subjects: int | None = None
    lead: str | None = None
    status: str
    created_at: datetime


class StudyCreate(BaseModel):
    name: str
    slug: str
    tagline: str | None = None
    category: str | None = None
    framework: str | None = None
    n_subjects: int | None = None


class StudyUpdate(BaseModel):
    """Partial update of a study (lifecycle + metadata).
    Only explicitly provided fields are written (model_dump exclude_unset)."""

    name: str | None = None
    tagline: str | None = None
    category: str | None = None
    framework: str | None = None
    lead: str | None = None
    n_subjects: int | None = None
    status: Literal["draft", "active", "locked", "archived"] | None = None


class StudyStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    state: dict[str, Any]
    created_at: datetime


class StudyStatePut(BaseModel):
    state: dict[str, Any]
