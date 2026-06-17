"""Modèles SQLAlchemy du module corpus. org_id NULL ⇒ document/chunk global."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    source_id: Mapped[str] = mapped_column(Text)
    evidence_type: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(Text)
    lifecycle: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date | None] = mapped_column(Date)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    priority_score: Mapped[float | None] = mapped_column(Numeric)
    is_new: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    org_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    token_count: Mapped[int | None] = mapped_column(Integer)


# ── Recherche live (retrieve-and-freeze) ──────────────────────────────────────
# Refs externes (org_id/study_id/created_by) = UUID nus, comme Document.org_id.


class LiteratureSnapshot(Base):
    __tablename__ = "literature_snapshots"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    study_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    # Artefact canonique exact qui a été haché (autorité du content_hash).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class SearchSession(Base):
    __tablename__ = "search_sessions"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    study_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    query: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class LiteratureEvent(Base):
    __tablename__ = "literature_events"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("search_sessions.id", ondelete="CASCADE")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class LiteratureQuery(Base):
    __tablename__ = "literature_queries"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    source: Mapped[str] = mapped_column(Text)
    query_string: Mapped[str] = mapped_column(Text)
    result: Mapped[Any] = mapped_column(JSONB)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
