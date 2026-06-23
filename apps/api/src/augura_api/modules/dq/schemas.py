"""Public contract for the dq module."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DqBundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    score_profile: str
    overall_score: float | None = None
    status: str
    requires_resolution: bool
    bundle: dict[str, Any]
    created_at: datetime


class DqRunResult(BaseModel):
    bundle_id: UUID
    status: str
    overall_score: float | None = None
