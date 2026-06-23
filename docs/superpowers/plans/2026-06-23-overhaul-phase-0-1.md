# Overhaul Phases 0 + 1 (Quick Wins + Safety Net) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land all low-risk hygiene fixes (Phase 0) and the CI/test safety net (Phase 1) so the riskier later phases are protected.

**Architecture:** Phase 0 = isolated, near-zero-risk edits across frontend + backend (no behavior change beyond removing a token leak and fake data). Phase 1 = additive CI jobs + pure-file pytest guards that fail closed on regressions. Nothing here touches the deploy path or runtime data flow.

**Tech Stack:** React 19 / Vite / eslint (apps/web), FastAPI / `uv` / pytest (apps/api), GitHub Actions, alembic, Supabase SQL bundle.

**Conventions for every task:**
- Source spec: [docs/superpowers/specs/2026-06-23-platform-overhaul-design.md](docs/superpowers/specs/2026-06-23-platform-overhaul-design.md).
- **Commits**: per `CLAUDE.md`, commit only when the user asks. The `git commit` steps below are the *intended* atomic units — run them only after the user gives the go-ahead for committing. No AI-attribution trailer in any message.
- Backend verification gate before moving on: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`.
- Frontend verification gate: `cd apps/web && npm run lint && npm run build`.

---

## PHASE 0 — Quick wins

### Task 1: Remove recovery-token `console.log`s

**Files:**
- Modify: `apps/web/src/ResetPassword.jsx:8-11`

- [ ] **Step 1: Delete the three debug logs**

In `apps/web/src/ResetPassword.jsx`, remove lines 8-11 (the three `console.log` calls + the blank line). The function body should start directly with the `useState` declarations:

```jsx
export default function ResetPassword() {
  const [newPassword, setNewPassword] = useState("");
```

- [ ] **Step 2: Verify**

Run: `cd apps/web && npm run lint`
Expected: PASS, and no `console` references remain (`grep -n console src/ResetPassword.jsx` → no output).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/ResetPassword.jsx
git commit -m "fix(web): stop logging URL/hash on the password-reset screen (token leak)"
```

---

### Task 2: Delete dead `DatasetUpload.jsx`

**Files:**
- Delete: `apps/web/src/workspace/DatasetUpload.jsx`

Confirmed: the only occurrence of `DatasetUpload` is its own `export` line — no import sites. The live upload path is `intake/intakeApi.js` + `AddDatasetModal` inside `DatasetsPage`.

- [ ] **Step 1: Re-confirm there are no importers**

Run: `cd apps/web && grep -rn "DatasetUpload" src/ | grep -v "src/workspace/DatasetUpload.jsx"`
Expected: no output.

- [ ] **Step 2: Delete the file**

```bash
git rm apps/web/src/workspace/DatasetUpload.jsx
```

- [ ] **Step 3: Verify build still succeeds**

Run: `cd apps/web && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(web): remove orphaned DatasetUpload.jsx (no import sites)"
```

---

### Task 3: Replace fabricated beta-tab data with honest empty states

**Files:**
- Modify: `apps/web/src/workspace/DatasetsPage.jsx` (const arrays at `:131-153`; render blocks at `:617-641`, `:711-736`, `:738-787`)

The Privacy / Validation / Lineage tabs render fabricated PHI-shaped rows (`hba1c_*`, `member_id`, `sha256:…`). Replace each tab body with its existing `<BetaNote>` plus an `<EmptyState>` (already imported, used by the Mapping/DQ tabs), and delete the four fake-data arrays.

- [ ] **Step 1: Delete the four fabricated arrays**

Remove lines `131-153` — the `PRIVACY_ROWS`, `VALIDATION_ROWS`, `LINEAGE_STEPS`, and `LINEAGE_USES` declarations (the `// ── Placeholder content …` comment block down to the `LINEAGE_USES` line). Keep the `BetaNote` component definition immediately after.

- [ ] **Step 2: Replace the Privacy tab body (was `:617-641`)**

```jsx
      {/* ── PRIVACY (beta — backend pass pending) ── */}
      {sub === 'privacy' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Privacy (beta).</strong> A PII/PHI scan will gate the dataset before
            mapping. This view activates once the backend privacy pass is wired — no preview data is shown.
          </BetaNote>
          <EmptyState icon={Shield} title="Privacy scan coming soon" subtitle="Backend privacy pass not yet wired." />
        </div>
      )}
```

- [ ] **Step 3: Replace the Validation tab body (was `:711-736`)**

```jsx
      {/* ── VALIDATION (beta — backend gate pending) ── */}
      {sub === 'validation' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Validation (beta).</strong> A release-gate summary (row count,
            missingness, types, duplicates, primary key) will live here once wired — no preview data is shown.
          </BetaNote>
          <EmptyState icon={CheckCircle2} title="Release-gate summary coming soon" subtitle="Backend validation pass not yet wired." />
        </div>
      )}
```

- [ ] **Step 4: Replace the Lineage tab body (was `:738-787`)**

```jsx
      {/* ── LINEAGE (beta — backend trace pending) ── */}
      {sub === 'lineage' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Lineage (beta).</strong> Every transformation from source to current
            state — versioned and replayable — will appear here once the backend trace is wired.
          </BetaNote>
          <EmptyState icon={GitBranch} title="Transformation trace coming soon" subtitle="Backend lineage trace not yet wired." />
        </div>
      )}
```

- [ ] **Step 5: Remove now-unused imports flagged by lint**

Run: `cd apps/web && npm run lint`
The `no-unused-vars` rule is an **error**, so any import left unused by the deletions (likely `Tag`, `ScanRow`, `ArrowRight`, `SectionTitle`, `TONE` — only if they are not still used elsewhere in the file) will fail the lint. Remove exactly the symbols lint reports as unused; keep `Shield`, `CheckCircle2`, `GitBranch`, `EmptyState`, `BetaNote`, `Card`.

- [ ] **Step 6: Verify**

Run: `cd apps/web && npm run lint && npm run build`
Expected: both PASS. `grep -nE "hba1c|member_id|sha256" src/workspace/DatasetsPage.jsx` → no output.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/workspace/DatasetsPage.jsx
git commit -m "fix(web): drop fabricated clinical rows from beta tabs (no-mock rule)"
```

---

### Task 4: Clean the eslint config + add `no-console`

**Files:**
- Modify: `apps/web/eslint.config.js`

Only `dist` exists among the ignored globs; `docs/backup/augura-corpus-intelligence/simulation/user-data/validation_dataset_doc` do not exist under `apps/web`. The server-side file group references `api/agents/tools/test/e2e/scripts` — none exist; only root `*.js` files (vite/eslint config) are real.

- [ ] **Step 1: Trim `globalIgnores` to what exists**

Replace the `globalIgnores([...])` block (lines 8-18) with:

```js
  // Build output is the only non-app folder under apps/web.
  globalIgnores(['dist']),
```

- [ ] **Step 2: Add `no-console` to the app-source rules**

In the app-source config object (`files: ['src/**/*.{js,jsx}']`), add to its `rules` map:

```js
      'no-console': ['warn', { allow: ['warn', 'error'] }],
```

- [ ] **Step 3: Scope the node block to real files**

Replace the server-side config object's `files` array (line 54) with just the root config files:

```js
    files: ['*.js'],
```

Leave that object's `extends`/`languageOptions`/`rules` as-is (node globals for `vite.config.js` / `eslint.config.js`).

- [ ] **Step 4: Verify**

Run: `cd apps/web && npm run lint`
Expected: PASS (any remaining `console.log` in app source now surfaces as a warning, not an error).

- [ ] **Step 5: Commit**

```bash
git add apps/web/eslint.config.js
git commit -m "chore(web): prune dead eslint ignore globs + add no-console"
```

---

### Task 5: Narrow the Modal probe in `enqueue_job` to `ImportError`

**Files:**
- Modify: `apps/api/src/augura_api/jobs/runner.py:130-135`

A bare `except Exception` makes a real Modal misconfiguration silently fall back to `BackgroundTasks` (which Modal doesn't run → job stuck in `queued`). Only a missing/uninitialized `modal` import should trigger the local path.

- [ ] **Step 1: Replace the try/except**

Replace lines 130-135 with:

```python
    try:
        import modal

        on_modal = not modal.is_local()
    except ImportError:
        # modal not installed ⇒ local path. Any OTHER failure (e.g. a real
        # misconfiguration inside a Modal container) must surface, not silently
        # fall back to BackgroundTasks (which Modal does not run → job stuck).
        on_modal = False
```

- [ ] **Step 2: Verify**

Run: `cd apps/api && uv run ruff check src/augura_api/jobs/runner.py && uv run pyright src/augura_api/jobs/runner.py`
Expected: PASS (the `# noqa: BLE001` is gone with the broad except; no new lint).

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/augura_api/jobs/runner.py
git commit -m "fix(jobs): only fall back to BackgroundTasks on modal ImportError"
```

---

### Task 6: Move disk I/O off the event loop + cheap `exists()`

**Files:**
- Modify: `apps/api/src/augura_api/core/storage.py`

The local-disk backend does synchronous `write_bytes`/`read_bytes`/`mkdir` inside `async def`, and `exists()` downloads the entire object on the Supabase backend.

- [ ] **Step 1: Import the thread offloader**

After `import httpx` (line 21), add:

```python
from anyio.to_thread import run_sync
```

- [ ] **Step 2: Add sync disk helpers + a ranged-GET existence probe**

Add these module-level helpers (e.g. just below `_supabase_get`):

```python
async def _supabase_exists(settings: Settings, ref: str) -> bool:
    # Range request: transfers 1 byte instead of the whole object just to test presence.
    headers = {**_auth_headers(settings), "Range": "bytes=0-0"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_object_url(settings, ref), headers=headers)
    if resp.status_code == 404:
        return False
    if resp.status_code not in (200, 206):
        raise OSError(f"Supabase Storage head failed ({resp.status_code}): {resp.text}")
    return True


def _write_disk(root: Path, ref: str, data: bytes) -> None:
    dest = root / ref
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def _read_disk(root: Path, storage_path: str) -> bytes:
    target = (root / storage_path).resolve()
    if not str(target).startswith(str(root)):
        raise FileNotFoundError("artifact path outside the allowed directory")
    return target.read_bytes()


def _exists_disk(root: Path, storage_path: str) -> bool:
    target = (root / storage_path).resolve()
    return str(target).startswith(str(root)) and target.is_file()
```

- [ ] **Step 3: Route the public functions through them**

Replace the disk branch of `save_bytes` (lines 95-98) with:

```python
    else:
        await run_sync(_write_disk, _root(settings), ref, data)
```

Replace the disk branch of `read_bytes` (lines 107-111) with:

```python
    return await run_sync(_read_disk, _root(settings).resolve(), storage_path)
```

Replace the body of `exists` (lines 115-123) with:

```python
    if _use_supabase(settings):
        return await _supabase_exists(settings, storage_path)
    return await run_sync(_exists_disk, _root(settings).resolve(), storage_path)
```

- [ ] **Step 4: Verify**

Run: `cd apps/api && uv run ruff check src/augura_api/core/storage.py && uv run pyright src/augura_api/core/storage.py && uv run pytest -q -k storage`
Expected: PASS (if no storage test exists, the `-k storage` selects nothing — that's fine; the type/lint check is the gate here).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/core/storage.py
git commit -m "perf(storage): offload disk I/O to a thread; probe existence with a ranged GET"
```

---

### Task 7: Translate remaining French docstrings/comments

**Files:**
- Modify: `apps/api/pyproject.toml:3`
- Modify: `apps/api/src/augura_api/modules/datasets/service.py:1`
- Modify: any other backend file with French comments found in Step 3

- [ ] **Step 1: Fix the pyproject description**

In `apps/api/pyproject.toml` line 3:

```toml
description = "Augura API — modular FastAPI monolith"
```

- [ ] **Step 2: Fix the datasets service docstring**

`apps/api/src/augura_api/modules/datasets/service.py` line 1:

```python
"""Datasets module logic: CRUD, columns (profiling), cohort reads."""
```

- [ ] **Step 3: Sweep for any remaining French**

Run: `cd apps/api && grep -rIlnE "(Logique|monolithe|colonnes|cohortes|données|requête|fichier|côté)" src/ pyproject.toml`
For each file reported, translate only comments/docstrings to English (no code/behavior change). Keep edits minimal and idiomatic.

- [ ] **Step 4: Verify**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/pyproject.toml apps/api/src
git commit -m "docs(api): translate remaining French docstrings to English"
```

---

## PHASE 1 — Safety net

### Task 8: Add a `web` CI job (lint + build)

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the job**

Append a new job under `jobs:` (sibling of `api`, `db-bundle`, `client-drift`):

```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
```

- [ ] **Step 2: Validate the workflow is well-formed**

Run: `cd /Users/quentin/Desktop/Augure/augura-platform && python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + build apps/web in CI"
```

---

### Task 9: Gate branch `Quentin`, add concurrency + dependency caching

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Trigger on `Quentin` and add a concurrency group**

Replace the top `on:` block (lines 3-6) with:

```yaml
on:
  push:
    branches: [main, Quentin]
  pull_request:

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

- [ ] **Step 2: Enable uv caching in all three uv jobs**

For every `uses: astral-sh/setup-uv@v5` step (jobs `api`, `db-bundle`, `client-drift`), add `enable-cache: true` under `with:` alongside the existing `python-version`:

```yaml
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
```

- [ ] **Step 3: Cache npm in `client-drift`**

In the `client-drift` job's `actions/setup-node@v4` step, add caching:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: packages/api-client/package-lock.json
```

(If `packages/api-client/package-lock.json` does not exist, omit the two cache lines for this job — verify with `ls packages/api-client/package-lock.json`.)

- [ ] **Step 4: Verify**

Run: `cd /Users/quentin/Desktop/Augure/augura-platform && python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: gate branch Quentin, add concurrency + uv/npm caching"
```

---

### Task 10: Reject AI-attribution trailers in CI

**Files:**
- Modify: `.github/workflows/ci.yml`

Server-side enforcement of the `.githooks/commit-msg` rule (local hook is opt-in per clone).

- [ ] **Step 1: Add the job**

```yaml
  commit-trailers:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Reject AI-attribution trailers in new commits
        run: |
          set -euo pipefail
          git fetch origin main --quiet || true
          if git rev-parse --verify --quiet origin/main >/dev/null; then
            range="origin/main..HEAD"
          else
            range="HEAD~1..HEAD"
          fi
          msgs="$(git log --format='%B' "$range" || true)"
          if printf '%s' "$msgs" | grep -Eni 'co-authored-by:[[:space:]]*claude|co-authored-by:.*anthropic|noreply@anthropic\.com|generated with .*claude code|🤖 generated'; then
            echo "::error::AI-attribution trailer found in a commit message (see CLAUDE.md)"
            exit 1
          fi
          echo "no AI-attribution trailers found in $range"
```

- [ ] **Step 2: Verify**

Run: `cd /Users/quentin/Desktop/Augure/augura-platform && python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: fail on AI-attribution trailers in commit messages"
```

---

### Task 11: DB guard — migration idempotency invariant

**Files:**
- Test: `apps/api/tests/db/test_migration_invariants.py` (create)

- [ ] **Step 1: Write the test**

```python
"""Pure-file guards on the alembic migration chain (no database needed)."""

import re
from pathlib import Path

ALEMBIC_DIR = Path(__file__).parents[2] / "alembic" / "versions"


def test_migrations_beyond_baseline_are_idempotent() -> None:
    """0001 applies the bundle wholesale; every migration >=0002 must be safely
    re-runnable on an already-migrated DB (CREATE/DROP ... IF [NOT] EXISTS or
    CREATE OR REPLACE)."""
    offenders = []
    for path in sorted(ALEMBIC_DIR.glob("0*.py")):
        if path.name.startswith("0001"):
            continue
        src = path.read_text(encoding="utf-8").lower()
        if not any(tok in src for tok in ("if not exists", "if exists", "create or replace")):
            offenders.append(path.name)
    assert not offenders, f"non-idempotent migrations (no IF [NOT] EXISTS / CREATE OR REPLACE): {offenders}"
```

- [ ] **Step 2: Run it**

Run: `cd apps/api && uv run pytest tests/db/test_migration_invariants.py -q`
Expected: PASS. (If it fails, a real non-idempotent migration exists — fix the migration, do not weaken the test.)

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/db/test_migration_invariants.py
git commit -m "test(db): assert migrations >=0002 are idempotent"
```

---

### Task 12: DB guard — seed stays demo-free

**Files:**
- Modify: `apps/api/tests/db/test_supabase_bundle.py`

- [ ] **Step 1: Add the tenant-data set + test**

Append to `apps/api/tests/db/test_supabase_bundle.py`:

```python
# Tenant/demo tables that seed.sql must NEVER populate (demo data lives only in
# tests/integration/fixtures.sql). Reference/ontology catalogs are allowed in seed.
TENANT_DATA_TABLES = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "dataset_files",
    "cohort_members",
    "cohort_biomarkers",
    "documents",
    "chunks",
    "agent_runs",
    "simulation_runs",
    "simulation_results",
    "jobs",
    "generated_documents",
    "usage_events",
    "artifacts",
    "dq_bundles",
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
}


def test_seed_has_no_tenant_data_inserts() -> None:
    seed = _read("seed.sql").lower()
    inserted = set(re.findall(r"insert into (\w+)", seed))
    leaked = inserted & TENANT_DATA_TABLES
    assert not leaked, f"seed.sql must stay demo-free; tenant-data inserts found: {sorted(leaked)}"
```

- [ ] **Step 2: Run it**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py::test_seed_has_no_tenant_data_inserts -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/db/test_supabase_bundle.py
git commit -m "test(db): assert seed.sql contains no tenant/demo data inserts"
```

---

### Task 13: DB guard — schema.sql tables can't bypass alembic

**Files:**
- Modify: `apps/api/tests/db/test_supabase_bundle.py`

Catches the footgun: a table added to `schema.sql` after baseline but with no migration exists on fresh DBs/CI yet is **missing on an already-migrated prod DB**.

- [ ] **Step 1: Add the post-baseline set + guard test**

Append to `apps/api/tests/db/test_supabase_bundle.py`:

```python
ALEMBIC_VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"

# Tables introduced AFTER the 0001 baseline (each must ship in a >=0002 migration).
POST_BASELINE_TABLES = {
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
    "semantic_releases",
    "dataset_files",
} | REFERENCE_CATALOGS

# Everything the baseline bundle (0001 applies schema.sql wholesale) already created.
BASELINE_TABLES = EXPECTED_TABLES - POST_BASELINE_TABLES


def _tables_created_in_migrations() -> set[str]:
    tables: set[str] = set()
    for path in sorted(ALEMBIC_VERSIONS.glob("0*.py")):
        if path.name.startswith("0001"):
            continue
        src = path.read_text(encoding="utf-8").lower()
        tables |= set(re.findall(r"create table(?: if not exists)? (\w+)", src))
        tables |= set(re.findall(r"create_table\(\s*[\"'](\w+)", src))
    return tables


def test_post_baseline_tables_each_have_a_migration() -> None:
    """Any table in schema.sql that isn't part of the 0001 baseline MUST also be
    created by a >=0002 migration, or it will be missing on already-migrated prod DBs."""
    schema_tables = set(re.findall(r"create table if not exists (\w+)", _read("schema.sql")))
    in_migrations = _tables_created_in_migrations()
    unguarded = {t for t in schema_tables if t not in BASELINE_TABLES and t not in in_migrations}
    assert not unguarded, (
        "tables in schema.sql with no >=0002 migration (would be missing on prod): "
        f"{sorted(unguarded)}. Add a migration, or add to BASELINE_TABLES if it predates 0002."
    )
```

- [ ] **Step 2: Run it**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py::test_post_baseline_tables_each_have_a_migration -q`
Expected: PASS. If a `POST_BASELINE_TABLES` member is reported as unguarded, the `create table` regex didn't match that migration's form — inspect the migration and extend `_tables_created_in_migrations()` accordingly (don't remove the table from the set).

- [ ] **Step 3: Full backend gate + commit**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest -q`
Expected: PASS.

```bash
git add apps/api/tests/db/test_supabase_bundle.py
git commit -m "test(db): guard against schema.sql tables that bypass alembic"
```

---

## Phase 1 follow-up (deferred — needs DB + model registration facts)

The **model↔DB reflection drift test** (reflect the post-`alembic upgrade head` DB in the `db-bundle` job and diff columns/types against `Base.metadata`, allowlisting the intentional partial `TaxonomyConcept` mapping) is intentionally NOT in this plan: it requires confirming how all module models register into `Base.metadata` (which import populates it) before exact code can be written without guessing. Schedule it as the first task of a short Phase 1b once we've verified the registration entrypoint (likely importing `augura_api.main`). The three pure-file guards above already cover the idempotency, seed-hygiene, and schema-bypass risks.

---

## Self-review notes (author)

- **Spec coverage**: Phase 0 items (token leak, fake data, dead file, eslint, enqueue_job, storage, French) → Tasks 1-7. Phase 1 items (web CI, gate Quentin, concurrency/caching, AI-trailer check, DB guards) → Tasks 8-13. The model↔DB drift test is explicitly deferred with rationale (not dropped).
- **Placeholders**: none — every code/YAML step shows the literal content. The two discovery-driven steps (eslint unused-import removal in Task 3; French sweep in Task 7) are deterministic via tool output, not vague instructions.
- **Naming consistency**: `EXPECTED_TABLES`, `REFERENCE_CATALOGS`, `_read` are reused from the existing `test_supabase_bundle.py`; `POST_BASELINE_TABLES`/`BASELINE_TABLES`/`_tables_created_in_migrations` are defined before use; `run_sync`, `_write_disk`/`_read_disk`/`_exists_disk`/`_supabase_exists` are defined in Task 6 before being referenced.
