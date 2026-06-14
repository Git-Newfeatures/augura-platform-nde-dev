"""Contrat public du module jobs."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    status: str
    progress: float
    result_ref: str | None = None
    error: str | None = None
