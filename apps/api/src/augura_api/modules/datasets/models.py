"""Modèles SQLAlchemy du module datasets (+ cohortes)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    study_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, server_default=text("'uploaded'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE")
    )
    sheet: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    value_kind: Mapped[str | None] = mapped_column(Text)
    n_total: Mapped[int | None] = mapped_column(Integer)
    n_non_null: Mapped[int | None] = mapped_column(Integer)
    null_pct: Mapped[float | None] = mapped_column(Numeric)
    n_distinct: Mapped[int | None] = mapped_column(Integer)
    value_min: Mapped[float | None] = mapped_column("min", Numeric)
    value_max: Mapped[float | None] = mapped_column("max", Numeric)
    top_values: Mapped[list[Any] | None] = mapped_column(JSONB)
    proposed_role: Mapped[str | None] = mapped_column(Text)
    proposed_group: Mapped[str | None] = mapped_column(Text)
    proposed_canonical_id: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric)
    rationale: Mapped[str | None] = mapped_column(Text)
    user_decision: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    final_role: Mapped[str | None] = mapped_column(Text)
    final_canonical_id: Mapped[str | None] = mapped_column(Text)


class CohortMember(Base):
    __tablename__ = "cohort_members"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    dataset_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    cohort_name: Mapped[str] = mapped_column(Text)
    member_id: Mapped[str] = mapped_column(Text)
    age: Mapped[float | None] = mapped_column(Numeric)
    sex: Mapped[str | None] = mapped_column(Text)
    bmi: Mapped[float | None] = mapped_column(Numeric)
    engagement_group: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)


class CohortBiomarker(Base):
    __tablename__ = "cohort_biomarkers"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    dataset_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    cohort_name: Mapped[str] = mapped_column(Text)
    member_id: Mapped[str] = mapped_column(Text)
    timepoint_months: Mapped[int] = mapped_column(Integer)
    hba1c_pct: Mapped[float | None] = mapped_column(Numeric)
    ldl_mgdl: Mapped[float | None] = mapped_column(Numeric)
    hs_crp_mgl: Mapped[float | None] = mapped_column(Numeric)
    adherence_pct: Mapped[float | None] = mapped_column(Numeric)
