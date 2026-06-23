# B4 Port — "On-the-fly" semantic enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the enrichment loop of the governed semantic layer — persist the proposed concepts/relations (from the DAG or from a dedicated LLM pipeline) into the global ontology, with versioning and a review guardrail.

**Architecture:** Faithful port of `Augura-Health/augura@98c1023` (`api/enrich-propose.js`, `api/enrich-apply.js`, `src/semantic/governed-vocab.js`, `LearnFromQuestionPanel.jsx`, SQL function `upsert_semantic_release`) into the platform's `modules/semantic/` vertical slice. Writing to the **global** ontology (`public`) via a `SECURITY DEFINER` SQL function; synchronous **apply** gated `owner`; **propose** run as a background job. 3 independently deliverable phases.

**Tech Stack:** FastAPI · SQLAlchemy async · asyncpg · Pydantic · Postgres/pgvector (Supabase) · Anthropic (LLM) · React 19/Vite (frontend) · `uv`/`pytest`/`ruff`/`pyright` (backend) · `npm`/`eslint` (frontend).

**Reference spec:** [docs/superpowers/specs/2026-06-19-b4-semantic-enrichment-port-design.md](../specs/2026-06-19-b4-semantic-enrichment-port-design.md)

**Port source (local working copy):** `/Users/quentin/Desktop/Augure/lucis-dashboard` (branch `data-intake-nde`, commit `98c1023`).

**Conventions to respect (CLAUDE.md):** comments/docstrings **in French**; `ruff` line 100; `pyright` strict; `lint-imports` (`causal → semantic` allowed, `core` never imports `modules`); migrations **0002+ idempotent**; **no mock/fallback** on the `apps/web` side; **never** hand-edit `packages/api-client/src/schema.d.ts`. **Never** commit/push/deploy without an explicit request — this plan creates local commits per task; the live DB switch and the Modal deployment remain separate manual actions.

**Verification commands (from `apps/api`, env loaded `set -a; . ./.env; set +a`):**
- `uv run ruff format --check . && uv run ruff check .`
- `uv run pyright`
- `uv run lint-imports`
- `uv run pytest -q` (the `@pytest.mark.integration` tests require `AUGURA_DATABASE_URL`)
- Contract regeneration: `uv run python scripts/dump_openapi.py` then `npm --prefix ../../packages/api-client run generate`

---

## File Structure (decomposition)

**Backend — Phase 1 (write-path / apply):**
- `apps/api/supabase/functions.sql` *(modify)* — adds the `upsert_semantic_release` function.
- `apps/api/alembic/versions/0006_semantic_enrich_function.py` *(create)* — idempotent migration (CREATE OR REPLACE).
- `apps/api/src/augura_api/modules/semantic/repo.py` *(modify)* — adds `apply_release()` (the only write method).
- `apps/api/src/augura_api/modules/semantic/enrich_schemas.py` *(create)* — Pydantic schemas for the enrich routes (apply + propose).
- `apps/api/src/augura_api/modules/semantic/enrich_apply.py` *(create)* — logic of the 4 apply paths (builds manifest+payload).
- `apps/api/src/augura_api/modules/semantic/router.py` *(modify)* — route `POST /semantic/enrich/apply` gated owner.
- `apps/api/tests/semantic/test_enrich_apply.py` *(create)* — apply unit tests.
- `apps/api/tests/semantic/test_upsert_semantic_release.py` *(create)* — SQL integration.

**Backend — Phase 2 (propose pipeline):**
- `apps/api/src/augura_api/modules/semantic/vocab.py` *(create)* — governed enums.
- `apps/api/src/augura_api/modules/causal/prompt.py` + `schemas.py` *(modify)* — consume `vocab.POLARITY` (drift fix).
- `apps/api/src/augura_api/modules/semantic/enrichment.py` *(create)* — pure logic (coverage, BFS, prechecks, reassign, stamp).
- `apps/api/src/augura_api/modules/semantic/enrich_propose.py` *(create)* — LLM batch orchestration.
- `apps/api/src/augura_api/jobs/handlers.py` *(modify)* — `handle_enrich_propose` + kind registration.
- `apps/api/src/augura_api/modules/semantic/router.py` *(modify)* — `POST /semantic/enrich/propose` + `GET /semantic/enrich/proposals/{job_id}`.
- `apps/api/tests/semantic/test_enrichment.py` *(create)* — pure-logic unit tests.
- `apps/api/tests/semantic/test_enrich_propose_handler.py` *(create)* — job with mocked LLM.

**Frontend — Phase 3:**
- `apps/web/src/workspace/dataClient.js` *(modify)* — wrappers `enrichPropose`/`pollJob`/`fetchEnrichProposals`/`enrichApply`.
- `apps/web/src/workspace/EnrichmentPanel.jsx` *(create)* — port of `LearnFromQuestionPanel`.
- `apps/web/src/workspace/SemanticLayerPage.jsx` *(modify)* — mounts the panel.
- `apps/web/src/workspace/CausalModelingPage.jsx` *(modify)* — "accept the edge" button + `resetSemanticStore()`.

