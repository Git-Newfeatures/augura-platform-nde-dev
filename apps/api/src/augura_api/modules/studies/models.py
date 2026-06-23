"""SQLAlchemy models for the studies module (never leave the module — spec §4).

The physical schema is created by the baseline migration (SQL bundle); these models
serve queries, not DDL.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    framework: Mapped[str | None] = mapped_column(Text)
    n_subjects: Mapped[int | None] = mapped_column(Integer)
    lead: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StudyState(Base):
    __tablename__ = "study_state"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StudyMember(Base):
    __tablename__ = "study_members"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    role: Mapped[str] = mapped_column(Text, server_default=text("'member'"))
