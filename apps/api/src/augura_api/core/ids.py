"""Identifiants typés (spec §9) — empêchent de confondre un StudyId et un TenantId."""

from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
StudyId = NewType("StudyId", UUID)
JobId = NewType("JobId", UUID)
