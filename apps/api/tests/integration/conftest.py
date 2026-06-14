"""Garde : les tests d'intégration ne doivent JAMAIS viser le projet Supabase de démo.

Les fixtures committent (elles ouvrent `session.begin()`), donc lancer la suite contre
la base de démo y laisse des lignes (étude « Integration », datasets de test, jobs…).
En CI ils tournent contre un Postgres éphémère ; en local, pointer AUGURA_DATABASE_URL
vers une branche Supabase jetable. Si l'URL contient le ref du projet démo, on échoue
franchement AVANT d'écrire quoi que ce soit.
"""

import os

import pytest

# Projet Supabase de démo/connecté (à ne pas polluer). Étendre si besoin.
_FORBIDDEN_PROJECT_REFS = ("fqmoylmvjoafihiuiiuj",)


@pytest.fixture(autouse=True)
def _forbid_demo_db() -> None:
    url = os.environ.get("AUGURA_DATABASE_URL", "")
    for ref in _FORBIDDEN_PROJECT_REFS:
        if ref in url:
            pytest.fail(
                f"Tests d'intégration pointés sur le projet Supabase de démo ({ref}) : "
                "ils committeraient des données. Utilise une branche Supabase jetable "
                "(ou laisse la CI utiliser son Postgres éphémère).",
                pytrace=False,
            )
