# Port B4 — Enrichissement sémantique « à la volée » — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer la boucle d'enrichissement de la couche sémantique gouvernée — persister les concepts/relations proposés (par le DAG ou par un pipeline LLM dédié) dans l'ontologie globale, avec versioning et garde-fou de revue.

**Architecture:** Port fidèle de `Augura-Health/augura@98c1023` (`api/enrich-propose.js`, `api/enrich-apply.js`, `src/semantic/governed-vocab.js`, `LearnFromQuestionPanel.jsx`, fonction SQL `upsert_semantic_release`) vers la tranche verticale `modules/semantic/` de la plateforme. Écriture sur l'ontologie **globale** (`public`) via une fonction SQL `SECURITY DEFINER` ; **apply** synchrone gated `owner` ; **propose** exécuté comme job background. 3 phases livrables indépendamment.

**Tech Stack:** FastAPI · SQLAlchemy async · asyncpg · Pydantic · Postgres/pgvector (Supabase) · Anthropic (LLM) · React 19/Vite (front) · `uv`/`pytest`/`ruff`/`pyright` (backend) · `npm`/`eslint` (front).

**Spec de référence :** [docs/superpowers/specs/2026-06-19-b4-semantic-enrichment-port-design.md](../specs/2026-06-19-b4-semantic-enrichment-port-design.md)

**Source du port (working copy locale) :** `/Users/quentin/Desktop/Augure/lucis-dashboard` (branche `data-intake-nde`, commit `98c1023`).

