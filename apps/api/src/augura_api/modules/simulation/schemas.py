"""Contrat public du module simulation."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PowerRequest(BaseModel):
    n: int | None = None
    dropout: float = 0.20
    effect: float = 0.30
    sigma: float | None = None
    outcome: str | None = None
    estimators: list[str] | None = None


class EstimatorPowerOut(BaseModel):
    estimator: str
    power: float
    bias: float
    variance: float
    mse: float
    effect: float
    ci_lower: float
    ci_upper: float


class PowerResponse(BaseModel):
    n: int
    dropout: float
    effect: float
    sigma: float
    power_threshold: float
    estimators: list[EstimatorPowerOut]


class SimulationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cohort_name: str
    scenario: str
    estimator: str
    effect_size: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    power: float | None = None
    p_value: float | None = None


class SimulationRequest(BaseModel):
    study_id: UUID | None = None
    params: dict[str, Any] = {}
    idempotency_key: str | None = None


class SimulationRunCreated(BaseModel):
    job_id: UUID
    run_id: UUID
    status: str
