"""SQLAlchemy model of the generated documents module."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    study_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    type: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    # Bytes of the generated document (HTML), stored in the database — consistent
    # cross-container on Modal, unlike the ephemeral local disk. Served by GET
    # /documents/{id}/download.
    content: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
