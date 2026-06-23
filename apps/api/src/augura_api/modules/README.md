# Modules — split convention

Each module is an isolated **vertical slice** (import-linter contract
"data modules do not import each other"). Canonical layout:

```
modules/<name>/
  __init__.py   # public interface: re-exposes `router` + the functions consumed
                # cross-module (e.g. jobs: create_job/get_job; corpus: search_corpus)
  router.py     # HTTP adapter: FastAPI routes, depends on core.deps (tenant/session)
  service.py    # application logic; orchestrates the repo, applies the rules
  repo.py       # data access (SQLAlchemy), each method scoped by tenant_id
  models.py     # SQLAlchemy tables
  schemas.py    # Pydantic contracts (input/output)
```

## Service / repo construction (DI)

Convention: **the router injects a repo built into the service** —
`XService(XRepo(session))` (cf. studies/corpus/datasets). The older modules
(simulation/documents/analytics) still inject the `session` and rebuild the
repo per method; identical behavior, to be aligned on the repo-injected form on the
next pass. Do not mix the two in a new module.

## Accepted exceptions

- **jobs** — cross-cutting infrastructure (queue). Logic in `service.py`
  (`create_job`/`get_job`, idempotent module-level functions), no service class;
  no rich input `schemas`. Consumed by simulation/documents AND by its own router.
- **agents** — LLM orchestration layer: no `repo.py`/`models.py` (owns no
  table; reads the corpus via the public interface of `corpus`). `service.py` +
  `streaming.py` + `tools.py`.

## Authorization

Sensitive routes are guarded with `core.deps.require_role("owner", …)` as a dependency
(e.g. `/analytics/admin`). Everything else goes through the `CurrentTenantDep` +
`SessionDep` chain (tenant RLS active).