---

# PHASE 1 — Write-path (apply)

Deliverable: you can accept a relation proposed by the DAG and see it persisted in the ontology (version bump). Independently testable.

## Task 1: SQL function `upsert_semantic_release`

**Files:**
- Modify: `apps/api/supabase/functions.sql` (append at the end of the file)
- Create: `apps/api/alembic/versions/0006_semantic_enrich_function.py`

- [ ] **Step 1: Write the function in `functions.sql`**

Add at the end of `apps/api/supabase/functions.sql`. **Targets `public`** (the platform has no `semantic` schema). Columns verified against `schema.sql:500-697` — note: `taxonomy_standard_codes` has **no** `review_status`.

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- upsert_semantic_release: applies an enrichment batch (B4) to the governed
-- semantic layer and flips the current release. SECURITY DEFINER: the application
-- role (RLS FOR SELECT only) writes EXCLUSIVELY through this function.
-- Idempotent (CREATE OR REPLACE + upserts by key).
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
    raise exception 'semantic_release_version required in the manifest';
  end if;

  -- Concepts first (FK target of relations / synonyms / codes).
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

  -- Flip the current release (append-only, a single is_current).
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
-- Conditional grant: the application role does not exist on the CI Postgres (db-bundle).
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_api') then
    execute 'grant execute on function public.upsert_semantic_release(jsonb, jsonb) to augura_api';
  end if;
end $$;
```

- [ ] **Step 2: Create the alembic 0006 migration**

`apps/api/alembic/versions/0006_semantic_enrich_function.py` — copy the SQL block above into an `op.execute(...)`. `CREATE OR REPLACE FUNCTION` + conditional grant = idempotent.

```python
"""upsert_semantic_release: semantic-layer enrichment write-path (B4)

SECURITY DEFINER function: the application role (RLS FOR SELECT) writes the global
ontology EXCLUSIVELY through it. Idempotent (CREATE OR REPLACE + conditional grant),
also lives in the canonical functions.sql bundle executed by 0001_baseline.

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
<<PASTE HERE the full SQL block from Step 1, from "create or replace function" to the final "end $$;">>
"""


def upgrade() -> None:
    op.execute(_FUNCTION_SQL)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.upsert_semantic_release(jsonb, jsonb);")
```

- [ ] **Step 3: Check the format/lint**

Run: `cd apps/api && uv run ruff format --check alembic/versions/0006_semantic_enrich_function.py && uv run ruff check alembic/versions/0006_semantic_enrich_function.py`
Expected: PASS (no error).

- [ ] **Step 4: Commit**

```bash
git add apps/api/supabase/functions.sql apps/api/alembic/versions/0006_semantic_enrich_function.py
git commit -m "feat(semantic): upsert_semantic_release write-path (B4 enrich)"
```

> **Live DB switch note (manual, out of plan):** after merge, apply the function to the prod DB via Supabase MCP (`execute_sql`, project `fqmoylmvjoafihiuiiuj`) — the Modal deployment does not run the migrations.

## Task 2: Repo method `apply_release` + integration test

**Files:**
- Modify: `apps/api/src/augura_api/modules/semantic/repo.py`
- Test: `apps/api/tests/semantic/test_upsert_semantic_release.py`

- [ ] **Step 1: Write the integration test (fails)**

Verifies that the function inserts a relation and flips `is_current`. Marked `integration` (requires `AUGURA_DATABASE_URL`). Uses disposable IDs prefixed `TEST_` and cleans up at the end of the test.

```python
"""Integration: the SQL function upsert_semantic_release writes the ontology + release."""

import json

import pytest
from sqlalchemy import text

from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_apply_release_inserts_relation_and_bumps_current(db_session) -> None:
    repo = SemanticRepo(db_session)
    # Prerequisite: two existing concepts + one predicate (reuses the real seed).
    rows = await repo.list_concepts()
    assert len(rows) >= 2, "the semantic seed must be present on the test DB"
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

    # The relation is readable and the current release has flipped.
    got = await db_session.execute(
        text("select active from ontology_relations where relation_id = 'TEST_REL_0001'")
    )
    assert got.scalar_one() is True
    cur = await db_session.execute(
        text("select semantic_release_version from semantic_releases where is_current")
    )
    assert cur.scalar_one() == "test.0.1"

    # Cleanup.
    await db_session.execute(text("delete from ontology_relation_evidence where evidence_id = 'TEST_EV_0001'"))
    await db_session.execute(text("delete from ontology_relations where relation_id = 'TEST_REL_0001'"))
    await db_session.execute(text("update semantic_releases set is_current = false where semantic_release_version = 'test.0.1'"))
    await db_session.execute(text("update semantic_releases set is_current = true where semantic_release_version = '2.2.0'"))
    await db_session.execute(text("delete from semantic_releases where semantic_release_version = 'test.0.1'"))
