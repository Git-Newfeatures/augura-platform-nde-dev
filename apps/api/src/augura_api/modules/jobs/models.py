"""Modèle SQLAlchemy de la table jobs (infra de suivi des traitements longs)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    progress: Mapped[float] = mapped_column(Numeric, server_default=text("0"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    result_ref: Mapped[str | None] = mapped_column(Text)
    # Résultat structuré du job stocké EN BASE (et non sur disque) : indispensable sur
    # Modal où le système de fichiers est éphémère et propre à chaque conteneur — un
    # artefact écrit par le worker ne serait pas relisible par le conteneur ASGI.
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    modal_call_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
