"""Interface publique du module jobs (consommée par simulation, documents, et le
routeur HTTP du module). La logique vit dans `service.py` ; ici on ré-expose."""

from augura_api.modules.jobs.router import router
from augura_api.modules.jobs.service import create_job, get_job

__all__ = ["router", "create_job", "get_job"]
