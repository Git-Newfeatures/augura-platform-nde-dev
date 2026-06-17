"""Contrat public du module analytics."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
    """Élément du fil d'activité (audit trail), accessible à tout membre du tenant."""

    id: UUID
    event_type: str
    route: str | None = None
    created_at: datetime
    metadata: dict[str, object] | None = None