```

> Note: if the `db_session` fixture does not yet exist in `apps/api/tests/`, look at an existing `@pytest.mark.integration` test (e.g. the corpus/literature module's `tests/`) and reuse/copy its privileged session fixture. Document in the test which fixture is used.

- [ ] **Step 2: Run the test (fails: `apply_release` does not exist)**

Run: `cd apps/api && set -a && . ./.env && set +a && uv run pytest tests/semantic/test_upsert_semantic_release.py -v`
Expected: FAIL — `AttributeError: 'SemanticRepo' object has no attribute 'apply_release'`.

- [ ] **Step 3: Add `apply_release` to the repo**

In `apps/api/src/augura_api/modules/semantic/repo.py`, add (after `release_status`) the **only** write method. It goes through the `SECURITY DEFINER` RPC; `json.dumps` because asyncpg expects jsonb text for the bound parameters.

```python
    # ── Write (B4 enrich): exclusively through the SECURITY DEFINER function ──

    async def apply_release(
        self, manifest: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Applies an enrichment batch + flips the current release.

        The application role has no direct write (RLS FOR SELECT); everything goes
        through public.upsert_semantic_release (SECURITY DEFINER). Returns {version,
        concepts, relations}."""
        stmt = text(
            "select public.upsert_semantic_release("
            "cast(:manifest as jsonb), cast(:payload as jsonb))"
        ).bindparams(manifest=json.dumps(manifest), payload=json.dumps(payload))
        res = await self.session.execute(stmt)
        return coerce_jsonb(res.scalar_one())
```

- [ ] **Step 4: Run the test (passes)**

Run: `cd apps/api && set -a && . ./.env && set +a && uv run pytest tests/semantic/test_upsert_semantic_release.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/repo.py apps/api/tests/semantic/test_upsert_semantic_release.py
git commit -m "feat(semantic): repo.apply_release via SECURITY DEFINER + integration test"
```

## Task 3: Pydantic schemas for the enrich routes

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_schemas.py`

- [ ] **Step 1: Write the schemas**

Covers the inputs of the 4 apply paths + the response. (The propose schemas are added in Phase 2 in the same file.)

```python
"""Public contract of the enrichment routes (B4) — apply + propose."""

from pydantic import BaseModel


class DirectRelationIn(BaseModel):
    """Lightweight relation proposed by the DAG (without a pre-assigned id)."""

    subject_concept_id: str
    object_concept_id: str
    predicate: str
    polarity: str = "neutral"
    default_strength: str = "moderate"
    mechanism_summary: str = ""
    relation_id: str | None = None  # provisional DAG id (reconciled on return)


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
    """Body of POST /semantic/enrich/apply — only one path set at a time."""

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

- [ ] **Step 2: Check types/format**

Run: `cd apps/api && uv run ruff check src/augura_api/modules/semantic/enrich_schemas.py && uv run pyright src/augura_api/modules/semantic/enrich_schemas.py`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrich_schemas.py
git commit -m "feat(semantic): enrich apply request/response schemas"
```

## Task 4: Apply logic (4 paths) + unit tests

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_apply.py`
- Test: `apps/api/tests/semantic/test_enrich_apply.py`

Source reference: `lucis-dashboard/api/enrich-apply.js` (the 4 branches). Adaptation: no Supabase JS — we build `manifest`+`payload` and delegate to `repo.apply_release`. The version bump is a pure function (testable without a DB).

- [ ] **Step 1: Write the unit tests (fail)**

Tests the pure payload-construction + bump logic, without a DB (mocked repo).

```python
"""Unit tests: manifest/payload construction for the 4 apply paths (no DB)."""

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
    # auto-stub evidence (1 per relation).
    assert len(payload["ontology_relation_evidence"]) == 1
    assert payload["ontology_relation_evidence"][0]["relation_id"] == "ENRR_20260619_003"
```

- [ ] **Step 2: Run (fails: module absent)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply.py -v`
Expected: FAIL — `ModuleNotFoundError: ...enrich_apply`.

- [ ] **Step 3: Implement `enrich_apply.py`**

Pure functions + an `apply()` orchestrator that picks the path and calls `repo.apply_release`. Faithful port of `enrich-apply.js` (bump_version lines 27-32; direct_relations 142-260; deactivate 66-98; add_qualifier 100-140; proposals 262-345).

```python
"""Enrichment apply logic (B4) — port of api/enrich-apply.js.

4 paths, only one active per request: approved proposals (propose pipeline) ·
direct_relations (relations proposed by the DAG) · deactivate_relation · add_qualifier.
All build a (manifest, payload) delegated to SemanticRepo.apply_release.
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
    """SemVer bump (port of bumpVersion). Fallback 3.0.0."""
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
    """Assigns ENRR_{today}_{NNN}, auto-stubs evidence, returns (payload, id_map)."""
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
    """Orchestrates the apply: picks the path, computes the bump, delegates to the repo."""

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
        raise ValueError("no apply path provided")

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
            raise ValueError(f"relation {relation_id} not found")
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
        # Port of enrich-apply.js:262-345 — filters the selected rows + cascades children,
        # stamps approved/active, bumps minor if concepts else patch.
        p = req.proposals or {}
        csel, rsel = set(req.selected_concept_ids), set(req.selected_relation_ids)
        concepts = [c for c in p.get("taxonomy_concepts", []) if c.get("local_concept_id") in csel]
        relations = [r for r in p.get("ontology_relations", []) if r.get("relation_id") in rsel]
        if not concepts and not relations:
            raise ValueError("no approved concept/relation to apply")
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

- [ ] **Step 4: Add the missing repo methods**

`_direct_relations`/`_deactivate`/`_add_qualifier` use 3 reads not yet present. Add them to `SemanticRepo` (read-only, OK with RLS):

```python
    async def max_relation_seq(self, today: str) -> int:
        """Largest NNN among relation_id ENRR_{today}_NNN (avoids id collisions)."""
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

- [ ] **Step 5: Run the unit tests (pass)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply.py -v`
Expected: PASS (both tests).

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

- [ ] **Step 1: Write the gating test (fails)**

Verifies that a non-owner member gets a 403. Reuse the existing HTTP test harness (look at a gated route test, e.g. analytics `admin`, for the client construction + auth override). Document the fixture used.

```python
"""The enrich/apply route requires the owner role (global ontology mutation)."""

import pytest


@pytest.mark.asyncio
async def test_enrich_apply_requires_owner(client_as_member) -> None:
    resp = await client_as_member.post(
        "/semantic/enrich/apply",
        json={"direct_relations": [{"subject_concept_id": "A", "object_concept_id": "B", "predicate": "precedes"}]},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run (fails: route absent → 404)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply_route.py -v`
Expected: FAIL (404 instead of 403).

- [ ] **Step 3: Add the route**

In `router.py` — import the owner pattern (cf. analytics) and wire the service. `today` is computed server-side (UTC).

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
    """Persists an enrichment into the GLOBAL ontology (owner-gated). Version bump."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    return await EnrichApplyService(SemanticRepo(session)).apply(req, today=today)
```

- [ ] **Step 4: Run (passes: 403)**

Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_apply_route.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + contracts**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"`
Expected: PASS everywhere.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/router.py apps/api/tests/semantic/test_enrich_apply_route.py
git commit -m "feat(semantic): POST /semantic/enrich/apply (owner-gated)"
```

## Task 6: Regenerate the API client (Phase 1)

**Files:**
- Modify: `packages/api-client/openapi.json` (generated), `packages/api-client/src/schema.d.ts` (generated)

- [ ] **Step 1: Regenerate**

Run:
```bash
cd apps/api && set -a && . ./.env && set +a && uv run python scripts/dump_openapi.py
cd ../.. && npm --prefix packages/api-client run generate
```
Expected: `openapi.json` contains `/semantic/enrich/apply`; `schema.d.ts` regenerated.

- [ ] **Step 2: Check the drift**

Run: `git status --porcelain packages/api-client`
Expected: both generated files modified (and only those in this package).

- [ ] **Step 3: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate for /semantic/enrich/apply"
```

> **Phase 1 checkpoint:** the write-path is complete and tested. The DAG→persistence loop can be wired (Phase 3 Task 16) independently of Phase 2.

---

# PHASE 2 — Propose pipeline

Deliverable: a job that analyzes the ontology coverage for PICOT questions and proposes concepts/relations (reviewed then applied via Phase 1).

## Task 7: Governed enums module `vocab.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/vocab.py`
- Test: `apps/api/tests/semantic/test_vocab.py`

- [ ] **Step 1: Write the test (fails)**

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

- [ ] **Step 2: Run (fails)** — Run: `cd apps/api && uv run pytest tests/semantic/test_vocab.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implement `vocab.py`** (port of `governed-vocab.js`)

```python
"""Governed vocabulary (Semantic Layer v3 §10.5) — single source of the enums.

Imported by enrichment (B4) AND causal (B2) so they no longer diverge. Historical bug
fixed: polarity was `mixed`/`unknown` on the DAG side but `neutral` on the enrichment
side. The governed value is `neutral`.
"""

# §10.5 — relation polarity.
POLARITY = ["increases", "decreases", "neutral"]

# augura_domain — concept domains.
AUGURA_DOMAINS = [
    "therapeutics", "measurement", "condition", "device", "procedure",
    "outcome", "structural", "biomarker", "pharmacology",
]

# §10.5 — governed qualifier enums.
QUALIFIER_TYPES = [
    "population", "comorbidity", "age_range", "sex",
    "therapeutic_context", "biomarker_threshold", "temporal_context",
]
QUALIFIER_EFFECTS = [
    "reverses_polarity", "attenuates_strength", "amplifies_strength", "restricts_applicability",
]

# Standard-code vocabularies accepted for Layer 1 concepts.
STANDARD_CODE_VOCABULARIES = ["LOINC", "SNOMED", "RxNorm", "OMOP", "ICD10CM"]

# Relation strength buckets.
RELATION_STRENGTH = ["strong", "moderate", "weak"]
```

- [ ] **Step 4: Run (passes)** — Run: `cd apps/api && uv run pytest tests/semantic/test_vocab.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/vocab.py apps/api/tests/semantic/test_vocab.py
git commit -m "feat(semantic): governed vocab module (single source of enums)"
```

## Task 8: Fix the causal polarity drift

**Files:**
- Modify: `apps/api/src/augura_api/modules/causal/prompt.py:141`
- Modify: `apps/api/src/augura_api/modules/causal/schemas.py:83` (default `ProposedRelation.polarity`)

- [ ] **Step 1: Write a guard test (fails)**

```python
"""The DAG tool schema and enrichment share the governed polarity enum."""

from augura_api.modules.causal.prompt import DAG_FILTER_TOOL
from augura_api.modules.semantic import vocab


def test_dag_tool_polarity_enum_matches_governed_vocab() -> None:
    props = DAG_FILTER_TOOL["input_schema"]["properties"]
    rel_props = props["proposed_relations"]["items"]["properties"]
    assert rel_props["polarity"]["enum"] == vocab.POLARITY
```

Place it in `apps/api/tests/causal/test_polarity_governed.py`.

- [ ] **Step 2: Run (fails)** — Run: `cd apps/api && uv run pytest tests/causal/test_polarity_governed.py -v` — Expected: FAIL (enum = `["increases","decreases","mixed","unknown"]`).

- [ ] **Step 3: Fix `prompt.py`**

Replace the hardcoded enum at line ~141 with the governed import. At the top of `prompt.py`:

```python
from augura_api.modules.semantic import vocab
```

And the polarity entry (line ~141):

```python
                            "enum": vocab.POLARITY,
```

- [ ] **Step 4: Fix the `ProposedRelation` default**

In `causal/schemas.py:83`, replace `polarity: str = "unknown"` with `polarity: str = "neutral"`.

- [ ] **Step 5: Run + DAG non-regression** — Run: `cd apps/api && uv run pytest tests/causal/ -v && uv run lint-imports` — Expected: PASS (the `causal → semantic` contract is allowed).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/causal/prompt.py apps/api/src/augura_api/modules/causal/schemas.py apps/api/tests/causal/test_polarity_governed.py
git commit -m "fix(causal): polarity enum from governed vocab (drop mixed/unknown)"
```

## Task 9: Pure enrichment logic `enrichment.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrichment.py`
- Test: `apps/api/tests/semantic/test_enrichment.py`

Port (without I/O) of `enrich-propose.js`: `buildSemanticData` (140-210), `matchTokens` (214-261), `directedBFS` (263-292), `analyzeCoverage` (294-361), `groupMissingConcepts` (399-418), `applyPreChecks` (479-576), `reassignIds` (431-461), `stampRows` (469-477), `mergeInto` (463-467). Use `@dataclass`/`dict`; `normalize()` = simple port of `lexical-normalizer.js` (lowercase + trim + normalized spaces; port it too if not present).

- [ ] **Step 1: Write the tests (fail)** — cover the key invariants.

```python
"""Unit tests of the pure enrichment logic (coverage, BFS, prechecks)."""

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
    assert batch["ontology_relations"] == []  # self-loop + orphan rejected
    assert any("self-loop" in m for m in log)
```

- [ ] **Step 2: Run (fails)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrichment.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implement `enrichment.py`**

Port each JS function cited above into idiomatic Python. Structures:

```python
"""Pure enrichment logic (B4) — port of api/enrich-propose.js (excluding I/O/LLM).

No DB or network dependency: unit-testable. Semantic index, coverage analysis
(matchTokens + directedBFS), grouping, pre-checks, ID reassignment, stamp.
"""

import re
from dataclasses import dataclass, field
from typing import Any

HOP_LIMIT = 3


def normalize(text: str | None) -> str:
    """Lexical normalization (port of lexical-normalizer.js): lowercase, trim,
    compacted spaces."""
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

Fill in each body **faithfully** following the corresponding source JS function (same thresholds: `len >= 4`, word coverage `>= 0.5`, `phraseWords <= 3`; same rejection rules: self-loop, duplicate by key `subject|predicate|object|polarity`, orphan subject/object, unknown predicate, L1-without-code; auto-stub evidence). IDs: `ENRC_/ENRR_/ENRV_/ENRQ_{today}_{NNN}` via `f"{prefix}_{today}_{n:03d}"`.

- [ ] **Step 4: Run (pass)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrichment.py -v` — Expected: PASS (the 3 tests).

- [ ] **Step 5: Format/lint/types** — Run: `cd apps/api && uv run ruff format . && uv run ruff check src/augura_api/modules/semantic/enrichment.py && uv run pyright src/augura_api/modules/semantic/enrichment.py` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/enrichment.py apps/api/tests/semantic/test_enrichment.py
git commit -m "feat(semantic): pure enrichment logic (coverage/bfs/prechecks)"
```

## Task 10: LLM proposal orchestration `enrich_propose.py`

**Files:**
- Create: `apps/api/src/augura_api/modules/semantic/enrich_propose.py`
- Test: `apps/api/tests/semantic/test_enrich_propose.py`

Port of the I/O part of `enrich-propose.js`: `PROPOSAL_SCHEMA` (derived from `vocab.py`), `buildSystemPrompt` (366-397), and the batch orchestration (Batch 1 missing concepts 794-864; Batch 2 path gaps 866-921; Batch 3 bootstrap 923-999; `selectedConcepts` shortcut 621-714). Adaptation: LLM calls via `core.llm.runtime.run_structured_agent` (instead of `callClaude`), Pydantic `ProposalBatch` instead of a raw JSON schema, progress via an injected `on_progress: Callable[[float, str], Awaitable[None]]` callback (the handler wires it onto `set_progress`).

- [ ] **Step 1: Write the test (fails) — with mocked LLM**

A mock client returns a `ToolUseBlock` with a minimal batch; verify that `propose()` produces an aggregated batch and calls `on_progress`.

```python
"""propose() aggregates the LLM batches and emits progress (mocked LLM)."""

import pytest

from augura_api.modules.semantic.enrich_propose import propose
# Reuse the LLM mock from the causal tests (tests/causal/): a client whose
# messages.create returns a 'propose_enrichment_batch' ToolUseBlock. Copy/adapt.


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
    assert progress  # at least one step emitted
```

- [ ] **Step 2: Run (fails)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose.py -v` — Expected: FAIL (module absent).

- [ ] **Step 3: Implement `enrich_propose.py`**

Public interface:

```python
"""Enrichment proposal pipeline (B4) — LLM orchestration.

Port of the LLM part of api/enrich-propose.js. Stateless on the server: takes the
semantic bundle + PICOT questions (or selected concepts), runs the LLM batches via
run_structured_agent, applies the pre-checks (enrichment.py) and returns the
aggregated proposal batch + the coverage summary + the precheck_log.
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
    "input_schema": {  # built from vocab.* (polarity/domains/etc. enums)
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
    """Returns {proposals, coverage_summary, precheck_log, summary}."""
    ...
```

Fill in the bodies: derive `PROPOSAL_TOOL["input_schema"]` from the enums of `vocab.py` (polarity, domains, qualifier types/effects, standard-code vocabs); for each batch, call `run_structured_agent(client, model=model, system=..., tool=PROPOSAL_TOOL, messages=[...], output_model=ProposalBatch, max_tokens=8192)`; after each call, `reassign_ids` + `apply_prechecks` (enrichment.py) + `merge_into` the aggregate; emit `on_progress(frac, message)` at the setup/coverage/propose/precheck steps; finish with `stamp_rows(all_proposals, "pending")`. Follow the source's batch order.

- [ ] **Step 4: Run (passes)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose.py -v` — Expected: PASS.

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

- [ ] **Step 1: Write the test (fails) — mocked LLM, mocked real repo**

Verify that the handler reads the bundle, runs `propose`, writes a storage artifact and returns a `result_ref`. Take inspiration from an existing handler test (if there is one) or set up a minimal `JobContext` with a mocked session.

```python
"""handle_enrich_propose: runs the pipeline and persists the proposals artifact."""

import json

import pytest


@pytest.mark.asyncio
async def test_handle_enrich_propose_writes_artifact(enrich_job_ctx_stub) -> None:
    from augura_api.jobs.handlers import handle_enrich_propose

    ref = await handle_enrich_propose(enrich_job_ctx_stub)
    assert ref and ref.startswith("org/")
    # The artifact contains a serializable proposal batch.
    from augura_api.core import storage
    data = json.loads(storage.read_bytes(enrich_job_ctx_stub.settings, ref))
    assert "proposals" in data and "coverage_summary" in data
```

- [ ] **Step 2: Run (fails)** — Run: `cd apps/api && uv run pytest tests/jobs/test_enrich_propose_handler.py -v` — Expected: FAIL (handler absent).

- [ ] **Step 3: Implement the handler + register the kind**

In `handlers.py`, add the handler (mirror of `handle_document`: reads, computes, writes the artifact, log_usage) and the registry entry.

```python
async def handle_enrich_propose(ctx: JobContext) -> str | None:
    """Enrichment proposal pipeline (B4): reads the bundle, runs the LLM batches,
    persists the proposal batch as a JSON artifact. Progress via set_progress (the
    detailed text log is included in the artifact)."""
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

And in `build_handlers()`:

```python
        "enrich_propose": handle_enrich_propose,
```

> Check that `ctx.settings.agent_model_dag` exists (used by the causal); otherwise use the appropriate agent-model setting in `core/config.py`.

- [ ] **Step 4: Run (passes)** — Run: `cd apps/api && uv run pytest tests/jobs/test_enrich_propose_handler.py -v` — Expected: PASS.

- [ ] **Step 5: Lint-imports (the handler crosses modules, which is allowed here)** — Run: `cd apps/api && uv run lint-imports` — Expected: PASS (`jobs.handlers` is the orchestration layer allowed to cross modules).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/jobs/handlers.py apps/api/tests/jobs/test_enrich_propose_handler.py
git commit -m "feat(jobs): enrich_propose handler (LLM pipeline → artifact)"
```

## Task 12: Propose routes + proposals retrieval

**Files:**
- Modify: `apps/api/src/augura_api/modules/semantic/router.py`
- Modify: `apps/api/src/augura_api/modules/semantic/enrich_schemas.py` (add propose request)
- Test: `apps/api/tests/semantic/test_enrich_propose_route.py`

- [ ] **Step 1: Add the propose request schema**

In `enrich_schemas.py`:

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

- [ ] **Step 2: Write the test (fails)** — propose returns 202 + job_id; retrieving a nonexistent job gives 404.

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

> Propose is **not** gated owner (proposing ≠ mutating): any member can launch an analysis; only the apply writes.

- [ ] **Step 3: Run (fails: 404)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose_route.py -v` — Expected: FAIL.

- [ ] **Step 4: Add the routes**

In `router.py` (mirror documents/router.py for the enqueue + artifact download):

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
    """Launches the coverage analysis + LLM proposal as a background job (polling)."""
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
    """Serves the JSON proposals artifact of a succeeded job (tenant-scoped)."""
    job = await jobs_iface.get_job(session, tenant.tenant_id, job_id)
    if job is None or not job.result_ref:
        raise NotFoundError("proposals not available", job_id=str(job_id))
    try:
        data = storage.read_bytes(settings, job.result_ref)
    except FileNotFoundError as exc:
        raise NotFoundError("artifact not found", job_id=str(job_id)) from exc
    return Response(content=data, media_type="application/json")
```

Add `from uuid import UUID` if absent.

- [ ] **Step 5: Run (passes)** — Run: `cd apps/api && uv run pytest tests/semantic/test_enrich_propose_route.py -v` — Expected: PASS.

- [ ] **Step 6: Full suite + contracts** — Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"` — Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/router.py apps/api/src/augura_api/modules/semantic/enrich_schemas.py apps/api/tests/semantic/test_enrich_propose_route.py
git commit -m "feat(semantic): POST /enrich/propose (job) + GET /enrich/proposals"
```

## Task 13: Regenerate the API client (Phase 2)

- [ ] **Step 1: Regenerate**

Run:
```bash
cd apps/api && set -a && . ./.env && set +a && uv run python scripts/dump_openapi.py
cd ../.. && npm --prefix packages/api-client run generate
```
Expected: `openapi.json` contains `/semantic/enrich/propose` + `/semantic/enrich/proposals/{job_id}` + the fixed polarity enum.

- [ ] **Step 2: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate for /semantic/enrich/propose"
```

---

# PHASE 3 — Frontend

Deliverable: review/acceptance surfaces wired to the real backend (no mock).

## Task 14: Client wrappers `dataClient.js`

**Files:**
- Modify: `apps/web/src/workspace/dataClient.js`

- [ ] **Step 1: Add the wrappers**

Follow the style of the existing calls (`apiJson` from `@/api`). The propose is asynchronous: create → poll `/jobs/{id}` → fetch `/semantic/enrich/proposals/{id}`.

```javascript
import { apiJson } from '@/api'

/** Launches the enrichment proposal job. → { job_id } */
export async function enrichPropose(body) {
  return apiJson('/semantic/enrich/propose', { method: 'POST', body: JSON.stringify(body) })
}

/** Polls a job's state. → { status, progress, result_ref, error } */
export async function pollJob(jobId) {
  return apiJson(`/jobs/${jobId}`)
}

/** Fetches the proposals artifact of a succeeded job. */
export async function fetchEnrichProposals(jobId) {
  return apiJson(`/semantic/enrich/proposals/${jobId}`)
}

/** Applies an enrichment (owner). Paths: proposals+selection | direct_relations | … */
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

## Task 15: Review panel `EnrichmentPanel.jsx`

**Files:**
- Create: `apps/web/src/workspace/EnrichmentPanel.jsx`
- Modify: `apps/web/src/workspace/SemanticLayerPage.jsx`

Port of `lucis-dashboard/src/workspace/LearnFromQuestionPanel.jsx` (492 lines). Key adaptation: the original reads the SSE as a stream (`res.body.getReader()`); here, **polling** — launch `enrichPropose`, loop `pollJob` (every ~1.5 s) showing `progress` (bar), then `fetchEnrichProposals` on `succeeded` status. The review (concept/relation selection + cascade) and the apply (`enrichApply({ proposals, selectedConceptIds, selectedRelationIds })`) stay identical. **No mock/fallback.**

- [ ] **Step 1: Create the component** — interface skeleton:

```jsx
import { useState } from 'react'
import { enrichPropose, pollJob, fetchEnrichProposals, enrichApply } from '@/workspace/dataClient'
import { resetSemanticStore, initSemanticStore } from '@/lib/semantic-store'

// Port of LearnFromQuestionPanel: propose (job+polling) → review → apply.
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
      // Poll until succeeded/failed.
      for (;;) {
        await new Promise(r => setTimeout(r, 1500))
        const job = await pollJob(job_id)
        setProgress(job.progress ?? 0)
        if (job.status === 'succeeded') break
        if (job.status === 'failed') throw new Error(job.error || 'job failed')
      }
      setProposals(await fetchEnrichProposals(job_id))
      setPhase('review')
    } catch (e) { setError(String(e.message ?? e)); setPhase('error') }
  }

  async function applySelected() {
    setPhase('applying')
    try {
      // snake_case body: EnrichApplyRequest expects selected_concept_ids /
      // selected_relation_ids (consistent with the rest of the front, e.g. /causal/dag).
      const selected_concept_ids = (proposals.proposals.taxonomy_concepts || [])
        .map(c => c.local_concept_id).filter(id => selected.has(id))
      const selected_relation_ids = (proposals.proposals.ontology_relations || [])
        .map(r => r.relation_id).filter(id => selected.has(id))
      await enrichApply({ proposals: proposals.proposals, selected_concept_ids, selected_relation_ids })
      resetSemanticStore(); await initSemanticStore()      // reload the enriched layer
      setPhase('done')
    } catch (e) { setError(String(e.message ?? e)); setPhase('error') }
  }

  // … render: launch button, progress bar, review table (checkboxes + cascade),
  //   apply button, error messages. Reuse the source layout.
}
```

Complete the rendering by reusing the visual structure of `LearnFromQuestionPanel.jsx` (concepts/relations table with checkboxes, "N/M selected" counters, apply button disabled if nothing selected).

- [ ] **Step 2: Mount in `SemanticLayerPage.jsx`** — replace the "intentionally omitted" comment (lines 12-13) and add an "Enrichment" tab/section rendering `<EnrichmentPanel questions={…}/>`. The PICOT questions can come from a simple input (textarea → one question) for v1.

- [ ] **Step 3: Lint + build** — Run: `cd apps/web && npm run lint && npm run build` — Expected: PASS.

- [ ] **Step 4: Browser check (preview)** — start the dev server, open the Semantic Layer page, verify the panel renders, launch a propose (with local backend + Anthropic key), confirm the progress bar then the review table. Capture proof.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/workspace/EnrichmentPanel.jsx apps/web/src/workspace/SemanticLayerPage.jsx
git commit -m "feat(web): semantic enrichment review panel (propose→review→apply)"
```

