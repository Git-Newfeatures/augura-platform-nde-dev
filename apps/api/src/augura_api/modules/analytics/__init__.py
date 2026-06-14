"""Interface publique du module analytics (logging consommé par les autres modules)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import StudyId, TenantId, UserId
from augura_api.modules.analytics.models import AgentRun, UsageEvent
from augura_api.modules.analytics.router import router


async def log_usage(
    session: AsyncSession,
    *,
    tenant_id: TenantId,
    user_id: UserId | None,
    event_type: str,
    route: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        UsageEvent(
            org_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            route=route,
            metadata_=metadata,
        )
    )
    await session.flush()


async def log_agent_run(
    session: AsyncSession,
    *,
    tenant_id: TenantId,
    agent_type: str,
    model: str,
    status: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int | None = None,
    study_id: StudyId | None = None,
) -> UUID:
    run = AgentRun(
        org_id=tenant_id,
        study_id=study_id,
        agent_type=agent_type,
        model=model,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run.id


__all__ = ["router", "log_usage", "log_agent_run"]
