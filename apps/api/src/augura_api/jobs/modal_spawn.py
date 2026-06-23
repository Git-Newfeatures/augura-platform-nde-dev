# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Confined, untyped Modal boundary.

The `modal` library stubs are partially typed (same rationale as at the top
of `modal_app.py`). We isolate here the single call concerned — `spawn` of the
`run_job` worker — to keep the rest of `jobs/` in strict pyright without compromise.
"""

from __future__ import annotations


def spawn_run_job(tenant_id: str, user_id: str, job_id: str) -> None:
    """Launches the Modal jobs worker (`run_job`) in a dedicated container."""
    import modal

    run_job = modal.Function.from_name("augura-api", "run_job")
    run_job.spawn(tenant_id, user_id, job_id)