**Conventions à respecter (CLAUDE.md) :** commentaires/docstrings **en français** ; `ruff` ligne 100 ; `pyright` strict ; `lint-imports` (`causal → semantic` autorisé, `core` n'importe jamais `modules`) ; migrations **0002+ idempotentes** ; **pas de mock/fallback** côté `apps/web` ; ne **jamais** éditer `packages/api-client/src/schema.d.ts` à la main. Ne **rien** committer/pousser/déployer sans demande explicite — ce plan crée des commits locaux par tâche ; la bascule DB live et le déploiement Modal restent des actions manuelles séparées.

**Commandes de vérification (depuis `apps/api`, env chargé `set -a; . ./.env; set +a`) :**
- `uv run ruff format --check . && uv run ruff check .`
- `uv run pyright`
- `uv run lint-imports`
- `uv run pytest -q` (les tests `@pytest.mark.integration` exigent `AUGURA_DATABASE_URL`)
- Régénération contrat : `uv run python scripts/dump_openapi.py` puis `npm --prefix ../../packages/api-client run generate`

---

## File Structure (decomposition)

**Backend — Phase 1 (write-path / apply) :**
- `apps/api/supabase/functions.sql` *(modify)* — ajoute la fonction `upsert_semantic_release`.
- `apps/api/alembic/versions/0006_semantic_enrich_function.py` *(create)* — migration idempotente (CREATE OR REPLACE).
- `apps/api/src/augura_api/modules/semantic/repo.py` *(modify)* — ajoute `apply_release()` (seule méthode d'écriture).
- `apps/api/src/augura_api/modules/semantic/enrich_schemas.py` *(create)* — schémas Pydantic des routes enrich (apply + propose).
- `apps/api/src/augura_api/modules/semantic/enrich_apply.py` *(create)* — logique des 4 chemins d'apply (construit manifest+payload).
- `apps/api/src/augura_api/modules/semantic/router.py` *(modify)* — route `POST /semantic/enrich/apply` gated owner.
- `apps/api/tests/semantic/test_enrich_apply.py` *(create)* — unitaires apply.
- `apps/api/tests/semantic/test_upsert_semantic_release.py` *(create)* — intégration SQL.

**Backend — Phase 2 (propose pipeline) :**
- `apps/api/src/augura_api/modules/semantic/vocab.py` *(create)* — enums gouvernés.
- `apps/api/src/augura_api/modules/causal/prompt.py` + `schemas.py` *(modify)* — consomment `vocab.POLARITY` (fix drift).
- `apps/api/src/augura_api/modules/semantic/enrichment.py` *(create)* — logique pure (coverage, BFS, prechecks, reassign, stamp).
- `apps/api/src/augura_api/modules/semantic/enrich_propose.py` *(create)* — orchestration des batchs LLM.
- `apps/api/src/augura_api/jobs/handlers.py` *(modify)* — `handle_enrich_propose` + enregistrement du kind.
- `apps/api/src/augura_api/modules/semantic/router.py` *(modify)* — `POST /semantic/enrich/propose` + `GET /semantic/enrich/proposals/{job_id}`.
- `apps/api/tests/semantic/test_enrichment.py` *(create)* — unitaires logique pure.
- `apps/api/tests/semantic/test_enrich_propose_handler.py` *(create)* — job à LLM mocké.

**Frontend — Phase 3 :**
- `apps/web/src/workspace/dataClient.js` *(modify)* — wrappers `enrichPropose`/`pollJob`/`fetchEnrichProposals`/`enrichApply`.
- `apps/web/src/workspace/EnrichmentPanel.jsx` *(create)* — port de `LearnFromQuestionPanel`.
- `apps/web/src/workspace/SemanticLayerPage.jsx` *(modify)* — monte le panneau.
- `apps/web/src/workspace/CausalModelingPage.jsx` *(modify)* — bouton « accepter l'arête » + `resetSemanticStore()`.

---

# PHASE 1 — Write-path (apply)

Livrable : on peut accepter une relation proposée par le DAG et la voir persistée dans l'ontologie (bump de version). Indépendamment testable.

## Task 1: Fonction SQL `upsert_semantic_release`

**Files:**
- Modify: `apps/api/supabase/functions.sql` (append en fin de fichier)
- Create: `apps/api/alembic/versions/0006_semantic_enrich_function.py`

- [ ] **Step 1: Écrire la fonction dans `functions.sql`**

Ajouter à la fin de `apps/api/supabase/functions.sql`. **Cible `public`** (la plateforme n'a pas de schéma `semantic`). Colonnes vérifiées contre `schema.sql:500-697` — note : `taxonomy_standard_codes` n'a **pas** de `review_status`.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- upsert_semantic_release : applique un batch d'enrichissement (B4) à la couche
-- sémantique gouvernée et bascule la release courante. SECURITY DEFINER : le rôle
-- applicatif (RLS FOR SELECT seulement) écrit EXCLUSIVEMENT via cette fonction.
-- Idempotent (CREATE OR REPLACE + upserts par clé).
-- ─────────────────────────────────────────────────────────────────────────
create or replace function public.upsert_semantic_release(
  p_manifest jsonb,
  p_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_version text := p_manifest->>'semantic_release_version';
begin
  if coalesce(v_version, '') = '' then
    raise exception 'semantic_release_version requis dans le manifest';
  end if;

  -- Concepts d'abord (cible FK des relations / synonyms / codes).
  insert into public.taxonomy_concepts
    select * from jsonb_populate_recordset(
      null::public.taxonomy_concepts,
      coalesce(p_payload->'taxonomy_concepts', '[]'::jsonb))
    on conflict (local_concept_id) do update set
      layer = excluded.layer,
      concept_name = excluded.concept_name,
      augura_domain = excluded.augura_domain,
      value_type = excluded.value_type,
      canonical_unit = excluded.canonical_unit,
      design_rationale = excluded.design_rationale,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

  insert into public.taxonomy_synonyms
    select * from jsonb_populate_recordset(
      null::public.taxonomy_synonyms,
      coalesce(p_payload->'taxonomy_synonyms', '[]'::jsonb))
    on conflict (local_concept_id, synonym) do update set
      synonym_type = excluded.synonym_type,
      source = excluded.source,
      review_status = excluded.review_status;

  insert into public.taxonomy_standard_codes
    select * from jsonb_populate_recordset(
      null::public.taxonomy_standard_codes,
      coalesce(p_payload->'taxonomy_standard_codes', '[]'::jsonb))
    on conflict (local_concept_id, vocabulary_id, concept_code) do update set
      standard_concept_id = excluded.standard_concept_id,
      standard_concept_name = excluded.standard_concept_name,
      standard_concept_flag = excluded.standard_concept_flag,
      concept_class_id = excluded.concept_class_id;

  insert into public.ontology_relations
    select * from jsonb_populate_recordset(
      null::public.ontology_relations,
      coalesce(p_payload->'ontology_relations', '[]'::jsonb))
    on conflict (relation_id) do update set
      subject_concept_id = excluded.subject_concept_id,
      predicate = excluded.predicate,
      object_concept_id = excluded.object_concept_id,
      polarity = excluded.polarity,
      default_strength = excluded.default_strength,
      default_temporal_lag = excluded.default_temporal_lag,
      mechanism_summary = excluded.mechanism_summary,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

  insert into public.ontology_relation_evidence
    select * from jsonb_populate_recordset(
      null::public.ontology_relation_evidence,
      coalesce(p_payload->'ontology_relation_evidence', '[]'::jsonb))
    on conflict (evidence_id) do update set
      relation_id = excluded.relation_id,
      source_type = excluded.source_type,
      citation_or_url = excluded.citation_or_url,
      evidence_summary = excluded.evidence_summary,
      population_notes = excluded.population_notes,
      evidence_strength = excluded.evidence_strength,
      review_status = excluded.review_status;

  insert into public.ontology_relation_qualifiers
    select * from jsonb_populate_recordset(
      null::public.ontology_relation_qualifiers,
      coalesce(p_payload->'ontology_relation_qualifiers', '[]'::jsonb))
    on conflict (qualifier_id) do update set
      relation_id = excluded.relation_id,
      qualifier_type = excluded.qualifier_type,
      qualifier_concept_id = excluded.qualifier_concept_id,
      qualifier_value = excluded.qualifier_value,
      qualifier_effect = excluded.qualifier_effect,
      is_hard_constraint = excluded.is_hard_constraint,
      notes = excluded.notes;

  -- Bascule la release courante (append-only, une seule is_current).
  update public.semantic_releases set is_current = false where is_current;
  insert into public.semantic_releases (
    semantic_release_version, taxonomy_version, causal_ontology_version,
    dq_ontology_version, omop_cdm_version, source, manifest, is_current
  ) values (
    v_version,
    coalesce(p_manifest->>'taxonomy_version', v_version),
    coalesce(p_manifest->>'causal_ontology_version', v_version),
    coalesce(p_manifest->>'dq_ontology_version', v_version),
    p_manifest->>'omop_cdm_version',
    coalesce(p_manifest->>'description', p_manifest->>'source'),
    p_manifest,
    true
  )
  on conflict (semantic_release_version) do update set
    manifest = excluded.manifest, is_current = true;

  return jsonb_build_object(
    'version', v_version,
    'concepts', jsonb_array_length(coalesce(p_payload->'taxonomy_concepts', '[]'::jsonb)),
    'relations', jsonb_array_length(coalesce(p_payload->'ontology_relations', '[]'::jsonb))
  );
end;
$$;

revoke all on function public.upsert_semantic_release(jsonb, jsonb) from public;
-- Grant conditionnel : le rôle applicatif n'existe pas sur le Postgres de CI (db-bundle).
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_api') then
    execute 'grant execute on function public.upsert_semantic_release(jsonb, jsonb) to augura_api';
  end if;
end $$;
```

- [ ] **Step 2: Créer la migration alembic 0006**

`apps/api/alembic/versions/0006_semantic_enrich_function.py` — copier le bloc SQL ci-dessus dans un `op.execute(...)`. `CREATE OR REPLACE FUNCTION` + grant conditionnel = idempotent.

```python
"""upsert_semantic_release : write-path d'enrichissement de la couche sémantique (B4)

Fonction SECURITY DEFINER : le rôle applicatif (RLS FOR SELECT) écrit l'ontologie
globale EXCLUSIVEMENT via elle. Idempotente (CREATE OR REPLACE + grant conditionnel),
vit aussi dans le bundle canonique functions.sql exécuté par 0001_baseline.

Revision ID: 0006_semantic_enrich_function
Revises: 0005_semantic_release
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_semantic_enrich_function"
down_revision: str | None = "0005_semantic_release"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_SQL = r"""
<<COLLER ICI le bloc SQL complet du Step 1, de "create or replace function" jusqu'au "end $$;" final>>
"""


def upgrade() -> None:
    op.execute(_FUNCTION_SQL)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.upsert_semantic_release(jsonb, jsonb);")
```

- [ ] **Step 3: Vérifier le format/lint**

Run: `cd apps/api && uv run ruff format --check alembic/versions/0006_semantic_enrich_function.py && uv run ruff check alembic/versions/0006_semantic_enrich_function.py`
Expected: PASS (aucune erreur).

- [ ] **Step 4: Commit**

```bash
git add apps/api/supabase/functions.sql apps/api/alembic/versions/0006_semantic_enrich_function.py
git commit -m "feat(semantic): upsert_semantic_release write-path (B4 enrich)"
```

> **Note bascule DB live (manuelle, hors plan) :** après merge, appliquer la fonction à la DB prod via MCP Supabase (`execute_sql`, project `fqmoylmvjoafihiuiiuj`) — le déploiement Modal ne lance pas les migrations.

## Task 2: Méthode repo `apply_release` + test d'intégration

**Files:**
- Modify: `apps/api/src/augura_api/modules/semantic/repo.py`
- Test: `apps/api/tests/semantic/test_upsert_semantic_release.py`

- [ ] **Step 1: Écrire le test d'intégration (échoue)**

Vérifie que la fonction insère une relation et bascule `is_current`. Marqué `integration` (exige `AUGURA_DATABASE_URL`). Utilise des IDs jetables préfixés `TEST_` et nettoie en fin de test.

```python
"""Intégration : la fonction SQL upsert_semantic_release écrit l'ontologie + release."""

import json

import pytest
from sqlalchemy import text

from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_apply_release_inserts_relation_and_bumps_current(db_session) -> None:
    repo = SemanticRepo(db_session)
    # Pré-requis : deux concepts + un prédicat existants (réutilise le seed réel).
    rows = await repo.list_concepts()
    assert len(rows) >= 2, "le seed sémantique doit être présent sur la DB de test"
    subj, obj = rows[0].local_concept_id, rows[1].local_concept_id
    pred = (await repo.list_causal_predicates())[0].predicate_id

    manifest = {"semantic_release_version": "test.0.1", "description": "test enrich"}
    payload = {
        "ontology_relations": [{
            "relation_id": "TEST_REL_0001",
            "subject_concept_id": subj, "predicate": pred, "object_concept_id": obj,
            "polarity": "increases", "default_strength": "moderate",
            "default_temporal_lag": "unknown", "mechanism_summary": "test",
            "review_status": "approved", "version": "test.0.1", "active": True,
        }],
        "ontology_relation_evidence": [{
            "evidence_id": "TEST_EV_0001", "relation_id": "TEST_REL_0001",
            "source_type": "established_physiology", "citation_or_url": "established physiology",
            "evidence_summary": "test", "population_notes": "test",
            "evidence_strength": "established", "review_status": "approved",
        }],
    }
    result = await repo.apply_release(manifest, payload)
    assert result["version"] == "test.0.1"

    # La relation est lisible et la release courante a basculé.
    got = await db_session.execute(
        text("select active from ontology_relations where relation_id = 'TEST_REL_0001'")
    )
    assert got.scalar_one() is True
    cur = await db_session.execute(
        text("select semantic_release_version from semantic_releases where is_current")
    )
    assert cur.scalar_one() == "test.0.1"

    # Nettoyage.
    await db_session.execute(text("delete from ontology_relation_evidence where evidence_id = 'TEST_EV_0001'"))
    await db_session.execute(text("delete from ontology_relations where relation_id = 'TEST_REL_0001'"))
    await db_session.execute(text("update semantic_releases set is_current = false where semantic_release_version = 'test.0.1'"))
    await db_session.execute(text("update semantic_releases set is_current = true where semantic_release_version = '2.2.0'"))
    await db_session.execute(text("delete from semantic_releases where semantic_release_version = 'test.0.1'"))
```

> Note : si la fixture `db_session` n'existe pas encore dans `apps/api/tests/`, regarder un test `@pytest.mark.integration` existant (ex. `tests/` du module corpus/literature) et réutiliser/copier sa fixture de session privilégiée. Documenter dans le test la fixture utilisée.

- [ ] **Step 2: Lancer le test (échoue : `apply_release` n'existe pas)**

Run: `cd apps/api && set -a && . ./.env && set +a && uv run pytest tests/semantic/test_upsert_semantic_release.py -v`
Expected: FAIL — `AttributeError: 'SemanticRepo' object has no attribute 'apply_release'`.

- [ ] **Step 3: Ajouter `apply_release` au repo**

Dans `apps/api/src/augura_api/modules/semantic/repo.py`, ajouter (après `release_status`) la **seule** méthode d'écriture. Elle passe par la RPC `SECURITY DEFINER` ; `json.dumps` car asyncpg attend du texte jsonb pour les paramètres liés.

```python
    # ── Écriture (B4 enrich) : exclusivement via la fonction SECURITY DEFINER ──

    async def apply_release(
        self, manifest: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Applique un batch d'enrichissement + bascule la release courante.

        Le rôle applicatif n'a pas le write direct (RLS FOR SELECT) ; tout passe par
        public.upsert_semantic_release (SECURITY DEFINER). Renvoie {version, concepts,
        relations}."""
        stmt = text(
            "select public.upsert_semantic_release("
            "cast(:manifest as jsonb), cast(:payload as jsonb))"
        ).bindparams(manifest=json.dumps(manifest), payload=json.dumps(payload))
        res = await self.session.execute(stmt)
        return coerce_jsonb(res.scalar_one())
```

- [ ] **Step 4: Lancer le test (passe)**

Run: `cd apps/api && set -a && . ./.env && set +a && uv run pytest tests/semantic/test_upsert_semantic_release.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/repo.py apps/api/tests/semantic/test_upsert_semantic_release.py
git commit -m "feat(semantic): repo.apply_release via SECURITY DEFINER + integration test"
```

## Task 3: Schémas Pydantic des routes enrich

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_schemas.py`

- [ ] **Step 1: Écrire les schémas**

Couvre les entrées des 4 chemins d'apply + la réponse. (Les schémas propose sont ajoutés en Phase 2 dans le même fichier.)

```python
"""Contrat public des routes d'enrichissement (B4) — apply + propose."""

from pydantic import BaseModel


class DirectRelationIn(BaseModel):
    """Relation légère proposée par le DAG (sans id pré-assigné)."""

    subject_concept_id: str
    object_concept_id: str
    predicate: str
    polarity: str = "neutral"
    default_strength: str = "moderate"
    mechanism_summary: str = ""
    relation_id: str | None = None  # id provisoire DAG (réconcilié au retour)


class DeactivateRelationIn(BaseModel):
    relation_id: str


class AddQualifierIn(BaseModel):
    relation_id: str
    qualifier_type: str
    qualifier_value: str
    qualifier_effect: str
    is_hard_constraint: bool = False
    notes: str = ""


class EnrichApplyRequest(BaseModel):
    """Corps de POST /semantic/enrich/apply — un seul chemin renseigné à la fois."""

    proposals: dict | None = None
    selected_concept_ids: list[str] = []
    selected_relation_ids: list[str] = []
    direct_relations: list[DirectRelationIn] = []
    deactivate_relation: DeactivateRelationIn | None = None
    add_qualifier: AddQualifierIn | None = None


class EnrichApplyResponse(BaseModel):
    new_version: str
    previous_version: str
    concepts_added: int = 0
    relations_added: int = 0
    relation_id_map: dict[str, str] = {}
    detail: str = ""
```

- [ ] **Step 2: Vérifier types/format**

Run: `cd apps/api && uv run ruff check src/augura_api/modules/semantic/enrich_schemas.py && uv run pyright src/augura_api/modules/semantic/enrich_schemas.py`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrich_schemas.py
git commit -m "feat(semantic): enrich apply request/response schemas"
```

## Task 4: Logique d'apply (4 chemins) + tests unitaires

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_apply.py`
- Test: `apps/api/tests/semantic/test_enrich_apply.py`

Référence source : `lucis-dashboard/api/enrich-apply.js` (les 4 branches). Adaptation : pas de Supabase JS — on construit `manifest`+`payload` et on délègue à `repo.apply_release`. Le bump de version est une fonction pure (testable sans DB).

- [ ] **Step 1: Écrire les tests unitaires (échouent)**

Teste la logique pure de construction de payload + bump, sans DB (repo mocké).

```python
"""Unitaires : construction manifest/payload des 4 chemins d'apply (sans DB)."""

import pytest

from augura_api.modules.semantic.enrich_apply import bump_version, build_direct_relations_payload
from augura_api.modules.semantic.enrich_schemas import DirectRelationIn


def test_bump_version_patch_minor_major() -> None:
    assert bump_version("3.0.0", "patch") == "3.0.1"
    assert bump_version("3.1.4", "minor") == "3.2.0"
    assert bump_version("3.1.4", "major") == "4.0.0"
    assert bump_version(None, "patch") == "3.0.1"  # fallback 3.0.0


def test_build_direct_relations_assigns_ids_and_autostubs_evidence() -> None:
    rels = [DirectRelationIn(subject_concept_id="A", object_concept_id="B", predicate="precedes")]
    payload, id_map = build_direct_relations_payload(
        rels, version="3.0.1", existing_max_rel_n=2, today="20260619"
    )
    assert payload["ontology_relations"][0]["relation_id"] == "ENRR_20260619_003"
    assert payload["ontology_relations"][0]["active"] is True
    assert payload["ontology_relations"][0]["polarity"] == "neutral"
    # evidence auto-stub (1 par relation).
    assert len(payload["ontology_relation_evidence"]) == 1
    assert payload["ontology_relation_evidence"][0]["relation_id"] == "ENRR_20260619_003"
```

- [ ] **Step 2: Lancer (échoue : module absent)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply.py -v`
Expected: FAIL — `ModuleNotFoundError: ...enrich_apply`.

- [ ] **Step 3: Implémenter `enrich_apply.py`**

Fonctions pures + un orchestrateur `apply()` qui choisit le chemin et appelle `repo.apply_release`. Port fidèle de `enrich-apply.js` (bump_version lignes 27-32 ; direct_relations 142-260 ; deactivate 66-98 ; add_qualifier 100-140 ; proposals 262-345).

```python
"""Logique d'apply de l'enrichissement (B4) — port de api/enrich-apply.js.

4 chemins, un seul actif par requête : proposals approuvées (pipeline propose) ·
direct_relations (relations proposées par le DAG) · deactivate_relation · add_qualifier.
Tous construisent un (manifest, payload) délégué à SemanticRepo.apply_release.
"""

from typing import Any

from augura_api.modules.semantic.enrich_schemas import (
    AddQualifierIn,
    DirectRelationIn,
    EnrichApplyRequest,
    EnrichApplyResponse,
)
from augura_api.modules.semantic.repo import SemanticRepo


def bump_version(current: str | None, kind: str) -> str:
    """Bump SemVer (port de bumpVersion). Fallback 3.0.0."""
    parts = [int(x) for x in (current or "3.0.0").split(".")]
    major, minor, patch = (parts + [0, 0, 0])[:3]
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _manifest(version: str, description: str) -> dict[str, Any]:
    return {
        "semantic_release_version": version,
        "taxonomy_version": version,
        "causal_ontology_version": version,
        "dq_ontology_version": version,
        "omop_cdm_version": "5.4",
        "description": description,
    }


def build_direct_relations_payload(
    relations: list[DirectRelationIn], *, version: str, existing_max_rel_n: int, today: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Assigne ENRR_{today}_{NNN}, auto-stub evidence, renvoie (payload, id_map)."""
    id_map: dict[str, str] = {}
    rel_rows: list[dict[str, Any]] = []
    ev_rows: list[dict[str, Any]] = []
    counter = existing_max_rel_n
    ev_counter = 0
    for rel in relations:
        counter += 1
        rid = f"ENRR_{today}_{counter:03d}"
        if rel.relation_id:
            id_map[rel.relation_id] = rid
        rel_rows.append({
            "relation_id": rid,
            "subject_concept_id": rel.subject_concept_id,
            "object_concept_id": rel.object_concept_id,
            "predicate": rel.predicate,
            "polarity": rel.polarity,
            "default_strength": rel.default_strength,
            "default_temporal_lag": "unknown",
            "mechanism_summary": rel.mechanism_summary,
            "version": version,
            "active": True,
            "review_status": "approved",
        })
        ev_counter += 1
        ev_rows.append({
            "evidence_id": f"ENRV_{today}_{ev_counter:03d}",
            "relation_id": rid,
            "source_type": "established_physiology",
            "citation_or_url": "established physiology",
            "evidence_summary": rel.mechanism_summary or "established physiology",
            "population_notes": "",
            "evidence_strength": "established",
            "review_status": "approved",
        })
    return {"ontology_relations": rel_rows, "ontology_relation_evidence": ev_rows}, id_map


class EnrichApplyService:
    """Orchestre l'apply : choisit le chemin, calcule le bump, délègue au repo."""

    def __init__(self, repo: SemanticRepo) -> None:
        self.repo = repo

    async def apply(self, req: EnrichApplyRequest, *, today: str) -> EnrichApplyResponse:
        status = await self.repo.release_status()
        current = (status.get("release") or {}).get("semantic_release_version") or "3.0.0"

        if req.deactivate_relation is not None:
            return await self._deactivate(req.deactivate_relation.relation_id, current)
        if req.add_qualifier is not None:
            return await self._add_qualifier(req.add_qualifier, current, today)
        if req.direct_relations:
            return await self._direct_relations(req.direct_relations, current, today)
        if req.proposals:
            return await self._proposals(req, current)
        raise ValueError("aucun chemin d'apply renseigné")

    async def _direct_relations(
        self, relations: list[DirectRelationIn], current: str, today: str
    ) -> EnrichApplyResponse:
        new_version = bump_version(current, "patch")
        max_n = await self.repo.max_relation_seq(today)
        payload, id_map = build_direct_relations_payload(
            relations, version=new_version, existing_max_rel_n=max_n, today=today
        )
        manifest = _manifest(
            new_version, f"patch: +{len(payload['ontology_relations'])} relation(s) via DAG"
        )
        await self.repo.apply_release(manifest, payload)
        return EnrichApplyResponse(
            new_version=new_version, previous_version=current,
            relations_added=len(payload["ontology_relations"]), relation_id_map=id_map,
        )

    async def _deactivate(self, relation_id: str, current: str) -> EnrichApplyResponse:
        existing = await self.repo.get_relation_row(relation_id)
        if existing is None:
            raise ValueError(f"relation {relation_id} introuvable")
        new_version = bump_version(current, "patch")
        row = {**existing, "active": False, "review_status": "deprecated", "version": new_version}
        manifest = _manifest(new_version, f"patch: deactivate {relation_id} via DAG review")
        await self.repo.apply_release(manifest, {"ontology_relations": [row]})
        return EnrichApplyResponse(
            new_version=new_version, previous_version=current,
            detail=f"relation_deactivated:{relation_id}",
        )

    async def _add_qualifier(
        self, q: AddQualifierIn, current: str, today: str
    ) -> EnrichApplyResponse:
        new_version = bump_version(current, "patch")
        max_n = await self.repo.max_qualifier_seq(today)
        row = {
            "qualifier_id": f"ENRQ_{today}_{max_n + 1:03d}",
            "relation_id": q.relation_id,
            "qualifier_type": q.qualifier_type,
            "qualifier_concept_id": None,
            "qualifier_value": q.qualifier_value,
            "qualifier_effect": q.qualifier_effect,
            "is_hard_constraint": q.is_hard_constraint,
            "notes": q.notes,
        }
        manifest = _manifest(new_version, f"patch: +1 qualifier on {q.relation_id}")
        await self.repo.apply_release(manifest, {"ontology_relation_qualifiers": [row]})
        return EnrichApplyResponse(
            new_version=new_version, previous_version=current,
            detail=f"qualifier_added:{row['qualifier_id']}",
        )

    async def _proposals(self, req: EnrichApplyRequest, current: str) -> EnrichApplyResponse:
        # Port de enrich-apply.js:262-345 — filtre les rows sélectionnés + cascade enfants,
        # stampe approved/active, bump minor si concepts sinon patch.
        p = req.proposals or {}
        csel, rsel = set(req.selected_concept_ids), set(req.selected_relation_ids)
        concepts = [c for c in p.get("taxonomy_concepts", []) if c.get("local_concept_id") in csel]
        relations = [r for r in p.get("ontology_relations", []) if r.get("relation_id") in rsel]
        if not concepts and not relations:
            raise ValueError("aucun concept/relation approuvé à appliquer")
        cset = {c["local_concept_id"] for c in concepts}
        rset = {r["relation_id"] for r in relations}
        new_version = bump_version(current, "minor" if concepts else "patch")

        def stamp(row: dict[str, Any]) -> dict[str, Any]:
            return {**row, "version": new_version, "active": True, "review_status": "approved"}

        def stamp_sub(row: dict[str, Any]) -> dict[str, Any]:
            return {**row, "review_status": "approved"}

        payload = {
            "taxonomy_concepts": [stamp(c) for c in concepts],
            "taxonomy_synonyms": [stamp_sub(s) for s in p.get("taxonomy_synonyms", [])
                                  if s.get("local_concept_id") in cset],
            "taxonomy_standard_codes": [s for s in p.get("taxonomy_standard_codes", [])
                                        if s.get("local_concept_id") in cset],
            "ontology_relations": [stamp(r) for r in relations],
            "ontology_relation_evidence": [stamp_sub(e) for e in p.get("ontology_relation_evidence", [])
                                           if e.get("relation_id") in rset],
            "ontology_relation_qualifiers": [stamp_sub(q) for q in p.get("ontology_relation_qualifiers", [])
                                             if q.get("relation_id") in rset],
        }
        manifest = _manifest(
            new_version,
            f"patch: +{len(concepts)} concept(s), +{len(relations)} relation(s) via enrichment",
        )
        await self.repo.apply_release(manifest, payload)
        return EnrichApplyResponse(
            new_version=new_version, previous_version=current,
            concepts_added=len(concepts), relations_added=len(relations),
        )
```

- [ ] **Step 4: Ajouter les méthodes repo manquantes**

`_direct_relations`/`_deactivate`/`_add_qualifier` utilisent 3 lectures non encore présentes. Les ajouter à `SemanticRepo` (lecture seule, OK avec RLS) :

```python
    async def max_relation_seq(self, today: str) -> int:
        """Plus grand NNN des relation_id ENRR_{today}_NNN (évite les collisions d'id)."""
        stmt = text(
            r"select coalesce(max(substring(relation_id from 'ENRR_' || :d || '_(\d{3})')::int), 0) "
            "from ontology_relations"
        ).bindparams(d=today)
        return int((await self.session.execute(stmt)).scalar_one())

    async def max_qualifier_seq(self, today: str) -> int:
        stmt = text(
            r"select coalesce(max(substring(qualifier_id from 'ENRQ_' || :d || '_(\d{3})')::int), 0) "
            "from ontology_relation_qualifiers"
        ).bindparams(d=today)
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_relation_row(self, relation_id: str) -> dict[str, Any] | None:
        stmt = text(
            "select to_jsonb(r) from ontology_relations r where relation_id = :rid"
        ).bindparams(rid=relation_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return coerce_jsonb(row) if row is not None else None
```

- [ ] **Step 5: Lancer les unitaires (passent)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply.py -v`
Expected: PASS (les deux tests).

- [ ] **Step 6: Format/lint/types**

Run: `cd apps/api && uv run ruff format . && uv run ruff check src/augura_api/modules/semantic/ && uv run pyright src/augura_api/modules/semantic/enrich_apply.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrich_apply.py apps/api/src/augura_api/modules/semantic/repo.py apps/api/tests/semantic/test_enrich_apply.py
git commit -m "feat(semantic): enrich apply service (4 paths) + repo seq helpers"
```

## Task 5: Route `POST /semantic/enrich/apply` gated owner

**Files:**
- Modify: `apps/api/src/augura_api/modules/semantic/router.py`
- Test: `apps/api/tests/semantic/test_enrich_apply_route.py`

- [ ] **Step 1: Écrire le test de gating (échoue)**

Vérifie qu'un membre non-owner reçoit 403. Réutiliser le harness de test HTTP existant (regarder un test de route gated, ex. analytics `admin`, pour la fabrication du client + override d'auth). Documenter la fixture utilisée.

```python
"""La route enrich/apply exige le rôle owner (mutation d'ontologie globale)."""

import pytest


@pytest.mark.asyncio
async def test_enrich_apply_requires_owner(client_as_member) -> None:
    resp = await client_as_member.post(
        "/semantic/enrich/apply",
        json={"direct_relations": [{"subject_concept_id": "A", "object_concept_id": "B", "predicate": "precedes"}]},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Lancer (échoue : route absente → 404)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply_route.py -v`
Expected: FAIL (404 au lieu de 403).

- [ ] **Step 3: Ajouter la route**

Dans `router.py` — importer le pattern owner (cf. analytics) et brancher le service. `today` est calculé côté serveur (UTC).

```python
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends

from augura_api.core.deps import require_role
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.semantic import enrich_schemas
from augura_api.modules.semantic.enrich_apply import EnrichApplyService

OwnerTenantDep = Annotated[CurrentTenant, Depends(require_role("owner"))]


@router.post("/enrich/apply", response_model=enrich_schemas.EnrichApplyResponse)
async def enrich_apply(
    req: enrich_schemas.EnrichApplyRequest,
    tenant: OwnerTenantDep,
    session: SessionDep,
) -> enrich_schemas.EnrichApplyResponse:
    """Persiste un enrichissement dans l'ontologie GLOBALE (gated owner). Bump de version."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    return await EnrichApplyService(SemanticRepo(session)).apply(req, today=today)
```

- [ ] **Step 4: Lancer (passe : 403)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply_route.py -v`
Expected: PASS.

- [ ] **Step 5: Suite complète + contrats**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"`
Expected: PASS partout.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/router.py apps/api/tests/semantic/test_enrich_apply_route.py
git commit -m "feat(semantic): POST /semantic/enrich/apply (owner-gated)"
```

## Task 6: Régénérer le client API (Phase 1)

**Files:**
- Modify: `packages/api-client/openapi.json` (généré), `packages/api-client/src/schema.d.ts` (généré)

- [ ] **Step 1: Régénérer**

Run:
```bash
cd apps/api && set -a && . ./.env && set +a && uv run python scripts/dump_openapi.py
cd ../.. && npm --prefix packages/api-client run generate
```
Expected: `openapi.json` contient `/semantic/enrich/apply` ; `schema.d.ts` régénéré.

- [ ] **Step 2: Vérifier le drift**

Run: `git status --porcelain packages/api-client`
Expected: les deux fichiers générés modifiés (et seulement eux dans ce package).

- [ ] **Step 3: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate for /semantic/enrich/apply"
```

> **Checkpoint Phase 1 :** le write-path est complet et testé. La boucle DAG→persistance peut être câblée (Phase 3 Task 16) indépendamment de la Phase 2.

---

# PHASE 2 — Propose pipeline

Livrable : un job qui analyse la couverture de l'ontologie pour des questions PICOT et propose concepts/relations (revus puis appliqués via Phase 1).

## Task 7: Module d'enums gouvernés `vocab.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/vocab.py`
- Test: `apps/api/tests/semantic/test_vocab.py`

- [ ] **Step 1: Écrire le test (échoue)**

```python
from augura_api.modules.semantic import vocab


def test_polarity_is_governed_three_values() -> None:
    assert vocab.POLARITY == ["increases", "decreases", "neutral"]
    assert "mixed" not in vocab.POLARITY and "unknown" not in vocab.POLARITY


def test_domains_and_qualifier_enums_present() -> None:
    assert "therapeutics" in vocab.AUGURA_DOMAINS
    assert "reverses_polarity" in vocab.QUALIFIER_EFFECTS
    assert "LOINC" in vocab.STANDARD_CODE_VOCABULARIES
```

- [ ] **Step 2: Lancer (échoue)** — Run: `cd apps/api && uv run pytest tests/semantic/test_vocab.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `vocab.py`** (port de `governed-vocab.js`)

```python
"""Vocabulaire gouverné (Semantic Layer v3 §10.5) — source unique des enums.

Importé par l'enrichissement (B4) ET le causal (B2) pour qu'ils ne divergent plus.
Bug historique corrigé : polarity valait `mixed`/`unknown` côté DAG mais `neutral`
côté enrichissement. La valeur gouvernée est `neutral`.
"""

# §10.5 — polarité des relations.
POLARITY = ["increases", "decreases", "neutral"]

# augura_domain — domaines des concepts.
AUGURA_DOMAINS = [
    "therapeutics", "measurement", "condition", "device", "procedure",
    "outcome", "structural", "biomarker", "pharmacology",
]

# §10.5 — enums gouvernés des qualifiers.
QUALIFIER_TYPES = [
    "population", "comorbidity", "age_range", "sex",
    "therapeutic_context", "biomarker_threshold", "temporal_context",
]
QUALIFIER_EFFECTS = [
    "reverses_polarity", "attenuates_strength", "amplifies_strength", "restricts_applicability",
]

# Vocabulaires de codes standards acceptés pour les concepts Layer 1.
STANDARD_CODE_VOCABULARIES = ["LOINC", "SNOMED", "RxNorm", "OMOP", "ICD10CM"]

# Buckets de force de relation.
RELATION_STRENGTH = ["strong", "moderate", "weak"]
```

- [ ] **Step 4: Lancer (passe)** — Run: `cd apps/api && uv run pytest tests/semantic/test_vocab.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/vocab.py apps/api/tests/semantic/test_vocab.py
git commit -m "feat(semantic): governed vocab module (single source of enums)"
```

## Task 8: Corriger le drift polarity du causal

**Files:**
- Modify: `apps/api/src/augura_api/modules/causal/prompt.py:141`
- Modify: `apps/api/src/augura_api/modules/causal/schemas.py:83` (défaut `ProposedRelation.polarity`)

- [ ] **Step 1: Écrire un test de garde (échoue)**

```python
"""Le tool schema DAG et l'enrichissement partagent l'enum polarity gouverné."""

from augura_api.modules.causal.prompt import DAG_FILTER_TOOL
from augura_api.modules.semantic import vocab


def test_dag_tool_polarity_enum_matches_governed_vocab() -> None:
    props = DAG_FILTER_TOOL["input_schema"]["properties"]
    rel_props = props["proposed_relations"]["items"]["properties"]
    assert rel_props["polarity"]["enum"] == vocab.POLARITY
```

Le placer dans `apps/api/tests/causal/test_polarity_governed.py`.

- [ ] **Step 2: Lancer (échoue)** — Run: `cd apps/api && uv run pytest tests/causal/test_polarity_governed.py -v` — Expected: FAIL (enum = `["increases","decreases","mixed","unknown"]`).

- [ ] **Step 3: Corriger `prompt.py`**

Remplacer l'enum en dur ligne ~141 par l'import gouverné. En tête de `prompt.py` :

```python
from augura_api.modules.semantic import vocab
```

Et l'entrée polarity (ligne ~141) :

```python
                            "enum": vocab.POLARITY,
```

- [ ] **Step 4: Corriger le défaut de `ProposedRelation`**

Dans `causal/schemas.py:83`, remplacer `polarity: str = "unknown"` par `polarity: str = "neutral"`.

- [ ] **Step 5: Lancer + non-régression DAG** — Run: `cd apps/api && uv run pytest tests/causal/ -v && uv run lint-imports` — Expected: PASS (le contrat `causal → semantic` est autorisé).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/causal/prompt.py apps/api/src/augura_api/modules/causal/schemas.py apps/api/tests/causal/test_polarity_governed.py
git commit -m "fix(causal): polarity enum from governed vocab (drop mixed/unknown)"
```

## Task 9: Logique pure d'enrichissement `enrichment.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrichment.py`
- Test: `apps/api/tests/semantic/test_enrichment.py`

Port (sans I/O) de `enrich-propose.js` : `buildSemanticData` (140-210), `matchTokens` (214-261), `directedBFS` (263-292), `analyzeCoverage` (294-361), `groupMissingConcepts` (399-418), `applyPreChecks` (479-576), `reassignIds` (431-461), `stampRows` (469-477), `mergeInto` (463-467). Utiliser des `@dataclass`/`dict` ; `normalize()` = port simple de `lexical-normalizer.js` (lowercase + trim + espaces normalisés ; le porter aussi si non présent).

- [ ] **Step 1: Écrire les tests (échouent)** — couvrir les invariants clés.

```python
"""Unitaires de la logique pure d'enrichissement (coverage, BFS, prechecks)."""

from augura_api.modules.semantic import enrichment as enr


def _concept(cid, label, domain="condition", layer=2):
    return {"local_concept_id": cid, "concept_name": label, "augura_domain": domain,
            "layer": layer, "active": True}


def test_match_tokens_exact_synonym_hit() -> None:
    concepts = [_concept("C1", "hypertension")]
    idx = enr.build_semantic_data({"taxonomy_concepts": concepts, "taxonomy_synonyms": [],
                                   "ontology_relations": [], "causal_predicates": []})
    matched, unmatched = enr.match_tokens(["hypertension"], idx.syn_lookup, idx.concept_index)
    assert matched["hypertension"] == ["C1"]
    assert not unmatched


def test_directed_bfs_finds_forward_path() -> None:
    rels = [{"relation_id": "R1", "subject_concept_id": "A", "object_concept_id": "B",
             "predicate": "precedes", "polarity": "increases", "active": True}]
    idx = enr.build_semantic_data({"taxonomy_concepts": [_concept("A", "a"), _concept("B", "b")],
                                   "taxonomy_synonyms": [], "ontology_relations": rels,
                                   "causal_predicates": []})
    res = enr.directed_bfs(idx.ontology, ["A"], ["B"], max_hops=3)
    assert res.found is True


def test_prechecks_reject_self_loop_and_orphan() -> None:
    batch = {"taxonomy_concepts": [], "taxonomy_synonyms": [], "taxonomy_standard_codes": [],
             "ontology_relations": [
                 {"relation_id": "X1", "subject_concept_id": "A", "object_concept_id": "A",
                  "predicate": "precedes", "polarity": "increases"},
                 {"relation_id": "X2", "subject_concept_id": "A", "object_concept_id": "ZZ",
                  "predicate": "precedes", "polarity": "increases"}],
             "ontology_relation_evidence": [], "ontology_relation_qualifiers": []}
    log: list[str] = []
    enr.apply_prechecks(batch, existing_concept_ids={"A"}, existing_relation_keys=set(),
                        valid_predicate_ids={"precedes"}, log=log,
                        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0})
    assert batch["ontology_relations"] == []  # self-loop + orphan rejetés
    assert any("self-loop" in m for m in log)
```

- [ ] **Step 2: Lancer (échoue)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrichment.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `enrichment.py`**

Porter chaque fonction JS citée ci-dessus en Python idiomatique. Structures :

```python
"""Logique pure d'enrichissement (B4) — port de api/enrich-propose.js (hors I/O/LLM).

Aucune dépendance DB ni réseau : testable unitairement. Index sémantique, analyse de
couverture (matchTokens + directedBFS), regroupement, pre-checks, reassign d'IDs, stamp.
"""

import re
from dataclasses import dataclass, field
from typing import Any

HOP_LIMIT = 3


def normalize(text: str | None) -> str:
    """Normalisation lexicale (port de lexical-normalizer.js) : minuscules, trim,
    espaces compactés."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


@dataclass
class _Ontology:
    relations: list[dict[str, Any]]
    by_subject: dict[str, list[dict[str, Any]]]
    by_object: dict[str, list[dict[str, Any]]]
    predicates: dict[str, dict[str, Any]]


@dataclass
class SemanticIndex:
    concept_index: list[dict[str, Any]]
    syn_lookup: dict[str, list[str]]
    ontology: _Ontology


@dataclass
class BfsResult:
    found: bool
    nearest_forward_hop: dict[str, Any] | None = None


def build_semantic_data(raw: dict[str, Any]) -> SemanticIndex: ...
def match_tokens(phrases, syn_lookup, concept_index) -> tuple[dict[str, list[str]], set[str]]: ...
def directed_bfs(ontology, from_ids, to_ids, max_hops=HOP_LIMIT) -> BfsResult: ...
def analyze_coverage(questions, concept_index, syn_lookup, ontology) -> dict[str, Any]: ...
def group_missing_concepts(missing: list[dict[str, Any]]) -> list[list[dict[str, Any]]]: ...
def apply_prechecks(batch, *, existing_concept_ids, existing_relation_keys,
                    valid_predicate_ids, log, id_counters) -> list[dict[str, Any]]: ...
def reassign_ids(batch, counters, today: str) -> None: ...
def stamp_rows(proposals, version: str) -> None: ...
def merge_into(target, source) -> None: ...
```

Remplir chaque corps en suivant **fidèlement** la fonction JS source correspondante (mêmes seuils : `len >= 4`, couverture de mots `>= 0.5`, `phraseWords <= 3` ; mêmes règles de rejet : self-loop, doublon par clé `subject|predicate|object|polarity`, orphelin sujet/objet, prédicat inconnu, L1-sans-code ; auto-stub evidence). IDs : `ENRC_/ENRR_/ENRV_/ENRQ_{today}_{NNN}` via `f"{prefix}_{today}_{n:03d}"`.

- [ ] **Step 4: Lancer (passent)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrichment.py -v` — Expected: PASS (les 3 tests).

- [ ] **Step 5: Format/lint/types** — Run: `cd apps/api && uv run ruff format . && uv run ruff check src/augura_api/modules/semantic/enrichment.py && uv run pyright src/augura_api/modules/semantic/enrichment.py` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrichment.py apps/api/tests/semantic/test_enrichment.py
git commit -m "feat(semantic): pure enrichment logic (coverage/bfs/prechecks)"
```

## Task 10: Orchestration des propositions LLM `enrich_propose.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_propose.py`
- Test: `apps/api/tests/semantic/test_enrich_propose.py`

Port de la partie I/O de `enrich-propose.js` : `PROPOSAL_SCHEMA` (dérivé de `vocab.py`), `buildSystemPrompt` (366-397), et l'orchestration des batchs (Batch 1 concepts manquants 794-864 ; Batch 2 path gaps 866-921 ; Batch 3 bootstrap 923-999 ; raccourci `selectedConcepts` 621-714). Adaptation : appels LLM via `core.llm.runtime.run_structured_agent` (au lieu de `callClaude`), Pydantic `ProposalBatch` au lieu de schéma JSON brut, progression via un callback `on_progress: Callable[[float, str], Awaitable[None]]` injecté (le handler le branche sur `set_progress`).

- [ ] **Step 1: Écrire le test (échoue) — à LLM mocké**

Un client mock renvoie un `ToolUseBlock` avec un batch minimal ; vérifier que `propose()` produit un batch agrégé et appelle `on_progress`.

```python
"""propose() agrège les batchs LLM et émet la progression (LLM mocké)."""

import pytest

from augura_api.modules.semantic.enrich_propose import propose
# Réutiliser le mock LLM des tests causal (tests/causal/) : un client dont
# messages.create renvoie un ToolUseBlock 'propose_enrichment_batch'. Copier/adapter.


@pytest.mark.asyncio
async def test_propose_aggregates_and_reports_progress(stub_llm_empty_batch) -> None:
    progress: list[tuple[float, str]] = []

    async def on_progress(frac: float, msg: str) -> None:
        progress.append((frac, msg))

    bundle = {"taxonomy_concepts": [], "taxonomy_synonyms": [], "ontology_relations": [],
              "causal_predicates": [{"predicate_id": "precedes", "description": "x"}]}
    result = await propose(
        client=stub_llm_empty_batch, model="claude-opus-4-8",
        bundle=bundle, questions=[{"id": "q1", "picot": {"intervention": ["aspirin"],
                                                          "outcome": ["stroke"]}}],
        selected_concepts=None, on_progress=on_progress,
    )
    assert "taxonomy_concepts" in result["proposals"]
    assert "coverage_summary" in result
    assert progress  # au moins une étape émise
```

- [ ] **Step 2: Lancer (échoue)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `enrich_propose.py`**

Interface publique :

```python
"""Pipeline de proposition d'enrichissement (B4) — orchestration LLM.

Port de la partie LLM de api/enrich-propose.js. Sans état serveur : prend le bundle
sémantique + des questions PICOT (ou des concepts sélectionnés), exécute les batchs
LLM via run_structured_agent, applique les pre-checks (enrichment.py) et renvoie le
batch de propositions agrégé + le résumé de couverture + le precheck_log.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from anthropic.types import ToolParam
from pydantic import BaseModel

from augura_api.core.llm.runtime import LLMClient, run_structured_agent
from augura_api.modules.semantic import enrichment, vocab


class ProposedConceptRow(BaseModel): ...      # cf. PROPOSAL_SCHEMA (concepts)
class ProposedSynonymRow(BaseModel): ...
class ProposedStandardCodeRow(BaseModel): ...
class ProposedRelationRow(BaseModel): ...
class ProposedEvidenceRow(BaseModel): ...
class ProposedQualifierRow(BaseModel): ...


class ProposalBatch(BaseModel):
    taxonomy_concepts: list[ProposedConceptRow] = []
    taxonomy_synonyms: list[ProposedSynonymRow] = []
    taxonomy_standard_codes: list[ProposedStandardCodeRow] = []
    ontology_relations: list[ProposedRelationRow] = []
    ontology_relation_evidence: list[ProposedEvidenceRow] = []
    ontology_relation_qualifiers: list[ProposedQualifierRow] = []


PROPOSAL_TOOL: ToolParam = {
    "name": "propose_enrichment_batch",
    "description": "Propose taxonomy concepts and causal ontology relations",
    "input_schema": {  # construit depuis vocab.* (enum polarity/domains/etc.)
        ...
    },
}


def build_system_prompt(predicate_list: str, existing_concepts_sample: str) -> str: ...


async def propose(
    *,
    client: LLMClient,
    model: str,
    bundle: dict[str, Any],
    questions: list[dict[str, Any]] | None,
    selected_concepts: list[dict[str, Any]] | None,
    on_progress: Callable[[float, str], Awaitable[None]],
) -> dict[str, Any]:
    """Renvoie {proposals, coverage_summary, precheck_log, summary}."""
    ...
```

Remplir les corps : dériver `PROPOSAL_TOOL["input_schema"]` des enums de `vocab.py` (polarity, domains, qualifier types/effects, standard-code vocabs) ; pour chaque batch, appeler `run_structured_agent(client, model=model, system=..., tool=PROPOSAL_TOOL, messages=[...], output_model=ProposalBatch, max_tokens=8192)` ; après chaque appel, `reassign_ids` + `apply_prechecks` (enrichment.py) + `merge_into` l'agrégat ; émettre `on_progress(frac, message)` aux étapes setup/coverage/propose/precheck ; finir par `stamp_rows(all_proposals, "pending")`. Suivre l'ordre des batchs de la source.

- [ ] **Step 4: Lancer (passe)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose.py -v` — Expected: PASS.

- [ ] **Step 5: Format/lint/types** — Run: `cd apps/api && uv run ruff format . && uv run ruff check src/augura_api/modules/semantic/enrich_propose.py && uv run pyright src/augura_api/modules/semantic/enrich_propose.py` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrich_propose.py apps/api/tests/semantic/test_enrich_propose.py
git commit -m "feat(semantic): LLM propose pipeline (coverage→batches→prechecks)"
```

## Task 11: Job handler `handle_enrich_propose`

**Files:**
- Modify: `apps/api/src/augura_api/jobs/handlers.py`
- Test: `apps/api/tests/jobs/test_enrich_propose_handler.py`

- [ ] **Step 1: Écrire le test (échoue) — LLM mocké, repo réel mocké**

Vérifier que le handler lit le bundle, exécute `propose`, écrit un artifact storage et renvoie un `result_ref`. S'inspirer d'un test de handler existant (s'il y en a) ou monter un `JobContext` minimal avec session mockée.

```python
"""handle_enrich_propose : exécute le pipeline et persiste l'artifact de propositions."""

import json

import pytest


@pytest.mark.asyncio
async def test_handle_enrich_propose_writes_artifact(enrich_job_ctx_stub) -> None:
    from augura_api.jobs.handlers import handle_enrich_propose

    ref = await handle_enrich_propose(enrich_job_ctx_stub)
    assert ref and ref.startswith("org/")
    # L'artifact contient un batch de propositions sérialisable.
    from augura_api.core import storage
    data = json.loads(storage.read_bytes(enrich_job_ctx_stub.settings, ref))
    assert "proposals" in data and "coverage_summary" in data
```

- [ ] **Step 2: Lancer (échoue)** — Run: `cd apps/api && uv run pytest tests/jobs/test_enrich_propose_handler.py -v` — Expected: FAIL (handler absent).

- [ ] **Step 3: Implémenter le handler + enregistrer le kind**

Dans `handlers.py`, ajouter le handler (mirroir de `handle_document` : lit, calcule, écrit l'artifact, log_usage) et l'entrée registry.

```python
async def handle_enrich_propose(ctx: JobContext) -> str | None:
    """Pipeline de proposition d'enrichissement (B4) : lit le bundle, exécute les
    batchs LLM, persiste le batch de propositions en artifact JSON. Progression via
    set_progress (le log textuel détaillé est inclus dans l'artifact)."""
    import json

    from augura_api.core.llm.runtime import get_anthropic_client
    from augura_api.modules import jobs as jobs_iface
    from augura_api.modules.semantic.enrich_propose import propose
    from augura_api.modules.semantic.repo import SemanticRepo

    payload = dict(ctx.job.payload or {})
    bundle = await SemanticRepo(ctx.session).read_bundle()
    client = get_anthropic_client(ctx.settings)

    async def on_progress(frac: float, _msg: str) -> None:
        await jobs_iface.set_progress(ctx.session, ctx.tenant_id, ctx.job.id, frac)

    result = await propose(
        client=client,
        model=ctx.settings.agent_model_dag,
        bundle=bundle,
        questions=payload.get("questions"),
        selected_concepts=payload.get("selected_concepts"),
        on_progress=on_progress,
    )
    ref = storage.save_bytes(
        ctx.settings,
        org_id=str(ctx.tenant_id),
        name=f"enrich-proposals-{ctx.job.id}.json",
        data=json.dumps(result).encode("utf-8"),
    )
    await analytics.log_usage(
        ctx.session, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
        event_type="semantic.enrich.proposed", route="/semantic/enrich/propose",
        metadata={"job_id": str(ctx.job.id), **result.get("summary", {})},
    )
    return ref
```

Et dans `build_handlers()` :

```python
        "enrich_propose": handle_enrich_propose,
```

> Vérifier que `ctx.settings.agent_model_dag` existe (utilisé par le causal) ; sinon utiliser le réglage de modèle d'agent approprié dans `core/config.py`.

- [ ] **Step 4: Lancer (passe)** — Run: `cd apps/api && uv run pytest tests/jobs/test_enrich_propose_handler.py -v` — Expected: PASS.

- [ ] **Step 5: Lint-imports (le handler croise les modules, c'est permis ici)** — Run: `cd apps/api && uv run lint-imports` — Expected: PASS (`jobs.handlers` est la couche d'orchestration autorisée à croiser les modules).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/jobs/handlers.py apps/api/tests/jobs/test_enrich_propose_handler.py
git commit -m "feat(jobs): enrich_propose handler (LLM pipeline → artifact)"
```

## Task 12: Routes propose + récupération des propositions

**Files:**
- Modify: `apps/api/src/augura_api/modules/semantic/router.py`
- Modify: `apps/api/src/augura_api/modules/semantic/enrich_schemas.py` (ajout requête propose)
- Test: `apps/api/tests/semantic/test_enrich_propose_route.py`

- [ ] **Step 1: Ajouter le schéma de requête propose**

Dans `enrich_schemas.py` :

```python
class PicotQuestionIn(BaseModel):
    id: str
    therapeutic_area: str | None = None
    picot: dict = {}  # {intervention?, comparator?, outcome?: list[str]}


class EnrichProposeRequest(BaseModel):
    questions: list[PicotQuestionIn] = []
    selected_concepts: list[dict] = []


class EnrichProposeAccepted(BaseModel):
    job_id: str
```

- [ ] **Step 2: Écrire le test (échoue)** — propose renvoie 202 + job_id ; la récupération d'un job inexistant donne 404.

```python
import pytest


@pytest.mark.asyncio
async def test_enrich_propose_enqueues_job(client_as_member) -> None:
    resp = await client_as_member.post(
        "/semantic/enrich/propose",
        json={"questions": [{"id": "q1", "picot": {"intervention": ["aspirin"], "outcome": ["stroke"]}}]},
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()
```

> Propose n'est **pas** gated owner (proposer ≠ muter) : tout membre peut lancer une analyse ; seul l'apply écrit.

- [ ] **Step 3: Lancer (échoue : 404)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose_route.py -v` — Expected: FAIL.

- [ ] **Step 4: Ajouter les routes**

Dans `router.py` (mirroir documents/router.py pour l'enqueue + le download d'artifact) :

```python
from fastapi import BackgroundTasks, status
from fastapi.responses import Response

from augura_api.core import storage
from augura_api.core.errors import NotFoundError
from augura_api.jobs.runner import enqueue_job
from augura_api.modules import jobs as jobs_iface


@router.post(
    "/enrich/propose",
    response_model=enrich_schemas.EnrichProposeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enrich_propose(
    req: enrich_schemas.EnrichProposeRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> enrich_schemas.EnrichProposeAccepted:
    """Lance l'analyse de couverture + proposition LLM en job background (polling)."""
    job = await jobs_iface.create_job(
        session, tenant.tenant_id, type="enrich_propose",
        payload={"questions": [q.model_dump() for q in req.questions],
                 "selected_concepts": req.selected_concepts},
    )
    enqueue_job(background_tasks, tenant, job.id, settings=settings)
    return enrich_schemas.EnrichProposeAccepted(job_id=str(job.id))


@router.get("/enrich/proposals/{job_id}")
async def enrich_proposals(
    job_id: UUID, tenant: CurrentTenantDep, session: SessionDep, settings: SettingsDep
) -> Response:
    """Sert l'artifact JSON de propositions d'un job réussi (scopé tenant)."""
    job = await jobs_iface.get_job(session, tenant.tenant_id, job_id)
    if job is None or not job.result_ref:
        raise NotFoundError("propositions non disponibles", job_id=str(job_id))
    try:
        data = storage.read_bytes(settings, job.result_ref)
    except FileNotFoundError as exc:
        raise NotFoundError("artifact introuvable", job_id=str(job_id)) from exc
    return Response(content=data, media_type="application/json")
```

Ajouter `from uuid import UUID` si absent.

- [ ] **Step 5: Lancer (passe)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose_route.py -v` — Expected: PASS.

- [ ] **Step 6: Suite complète + contrats** — Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"` — Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/router.py apps/api/src/augura_api/modules/semantic/enrich_schemas.py apps/api/tests/semantic/test_enrich_propose_route.py
git commit -m "feat(semantic): POST /enrich/propose (job) + GET /enrich/proposals"
```

## Task 13: Régénérer le client API (Phase 2)

- [ ] **Step 1: Régénérer**

Run:
```bash
cd apps/api && set -a && . ./.env && set +a && uv run python scripts/dump_openapi.py
cd ../.. && npm --prefix packages/api-client run generate
```
Expected: `openapi.json` contient `/semantic/enrich/propose` + `/semantic/enrich/proposals/{job_id}` + enum polarity corrigé.

- [ ] **Step 2: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate for /semantic/enrich/propose"
```

---

# PHASE 3 — Frontend

Livrable : surfaces de revue/acceptation câblées sur le backend réel (aucun mock).

## Task 14: Wrappers client `dataClient.js`

**Files:**
- Modify: `apps/web/src/workspace/dataClient.js`

- [ ] **Step 1: Ajouter les wrappers**

Suivre le style des appels existants (`apiJson` de `@/api`). Le propose est asynchrone : create → poll `/jobs/{id}` → fetch `/semantic/enrich/proposals/{id}`.

```javascript
import { apiJson } from '@/api'

/** Lance le job de proposition d'enrichissement. → { job_id } */
export async function enrichPropose(body) {
  return apiJson('/semantic/enrich/propose', { method: 'POST', body: JSON.stringify(body) })
}

/** Poll l'état d'un job. → { status, progress, result_ref, error } */
export async function pollJob(jobId) {
  return apiJson(`/jobs/${jobId}`)
}

/** Récupère l'artifact de propositions d'un job réussi. */
export async function fetchEnrichProposals(jobId) {
  return apiJson(`/semantic/enrich/proposals/${jobId}`)
}

/** Applique un enrichissement (owner). Chemins : proposals+selection | direct_relations | … */
export async function enrichApply(body) {
  return apiJson('/semantic/enrich/apply', { method: 'POST', body: JSON.stringify(body) })
}
```

- [ ] **Step 2: Lint** — Run: `cd apps/web && npm run lint` — Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/dataClient.js
git commit -m "feat(web): enrich propose/apply api client wrappers"
```

## Task 15: Panneau de revue `EnrichmentPanel.jsx`

**Files:**
- Create: `apps/web/src/workspace/EnrichmentPanel.jsx`
- Modify: `apps/web/src/workspace/SemanticLayerPage.jsx`

Port de `lucis-dashboard/src/workspace/LearnFromQuestionPanel.jsx` (492 l.). Adaptation clé : l'original lit le SSE en flux (`res.body.getReader()`) ; ici, **polling** — lancer `enrichPropose`, boucler `pollJob` (toutes ~1.5 s) en affichant `progress` (barre), puis `fetchEnrichProposals` au statut `succeeded`. La revue (sélection concepts/relations + cascade) et l'apply (`enrichApply({ proposals, selectedConceptIds, selectedRelationIds })`) restent identiques. **Aucun mock/fallback.**

- [ ] **Step 1: Créer le composant** — squelette d'interface :

```jsx
import { useState } from 'react'
import { enrichPropose, pollJob, fetchEnrichProposals, enrichApply } from '@/workspace/dataClient'
import { resetSemanticStore, initSemanticStore } from '@/lib/semantic-store'

// Port de LearnFromQuestionPanel : propose (job+polling) → revue → apply.
export function EnrichmentPanel({ questions }) {
  const [phase, setPhase] = useState('idle')      // idle | running | review | applying | done | error
  const [progress, setProgress] = useState(0)
  const [proposals, setProposals] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [error, setError] = useState('')

  async function runPropose() {
    setPhase('running'); setError('')
    try {
      const { job_id } = await enrichPropose({ questions })
      // Polling jusqu'à succeeded/failed.
      for (;;) {
        await new Promise(r => setTimeout(r, 1500))
        const job = await pollJob(job_id)
        setProgress(job.progress ?? 0)
        if (job.status === 'succeeded') break
        if (job.status === 'failed') throw new Error(job.error || 'job échoué')
      }
      setProposals(await fetchEnrichProposals(job_id))
      setPhase('review')
    } catch (e) { setError(String(e.message ?? e)); setPhase('error') }
  }

  async function applySelected() {
    setPhase('applying')
    try {
      // Corps en snake_case : EnrichApplyRequest attend selected_concept_ids /
      // selected_relation_ids (cohérent avec le reste du front, ex. /causal/dag).
      const selected_concept_ids = (proposals.proposals.taxonomy_concepts || [])
        .map(c => c.local_concept_id).filter(id => selected.has(id))
      const selected_relation_ids = (proposals.proposals.ontology_relations || [])
        .map(r => r.relation_id).filter(id => selected.has(id))
      await enrichApply({ proposals: proposals.proposals, selected_concept_ids, selected_relation_ids })
      resetSemanticStore(); await initSemanticStore()      // recharge la couche enrichie
      setPhase('done')
    } catch (e) { setError(String(e.message ?? e)); setPhase('error') }
  }

  // … rendu : bouton lancer, barre de progression, tableau de revue (cases + cascade),
  //   bouton appliquer, messages d'erreur. Reprendre la mise en page de la source.
}
```

Compléter le rendu en reprenant la structure visuelle de `LearnFromQuestionPanel.jsx` (tableau concepts/relations avec cases à cocher, compteurs « N/M selected », bouton apply désactivé si rien de sélectionné).

- [ ] **Step 2: Monter dans `SemanticLayerPage.jsx`** — remplacer le commentaire « intentionally omitted » (lignes 12-13) et ajouter un onglet/section « Enrichissement » rendant `<EnrichmentPanel questions={…}/>`. Les questions PICOT peuvent venir d'une saisie simple (textarea → une question) pour la v1.

- [ ] **Step 3: Lint + build** — Run: `cd apps/web && npm run lint && npm run build` — Expected: PASS.

- [ ] **Step 4: Vérification navigateur (preview)** — démarrer le dev server, ouvrir la page Semantic Layer, vérifier que le panneau s'affiche, lancer un propose (avec backend local + clé Anthropic), confirmer barre de progression puis tableau de revue. Capturer une preuve.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/workspace/EnrichmentPanel.jsx apps/web/src/workspace/SemanticLayerPage.jsx
git commit -m "feat(web): semantic enrichment review panel (propose→review→apply)"
```

## Task 16: Acceptation d'arête proposée sur le DAG

**Files:**
- Modify: `apps/web/src/workspace/CausalModelingPage.jsx`

L'original (`DagGenerationTab.jsx`) propose d'accepter une arête `proposed_*` → `enrich-apply` via `direct_relations`. Ici, brancher le bouton « accepter » sur les arêtes pointillées (déjà identifiées par `isProposed(e)` ligne 30).

- [ ] **Step 1: Câbler l'acceptation**

Sur clic d'une arête `proposed_*`, appeler :

```javascript
import { enrichApply } from '@/workspace/dataClient'
import { resetSemanticStore, initSemanticStore } from '@/lib/semantic-store'

async function acceptProposedEdge(edge) {
  await enrichApply({
    direct_relations: [{
      subject_concept_id: edge.source, object_concept_id: edge.to,
      predicate: edge.predicate, polarity: edge.polarity,
      default_strength: edge.strength, mechanism_summary: edge.mechanism_summary || '',
      relation_id: edge.id,
    }],
  })
  resetSemanticStore(); await initSemanticStore()
  // Re-générer le DAG ou re-styler l'arête comme persistée (plus de pointillé).
}
```

Ajouter l'affordance UI (bouton/menu au survol d'une arête proposée), réservée aux owners (masquer/désactiver sinon — l'API renverra 403 pour les autres ; le front ne doit pas mocker).

- [ ] **Step 2: Lint + build** — Run: `cd apps/web && npm run lint && npm run build` — Expected: PASS.

- [ ] **Step 3: Vérification navigateur** — générer un DAG produisant des arêtes proposées, accepter l'une d'elles (compte owner), confirmer la persistance (l'arête n'est plus pointillée après re-fetch). Capturer une preuve.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/workspace/CausalModelingPage.jsx
git commit -m "feat(web): accept DAG-proposed edge → persist via enrich/apply"
```

## Task 17: Vérification finale

- [ ] **Step 1: Backend complet**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"`
Expected: tout PASS. (Intégration : `uv run pytest -q -m integration` avec `AUGURA_DATABASE_URL` chargé.)

- [ ] **Step 2: Front complet**

Run: `cd apps/web && npm run lint && npm run build`
Expected: PASS.

- [ ] **Step 3: Drift contrat**

Run: `git status --porcelain packages/api-client` — Expected: rien (déjà committé en Tasks 6 & 13).

- [ ] **Step 4: Récapitulatif des actions manuelles restantes (hors plan)**

À faire séparément, sur demande explicite : (1) appliquer la fonction SQL à la DB live via MCP Supabase ; (2) redéployer le backend sur Modal ; (3) déployer le front (Vercel). Vérifier l'enrichissement de bout en bout en prod **avec un compte owner**.

---

## Notes de risque (rappel spec §8)

- **Colonnes SQL** : `taxonomy_standard_codes` n'a pas de `review_status` ; `ontology_relation_qualifiers` a `qualifier_concept_id` + `notes NOT NULL`. La fonction et les payloads doivent matcher exactement (sinon erreur d'insert).
- **`jsonb_populate_recordset`** ignore les clés en trop et met `NULL` pour les colonnes absentes : tout payload doit fournir **toutes** les colonnes `NOT NULL` de la table ciblée.
- **Grant conditionnel** : nécessaire pour que la CI `db-bundle` (Postgres sans rôle `augura_api`) passe.
- **Enum polarity** : avant bascule prod, vérifier qu'aucune donnée DAG live ne porte `mixed`/`unknown` (sinon migration de données à prévoir).
- **`set_progress` est un flottant** (0..1), pas un message : le log textuel détaillé vit dans l'artifact de propositions, pas dans le job.
```
