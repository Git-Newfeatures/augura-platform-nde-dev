"""Contrat public du module documents."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GeneratedDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID | None = None
    type: str
    storage_path: str | None = None
    status: str
    created_at: datetime


class GenerateRequest(BaseModel):
    study_id: UUID | None = None
    type: Literal["protocol", "report"]
    idempotency_key: str | None = None


class GeneratedDocumentCreated(BaseModel):
    document_id: UUID
    job_id: UUID
    status: str
