# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Frontière Modal non-typée, confinée.

Les stubs de la lib `modal` sont partiellement typés (même justification qu'en
tête de `modal_app.py`). On isole ici le seul appel concerné — `spawn` du worker
`run_job` — pour garder le reste de `jobs/` en pyright strict sans concession.
"""

from __future__ import annotations


def spawn_run_job(tenant_id: str, user_id: str, job_id: str) -> None:
    """Lance le worker de jobs Modal (`run_job`) dans un conteneur dédié."""
    import modal

    run_job = modal.Function.from_name("augura-api", "run_job")
    run_job.spawn(tenant_id, user_id, job_id)
