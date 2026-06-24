"""Public contract of the analytics module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RecentEvent(BaseModel):
    user_id: UUID | None = None
    event_type: str
    route: str | None = None
    created_at: datetime


class AdminStats(BaseModel):
    window_days: int
    total_events: int
    unique_users: int
    by_type: dict[str, int]
    recent: list[RecentEvent]


class ActivityEvent(BaseModel):
    """Activity-feed item (audit trail), accessible to any tenant member."""

    id: UUID
    event_type: str
    route: str | None = None
    created_at: datetime
    metadata: dict[str, object] | None = None


class LoginEventIn(BaseModel):
    """Client payload for a login telemetry event. Identity is NEVER taken from
    here — user_id/org_id come from the authenticated context server-side. Extra
    fields are rejected (extra='forbid') so a client cannot even attempt to smuggle
    a user_id/event_type into the audit trail."""

    model_config = ConfigDict(extra="forbid")

    route: str | None = None


class ArtifactOut(BaseModel):
    """Versioned & hashed artifact (reproducibility backbone) — feeds the
    Lineage tab. `content` is intentionally excluded (can be large)."""

    id: UUID
    kind: str
    version: int
    sha256: str
    study_id: UUID | None = None
    storage_ref: str | None = None
    provenance: dict[str, object] | None = None
    locked: bool = False
    created_at: datetime
