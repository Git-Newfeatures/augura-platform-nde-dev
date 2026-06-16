"""Vérifie la connexion backend → Supabase de bout en bout, via la vraie couche
de données (request_session pose app.tenant_id/app.user_id, RLS active sous augura_api).

Usage : AUGURA_* dans l'env (source apps/api/.env), puis `uv run python scripts/verify_supabase.py`.
"""

import asyncio
from uuid import UUID

from augura_api.core.config import Settings
from augura_api.core.db import request_session
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.corpus.repo import CorpusFilters, CorpusRepo
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.simulation.repo import SimulationRepo
from augura_api.modules.studies.repo import StudyRepo

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


async def main() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue] -- AUGURA_* via env
    async for session in request_session(settings, LUCIS, USER):
        studies = await StudyRepo(session).list_for_tenant(LUCIS)
        docs, total_docs = await CorpusRepo(session).feed(CorpusFilters(), limit=50, offset=0)
        members = await DatasetRepo(session).cohort_members(LUCIS, "validation_v1")
        sims = await SimulationRepo(session).list_results(LUCIS, "validation_v1")
        print("✓ Connexion Supabase OK (rôle augura_api, RLS active via app.tenant_id)")
        print(f"  studies          : {[s.slug for s in studies]}")
        print(f"  corpus documents : {total_docs} (échantillon {len(docs)})")
        print(f"  cohort_members   : {len(members)}")
        print(f"  simulation_results: {len(sims)}")


if __name__ == "__main__":
    asyncio.run(main())
