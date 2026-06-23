"""Public interface of the analytics module (logging consumed by the other modules).

Includes the provenance/reproducibility backbone (spec §2): versioned & hashed
artifacts (`create_artifact`/`get_artifact`/`lock_artifact`) and the audit log
(`record_event` → outbox_events). Every write emits a provenance event.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.errors import ConflictError, NotFoundError
from augura_api.core.ids import StudyId, TenantId, UserId
from augura_api.core.provenance import content_hash
from augura_api.modules.analytics.models import AgentRun, Artifact, OutboxEvent, UsageEvent
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


# ── Provenance / artifacts (reproducibility backbone, spec §2) ─────


async def record_event(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: UUID | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Write an immutable audit event into outbox_events (user/ts via payload)."""
    session.add(
        OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload or {},
        )
    )
    await session.flush()


async def create_artifact(
    session: AsyncSession,
    *,
    tenant_id: TenantId,
    kind: str,
    content: Any,
    study_id: StudyId | None = None,
    version: int = 0,
    provenance: dict[str, Any] | None = None,
    created_by: UserId | None = None,
    locked: bool = False,
    storage_ref: str | None = None,
) -> Artifact:
    """Create a versioned + hashed artifact (SHA-256 of the canonical content) and emit
    the provenance event. content=None ⇒ hash the storage_ref (large external file)."""
    sha = content_hash(content if content is not None else {"storage_ref": storage_ref})
    artifact = Artifact(
        org_id=tenant_id,
        study_id=study_id,
        kind=kind,
        version=version,
        sha256=sha,
        content=content,
        storage_ref=storage_ref,
        provenance=provenance or {},
        locked=locked,
        created_by=created_by,
    )
    session.add(artifact)
    await session.flush()
    await session.refresh(artifact)
    await record_event(
        session,
        aggregate_type="artifact",
        aggregate_id=artifact.id,
        event_type="artifact.created",
        payload={
            "kind": kind,
            "version": version,
            "sha256": sha,
            "study_id": str(study_id) if study_id else None,
            "created_by": str(created_by) if created_by else None,
        },
    )
    return artifact


async def get_artifact(
    session: AsyncSession,
    *,
    tenant_id: TenantId,
    kind: str,
    study_id: StudyId | None = None,
    version: int | None = None,
) -> Artifact | None:
    """Fetch an artifact (given version, or the most recent if version=None)."""
    stmt = select(Artifact).where(Artifact.org_id == tenant_id, Artifact.kind == kind)
    if study_id is not None:
        stmt = stmt.where(Artifact.study_id == study_id)
    if version is not None:
        stmt = stmt.where(Artifact.version == version)
    else:
        stmt = stmt.order_by(Artifact.version.desc())
    res = await session.execute(stmt.limit(1))
    return res.scalar_one_or_none()


async def lock_artifact(
    session: AsyncSession,
    *,
    tenant_id: TenantId,
    artifact_id: UUID,
    locked_by: UserId | None = None,
) -> Artifact:
    """Lock an artifact (pre-specification lock) and emit the event. Idempotence is
    refused: an already-locked artifact raises ConflictError."""
    res = await session.execute(
        select(Artifact).where(Artifact.org_id == tenant_id, Artifact.id == artifact_id)
    )
    artifact = res.scalar_one_or_none()
    if artifact is None:
        raise NotFoundError("artifact not found", artifact_id=str(artifact_id))
    if artifact.locked:
        raise ConflictError("artifact already locked", artifact_id=str(artifact_id))
    artifact.locked = True
    await session.flush()
    await record_event(
        session,
        aggregate_type="artifact",
        aggregate_id=artifact.id,
        event_type="artifact.locked",
        payload={
            "kind": artifact.kind,
            "version": artifact.version,
            "sha256": artifact.sha256,
            "locked_by": str(locked_by) if locked_by else None,
        },
    )
    return artifact


__all__ = [
    "router",
    "log_usage",
    "log_agent_run",
    "record_event",
    "create_artifact",
    "get_artifact",
    "lock_artifact",
]
