# Datasets bytes → Supabase Storage (cross-container fix)

- **Date**: 2026-06-22
- **Branch**: Quentin
- **Status**: approved (design)

## Problem

`datasets/service.upload_dataset` writes the uploaded file to local disk via
`core.storage.save_bytes(...)` and stores a relative path in `datasets.storage_path`.
`dq/service.run` reads it back via `core.storage.read_bytes(...)`.

On Modal the filesystem is ephemeral **and per-container**. Upload and DQ-read both run in
synchronous ASGI requests, but Modal scales the ASGI app horizontally — the container that
handled the upload is not necessarily the one that later serves the DQ read. So `read_bytes`
hits an empty disk → `FileNotFoundError`. Same class of cross-container bug already fixed for
the semantic-enrich flow (`jobs.result_json`, 3079a94) and document generation
(`generated_documents.content` bytea, 0008 + f45fd00).

## Decision

Fix datasets via a **real shared object store** (Supabase Storage) behind `core/storage.py`,
not a DB `bytea` column. Chosen over the bytea route deliberately: datasets are file blobs
that belong in object storage, and `core/storage.py` already documented Supabase Storage as
its intended prod backend.

Consequence vs. the documents fix: **no DB migration**. `datasets.storage_path` already
exists and holds a backend-agnostic ref, so there is no `schema.sql`/alembic change. The
"infra applied to prod" step becomes *provision a bucket* + *set secrets*, not *add a column*.

## Scope (small)

- Only `save_bytes` caller: `datasets/service.upload_dataset`.
- Only `read_bytes` caller: `dq/service.run`.
- The documents handler uses only `build_ref` (pure string) + DB `content` — untouched.
- Both target call sites are already `async`.

## Design

### 1. `core/storage.py` — dual backend, async

- `save_bytes` / `read_bytes` become **`async`**. `build_ref` stays a sync string helper.
- Backend chosen at runtime from `Settings`:
  - **Supabase Storage** when `supabase_url` *and* `supabase_service_role_key` are set.
  - **Local disk** otherwise (current dev/test/CI behavior — keeps the gate green with no creds).
- Supabase calls use the existing `httpx` dep (`AsyncClient`):
  - upload: `POST {url}/storage/v1/object/{bucket}/{ref}` headers
    `Authorization: Bearer <key>`, `apikey: <key>`, `x-upsert: true`, body = bytes.
    Non-2xx → raise `OSError` with status + body.
  - download: `GET {url}/storage/v1/object/{bucket}/{ref}` same auth headers.
    404 → `FileNotFoundError` (preserves the existing contract).
- Object key = existing `build_ref(org_id, name)` = `org/<org>/<name>`. `datasets.storage_path`
  keeps storing this ref unchanged.
- `exists` (no current caller) routed through the chosen backend for consistency.

### 2. `core/config.py` — new optional settings

`supabase_url: str | None`, `supabase_service_role_key: str | None`,
`storage_bucket: str = "datasets"`. All optional ⇒ boot/health unaffected; absent ⇒ disk.

### 3. Call sites

- `datasets/service.upload_dataset`: `ref = await save_bytes(...)`.
- `dq/service.run`: `data = await read_bytes(...)`, mapping `FileNotFoundError` →
  `NotFoundError` for a clean 404 instead of a 500.

### 4. Error handling

- 25 MB cap is enforced upstream by `parse_upload` before `save_bytes`.
- Upload non-2xx → `OSError` (fails the upload request cleanly).
- Download 404/missing → `FileNotFoundError` → `NotFoundError` at the dq layer.
- `httpx` timeout set explicitly.

## Infra (prod)

- Provision a **private** bucket `datasets` via Supabase MCP
  (`insert into storage.buckets ... public = false`). Service role bypasses Storage RLS ⇒
  no storage policies required.
- Add `AUGURA_SUPABASE_URL` + `AUGURA_SUPABASE_SERVICE_ROLE_KEY` to `apps/api/.env`
  (service-role key supplied by the user — not exposed via MCP), then re-create the
  `augura-api` Modal secret via `scripts/deploy_modal.sh` and redeploy.

## Tests + verification

- `tests/core/test_storage.py`: disk-backend roundtrip; Supabase backend with a monkeypatched
  fake `httpx.AsyncClient` (asserts URL/headers/upsert; 404 → `FileNotFoundError`);
  backend-selection logic. (`respx`/`pytest-httpx` not installed → monkeypatch.)
- Existing `test_datasets_upload` / `test_dq_run` integration tests stay green on disk backend.
- Full CI gate before push: `ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest`.
- Prod: upload a dataset, then run DQ in a separate request/container; confirm the read
  succeeds and the object exists in the bucket.

## Non-goals

- Migrating documents/exports/artifacts to Storage (documents already uses bytea; out of scope).
- Recovering pre-existing prod dataset rows whose ephemeral-disk files are already gone.
- Storage RLS policies (backend uses service role, which bypasses them).