## Task 16: Accepting a proposed edge on the DAG

**Files:**
- Modify: `apps/web/src/workspace/CausalModelingPage.jsx`

The original (`DagGenerationTab.jsx`) offers to accept a `proposed_*` edge → `enrich-apply` via `direct_relations`. Here, wire the "accept" button on the dashed edges (already identified by `isProposed(e)` line 30).

- [ ] **Step 1: Wire the acceptance**

On clicking a `proposed_*` edge, call:

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
  // Re-generate the DAG or re-style the edge as persisted (no longer dashed).
}
```

Add the UI affordance (button/menu on hover of a proposed edge), reserved for owners (hide/disable otherwise — the API will return 403 for the others; the frontend must not mock).

- [ ] **Step 2: Lint + build** — Run: `cd apps/web && npm run lint && npm run build` — Expected: PASS.

- [ ] **Step 3: Browser check** — generate a DAG producing proposed edges, accept one of them (owner account), confirm persistence (the edge is no longer dashed after a re-fetch). Capture proof.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/workspace/CausalModelingPage.jsx
git commit -m "feat(web): accept DAG-proposed edge → persist via enrich/apply"
```

## Task 17: Final verification

- [ ] **Step 1: Full backend**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q -m "not integration"`
Expected: all PASS. (Integration: `uv run pytest -q -m integration` with `AUGURA_DATABASE_URL` loaded.)

- [ ] **Step 2: Full frontend**

Run: `cd apps/web && npm run lint && npm run build`
Expected: PASS.

- [ ] **Step 3: Contract drift**

Run: `git status --porcelain packages/api-client` — Expected: nothing (already committed in Tasks 6 & 13).

- [ ] **Step 4: Recap of the remaining manual actions (out of plan)**

To be done separately, on explicit request: (1) apply the SQL function to the live DB via Supabase MCP; (2) redeploy the backend on Modal; (3) deploy the frontend (Vercel). Verify end-to-end enrichment in prod **with an owner account**.

---

## Risk notes (recap of spec §8)

- **SQL columns**: `taxonomy_standard_codes` has no `review_status`; `ontology_relation_qualifiers` has `qualifier_concept_id` + `notes NOT NULL`. The function and the payloads must match exactly (otherwise an insert error).
- **`jsonb_populate_recordset`** ignores extra keys and sets `NULL` for absent columns: every payload must provide **all** the `NOT NULL` columns of the targeted table.
- **Conditional grant**: needed for the CI `db-bundle` (Postgres without the `augura_api` role) to pass.
- **Polarity enum**: before the prod switch, verify that no live DAG data carries `mixed`/`unknown` (otherwise a data migration is needed).
- **`set_progress` is a float** (0..1), not a message: the detailed text log lives in the proposals artifact, not in the job.
```
