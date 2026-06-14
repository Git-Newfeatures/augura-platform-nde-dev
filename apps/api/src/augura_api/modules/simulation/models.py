"""Modèles SQLAlchemy du module simulation."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class SimulationResult(Base):
    """Read-model précalculé (mode VALIDATED du front)."""

    __tablename__ = "simulation_results"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    cohort_name: Mapped[str] = mapped_column(Text)
    scenario: Mapped[str] = mapped_column(Text)
    estimator: Mapped[str] = mapped_column(Text)
    effect_size: Mapped[float | None] = mapped_column(Numeric)
    ci_lower: Mapped[float | None] = mapped_column(Numeric)
    ci_upper: Mapped[float | None] = mapped_column(Numeric)
    power: Mapped[float | None] = mapped_column(Numeric)
    p_value: Mapped[float | None] = mapped_column(Numeric)


class SimulationRun(Base):
    """Run de bootstrap à la demande (lié à un job)."""

    __tablename__ = "simulation_runs"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    study_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
