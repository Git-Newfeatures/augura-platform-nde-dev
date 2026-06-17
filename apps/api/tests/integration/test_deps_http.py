"""Garde anti-régression HTTP de la chaîne de dépendances complète, sur vrai Postgres.

Sauté si AUGURA_DATABASE_URL est absent. On neutralise seulement la vérification JWT
(`get_principal`) pour injecter un utilisateur ; tout le reste — résolution
`memberships`, session RLS-scopée, repo — tourne pour de vrai. C'est exactement le
chemin qui rendait 500 quand la requête d'appartenance ne compilait pas. La base
n'est plus seedée : on vérifie que la chaîne répond 200 (liste vide acceptée), pas
un contenu de démonstration précis.
"""

import os
from uuid import UUID

import httpx
import pytest

from augura_api.core.auth import Principal
from augura_api.core.deps import get_principal
from augura_api.core.ids import UserId
from augura_api.main import create_app

pytestmark = pytest.mark.integration

TEST_USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


async def test_authenticated_studies_runs_full_deps_chain() -> None:
    if not os.environ.get("AUGURA_DATABASE_URL"):
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")

    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=TEST_USER, email="test@augura.test", claims={}
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/studies")

    # 500 = régression de la chaîne de deps. Le corps peut être une liste vide.
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
