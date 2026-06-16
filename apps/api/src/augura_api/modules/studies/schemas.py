"""Schémas Pydantic — le contrat public du module (frontières inter-modules)."""

from datetime import datetime
from typing import Any
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


class StudyStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    state: dict[str, Any]
    created_at: datetime


class StudyStatePut(BaseModel):
    state: dict[str, Any]
