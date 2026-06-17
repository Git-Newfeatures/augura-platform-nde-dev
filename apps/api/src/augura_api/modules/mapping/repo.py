"""Accès base du module mapping — met à jour les propositions sur dataset_columns."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.datasets.models import DatasetColumn


class MappingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def update_proposal(
        self,
        column_id: UUID,
        *,
        proposed_canonical_id: str | None,
        proposed_role: str | None,
        confidence: float | None,
    ) -> None:
        await self.session.execute(
            update(DatasetColumn)
            .where(DatasetColumn.id == column_id)
            .values(
                proposed_canonical_id=proposed_canonical_id,
                proposed_role=proposed_role,
                confidence=confidence,
            )
        )
