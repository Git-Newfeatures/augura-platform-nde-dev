"""Typed identifiers (spec §9) — prevent confusing a StudyId with a TenantId."""

from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
StudyId = NewType("StudyId", UUID)
JobId = NewType("JobId", UUID)
