"""Job handlers: the actual work executed by the runner, by job type.

Orchestration layer (like `modules.agents`): this is the ONLY place that crosses
several data modules (simulation, documents, studies, corpus) + the
analytics/provenance spine. Each handler persists its result, emits a provenance event
(`create_artifact` → outbox_events) and logs usage (`log_usage`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from augura_api.core.ids import StudyId
from augura_api.modules import analytics
from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.documents.render import render_document_html
from augura_api.modules.documents.repo import DocumentRepo
from augura_api.modules.simulation.bootstrap import compute_bootstrap
from augura_api.modules.simulation.repo import SimulationRepo
from augura_api.modules.studies.repo import StudyRepo

if TYPE_CHECKING:
    from augura_api.jobs.runner import JobContext, JobHandler

from augura_api.core import storage

log = structlog.get_logger(__name__)


async def handle_bootstrap(ctx: JobContext) -> str | None:
    """Monte-Carlo bootstrap: computes, finalizes the run, projects the
    simulation_results read-model, archives the artifact + provenance, logs usage."""
    from augura_api.jobs.runner import run_in_thread

    repo = SimulationRepo(ctx.session)
    run = await repo.get_run_by_job(ctx.tenant_id, ctx.job.id)
    params = dict(ctx.job.payload or {})

    result = await run_in_thread(lambda: compute_bootstrap(params))
    cohort_name = result["cohort_name"]
    rows = result["rows"]

    if run is not None:
        await repo.finalize_run(ctx.tenant_id, run.id, status="succeeded", results=result)
    await repo.replace_results(ctx.tenant_id, cohort_name, rows)

    await analytics.create_artifact(
        ctx.session,
        tenant_id=ctx.tenant_id,
        kind="simulation_run",
        content=result,
        study_id=StudyId(run.study_id) if run is not None and run.study_id else None,
        provenance={"job_id": str(ctx.job.id), "params": params},
        created_by=ctx.user_id,
    )
    await analytics.log_usage(
        ctx.session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        event_type="simulation.bootstrap.succeeded",
        route="/simulations",
        metadata={"cohort_name": cohort_name, "n_rows": len(rows)},
    )
    return f"run:{run.id}" if run is not None else None


async def handle_document(ctx: JobContext) -> str | None:
    """Generates the document (print-friendly HTML), stores it, marks the document `ready`,
    archives the artifact + provenance, logs usage."""
    payload = dict(ctx.job.payload or {})
    document_id = UUID(str(payload["document_id"]))
    study_id_raw = payload.get("study_id")
    doc_type = ctx.job.type.replace("generate_", "")  # generate_protocol -> protocol

    study_dict = None
    state_dict = None
    if study_id_raw:
        sid = StudyId(UUID(str(study_id_raw)))
        study_repo = StudyRepo(ctx.session)
        study = await study_repo.get(ctx.tenant_id, sid)
        if study is not None:
            study_dict = {
                "name": study.name,
                "framework": study.framework,
                "category": study.category,
                "status": study.status,
                "lead": study.lead,
                "n_subjects": study.n_subjects,
                "tagline": study.tagline,
            }
            latest = await study_repo.latest_state(ctx.tenant_id, sid)
            state_dict = latest.state if latest is not None else None

    sim_rows = await SimulationRepo(ctx.session).list_results(ctx.tenant_id, None)
    results = [
        {
            "cohort_name": r.cohort_name,
            "scenario": r.scenario,
            "estimator": r.estimator,
            "effect_size": float(r.effect_size) if r.effect_size is not None else None,
            "ci_lower": float(r.ci_lower) if r.ci_lower is not None else None,
            "ci_upper": float(r.ci_upper) if r.ci_upper is not None else None,
            "power": float(r.power) if r.power is not None else None,
            "p_value": float(r.p_value) if r.p_value is not None else None,
        }
        for r in sim_rows
    ]
    source_counts = await CorpusRepo(ctx.session).source_counts()
    sources = [{"source_id": s, "count": c} for s, c in source_counts]

    html = render_document_html(
        doc_type=doc_type,
        study=study_dict,
        state=state_dict,
        results=results,
        sources=sources,
        generated_at=datetime.now(UTC),
    )
    # Bytes stored IN THE DATABASE (generated_documents.content), not on the container's
    # local disk: on Modal the `run_job` worker and the ASGI app are distinct containers with
    # an ephemeral FS, so a disk file would be unreachable on download (404). `storage_path`
    # remains a stable logical identifier (provenance), decoupled from the disk.
    data = html.encode("utf-8")
    ref = storage.build_ref(str(ctx.tenant_id), f"{document_id}.html")
    await DocumentRepo(ctx.session).set_status(
        ctx.tenant_id, document_id, status="ready", storage_path=ref, content=data
    )
    await analytics.create_artifact(
        ctx.session,
        tenant_id=ctx.tenant_id,
        kind="document",
        content=None,
        study_id=StudyId(UUID(str(study_id_raw))) if study_id_raw else None,
        provenance={"document_id": str(document_id), "type": doc_type, "job_id": str(ctx.job.id)},
        created_by=ctx.user_id,
        storage_ref=ref,
    )
    await analytics.log_usage(
        ctx.session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        event_type="document.generated",
        route="/documents",
        metadata={"document_id": str(document_id), "type": doc_type},
    )
    return ref


async def handle_enrich_propose(ctx: JobContext) -> str | None:
    """Enrichment proposal pipeline (B4): reads the bundle, runs the LLM
    batches, persists the proposal batch IN THE DATABASE (jobs.result_json). The
    result is NOT written to disk: on Modal the FS is ephemeral and container-local,
    so a file artifact would not be readable back by the ASGI container."""
    from augura_api.core.db import get_sessionmaker, set_tenant_stmt, set_user_stmt
    from augura_api.core.llm.runtime import get_anthropic_client
    from augura_api.modules import jobs as jobs_iface
    from augura_api.modules.semantic.enrich_propose import propose
    from augura_api.modules.semantic.repo import SemanticRepo

    payload = dict(ctx.job.payload or {})
    bundle = await SemanticRepo(ctx.session).read_bundle()
    client = get_anthropic_client(ctx.settings)

    last_pct = -1

    async def on_progress(frac: float, _message: str) -> None:
        # The runner's work transaction only commits at the end: progress written on it
        # would stay invisible to polling. We commit it in a DEDICATED short
        # transaction (throttled per percentage point) so it surfaces.
        # Best-effort: progress must never make the job itself fail.
        nonlocal last_pct
        pct = round(max(0.0, min(1.0, frac)) * 100)
        if pct == last_pct and frac < 1.0:
            return
        last_pct = pct
        try:
            async with get_sessionmaker(ctx.settings)() as s, s.begin():
                await s.execute(set_user_stmt(ctx.user_id))
                await s.execute(set_tenant_stmt(ctx.tenant_id))
                await jobs_iface.set_progress(s, ctx.tenant_id, ctx.job.id, frac)
        except Exception:  # noqa: BLE001 — best-effort progress
            log.warning("enrich.progress.skipped", job_id=str(ctx.job.id), frac=frac)

    result = await propose(
        client=client,
        # North Star Phase 2.1: a larger, more capable model (Opus) proposes the taxonomy
        # concepts + relations that fill the question's unresolved gaps.
        model=ctx.settings.agent_model_deep,
        bundle=bundle,
        questions=payload.get("questions"),
        selected_concepts=payload.get("selected_concepts"),
        on_progress=on_progress,
    )
    result["generated_at"] = datetime.now(UTC).isoformat()
    await jobs_iface.set_result_json(ctx.session, ctx.tenant_id, ctx.job.id, result)
    await analytics.log_usage(
        ctx.session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        event_type="semantic.enrich.proposed",
        route="/semantic/enrich/propose",
        metadata={"job_id": str(ctx.job.id), **result.get("summary", {})},
    )
    return None


def build_handlers() -> dict[str, JobHandler]:
    return {
        "bootstrap": handle_bootstrap,
        "generate_protocol": handle_document,
        "generate_report": handle_document,
        "enrich_propose": handle_enrich_propose,
    }
