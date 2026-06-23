"""SQLAlchemy model for the dq module."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class DqBundle(Base):
    __tablename__ = "dq_bundles"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    dataset_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    score_profile: Mapped[str] = mapped_column(Text, server_default=text("'exploratory'"))
    overall_score: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    requires_resolution: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bundle: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
