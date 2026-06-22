"""Interface publique du module jobs (consommée par simulation, documents, et le
routeur HTTP du module). La logique vit dans `service.py` ; ici on ré-expose."""

from augura_api.modules.jobs.router import router
from augura_api.modules.jobs.service import (
    create_job,
    get_job,
    mark_failed,
    mark_running,
    mark_succeeded,
    set_progress,
    set_result_json,
)

__all__ = [
    "router",
    "create_job",
    "get_job",
    "mark_running",
    "set_progress",
    "mark_succeeded",
    "set_result_json",
    "mark_failed",
]
