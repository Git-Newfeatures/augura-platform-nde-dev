# Phase 1 — Monorepo foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An `augura-platform` monorepo where quality is locked down (pyright strict, ruff, import-linter, pytest, CI) and where a minimal FastAPI app (healthcheck, fail-fast config, structured logging, RFC 9457 errors) is deployed to Modal in the dev environment.

**Architecture:** Modular FastAPI monolith (spec: `docs/specs/2026-06-11-augura-backend-architecture-design.md`). This phase builds only the `core/` foundation (config, logging, errors) + the plumbing (uv, CI, Modal). The `modules/` and `jobs/` packages are created empty so that the import contracts are active from day one.

**Tech Stack:** Python 3.12 · uv · FastAPI · pydantic-settings · structlog · pytest + pytest-asyncio + httpx · ruff · pyright (strict) · import-linter · Modal · GitHub Actions.

**Spec reference:** §4 (monorepo), §9 (rules), §10 (deployment), §12 phase 1.

**Execution context:** repo `/Users/quentin/Desktop/Augure/augura-platform` (already `git init`, branch `main`). No worktree needed: dedicated fresh repo. Commits without a co-author trailer (Quentin's preference).

---

### Task 1: Scaffold the monorepo and the apps/api project

**Files:**
- Create: `.gitignore`, `README.md`
- Create: `apps/api/` (uv project, src layout), `apps/api/src/augura_api/{core,modules,jobs}/__init__.py`

- [ ] **Step 1: Create the root .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
dist/

# Node (apps/web arrives in phase 2)
node_modules/

# Env & tooling
.env
.env.*
.DS_Store
```

- [ ] **Step 2: Create the root README**

```markdown
# Augura Platform

Augura's production monorepo — clinical study design platform.

- `apps/api` — FastAPI backend (modular monolith), deployed to Modal
- `apps/web` — React frontend (arrives in phase 2)
- `packages/api-client` — TS client generated from the OpenAPI (arrives in phase 2)
- `docs/specs` — validated architecture · `docs/plans` — implementation plans

Reference spec: `docs/specs/2026-06-11-augura-backend-architecture-design.md`.
```

- [ ] **Step 3: Initialize the uv project in src layout**

```bash
cd /Users/quentin/Desktop/Augure/augura-platform
mkdir -p apps/api && cd apps/api
uv init --lib --name augura-api --python 3.12
```

Expected: `uv init` creates `pyproject.toml`, `src/augura_api/__init__.py`, `.python-version`.
Then empty the generated `__init__.py` (remove the example function if there is one):

```bash
echo '' > src/augura_api/__init__.py
rm -f src/augura_api/py.typed && touch src/augura_api/py.typed
```

- [ ] **Step 4: Create the core, modules, jobs packages (empty but real)**

```bash
mkdir -p src/augura_api/core src/augura_api/modules src/augura_api/jobs tests
touch src/augura_api/core/__init__.py src/augura_api/modules/__init__.py src/augura_api/jobs/__init__.py
```

- [ ] **Step 5: Add the dependencies**

```bash
uv add fastapi "uvicorn[standard]" pydantic-settings structlog
uv add --dev pytest pytest-asyncio httpx ruff pyright import-linter modal
```

Expected: `pyproject.toml` updated + `uv.lock` created, with no resolution error.

- [ ] **Step 6: Verify the package imports**

Run: `uv run python -c "import augura_api; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
cd /Users/quentin/Desktop/Augure/augura-platform
git add .gitignore README.md apps/api
git commit -m "chore: scaffold monorepo + apps/api project (uv, src layout)"
```

---

### Task 2: Fail-fast settings (core/config.py)

**Files:**
- Create: `apps/api/src/augura_api/core/config.py`
- Test: `apps/api/tests/core/test_config.py`

- [ ] **Step 1: Configure pytest in pyproject.toml**

Add to `apps/api/pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the failing tests**

Create an empty `apps/api/tests/__init__.py`, an empty `apps/api/tests/core/__init__.py`, then `apps/api/tests/core/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from augura_api.core.config import Settings, get_settings


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    s = Settings()  # pyright: ignore[reportCallIssue] -- fields injected by the environment
    assert s.env == "dev"
    assert s.app_name == "augura-api"
    assert s.version == "0.1.0"


def test_settings_fails_fast_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUGURA_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue] -- a missing env must raise


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
```

- [ ] **Step 3: Verify the tests fail**

Run: `cd apps/api && uv run pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.core.config'`

- [ ] **Step 4: Implement Settings**

Create `apps/api/src/augura_api/core/config.py`:

```python
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from the AUGURA_* variables.

    Any missing required field fails the boot (fail-fast).
    """

    model_config = SettingsConfigDict(env_prefix="AUGURA_", frozen=True)

    env: Literal["dev", "prod"]
    app_name: str = "augura-api"
    version: str = "0.1.0"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- fields injected by the environment
```

- [ ] **Step 5: Verify the tests pass**

Run: `cd apps/api && uv run pytest tests/core/test_config.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/pyproject.toml apps/api/tests apps/api/src/augura_api/core/config.py
git commit -m "feat(core): settings pydantic fail-fast (AUGURA_*)"
```

---

### Task 3: App factory + healthcheck

**Files:**
- Create: `apps/api/src/augura_api/main.py`
- Create: `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_app.py`

- [ ] **Step 1: Create the shared environment fixture**

Create `apps/api/tests/conftest.py`:

```python
import pytest

from augura_api.core.config import get_settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean dev environment and an empty settings cache."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

Note: `test_settings_fails_fast_without_env` (Task 2) stays correct — its `delenv` runs after the autouse fixture.

- [ ] **Step 2: Write the failing test**

Create `apps/api/tests/test_app.py`:

```python
import httpx

from augura_api.main import create_app


async def test_healthz_returns_ok() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "env": "dev", "version": "0.1.0"}
```

- [ ] **Step 3: Verify the test fails**

Run: `cd apps/api && uv run pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.main'`

- [ ] **Step 4: Implement create_app**

Create `apps/api/src/augura_api/main.py`:

```python
from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    app = FastAPI(title=cfg.app_name, version=cfg.version)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    return app
```

- [ ] **Step 5: Verify the test passes**

Run: `cd apps/api && uv run pytest -v`
Expected: all PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/conftest.py apps/api/tests/test_app.py apps/api/src/augura_api/main.py
git commit -m "feat(api): app factory + healthcheck /healthz"
```

---

### Task 4: Structured logging + request_id middleware

**Files:**
- Create: `apps/api/src/augura_api/core/logging.py`
- Modify: `apps/api/src/augura_api/main.py`
- Test: `apps/api/tests/core/test_logging.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/core/test_logging.py`:

```python
import httpx

from augura_api.main import create_app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_response_carries_generated_request_id() -> None:
    r = await _get("/healthz")
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) == 32  # uuid4().hex


async def test_incoming_request_id_is_preserved() -> None:
    r = await _get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd apps/api && uv run pytest tests/core/test_logging.py -v`
Expected: FAIL — `assert 'x-request-id' in r.headers`

- [ ] **Step 3: Implement the logging and the middleware (pure ASGI — not BaseHTTPMiddleware, which would break SSE streaming in phase 4)**

Create `apps/api/src/augura_api/core/logging.py`:

```python
import logging
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import structlog

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


class RequestIdMiddleware:
    """Propagates X-Request-ID (incoming or generated) into the response and the log context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]
        }
        request_id = incoming.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
```

- [ ] **Step 4: Wire it into create_app**

Replace the contents of `apps/api/src/augura_api/main.py` with:

```python
from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings
from augura_api.core.logging import RequestIdMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(title=cfg.app_name, version=cfg.version)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    return app
```

- [ ] **Step 5: Verify everything passes**

Run: `cd apps/api && uv run pytest -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/core/logging.py apps/api/src/augura_api/main.py apps/api/tests/core/test_logging.py
git commit -m "feat(core): structlog JSON + ASGI request_id middleware"
```

---

### Task 5: AppError hierarchy + Problem Details responses (RFC 9457)

**Files:**
- Create: `apps/api/src/augura_api/core/errors.py`
- Modify: `apps/api/src/augura_api/main.py`
- Test: `apps/api/tests/core/test_errors.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/core/test_errors.py`:

```python
import httpx

from augura_api.core.errors import NotFoundError
from augura_api.main import create_app


def _app_with_boom() -> httpx.ASGITransport:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("study not found", study_id="s1")

    return httpx.ASGITransport(app=app)


async def test_app_error_renders_problem_details() -> None:
    async with httpx.AsyncClient(transport=_app_with_boom(), base_url="http://test") as client:
        r = await client.get("/boom")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["title"] == "Resource not found"
    assert body["status"] == 404
    assert body["detail"] == "study not found"
    assert body["code"] == "not_found"
    assert body["context"] == {"study_id": "s1"}
```

- [ ] **Step 2: Verify the test fails**

Run: `cd apps/api && uv run pytest tests/core/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.core.errors'`

- [ ] **Step 3: Implement the hierarchy and the handler**

Create `apps/api/src/augura_api/core/errors.py`:

```python
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error. Subclass it, never raise it directly."""

    code: str = "app_error"
    http_status: int = 500
    title: str = "Application error"

    def __init__(self, detail: str, **context: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.context = context


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404
    title = "Resource not found"


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = 403
    title = "Forbidden"


class ConflictError(AppError):
    code = "conflict"
    http_status = 409
    title = "Conflict"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {
            "type": f"https://augura.dev/errors/{exc.code}",
            "title": exc.title,
            "status": exc.http_status,
            "detail": exc.detail,
            "code": exc.code,
        }
        if exc.context:
            body["context"] = exc.context
        return JSONResponse(
            status_code=exc.http_status,
            content=body,
            media_type="application/problem+json",
        )
```

- [ ] **Step 4: Wire it into create_app**

Replace the contents of `apps/api/src/augura_api/main.py` with:

```python
from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings
from augura_api.core.errors import register_error_handlers
from augura_api.core.logging import RequestIdMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(title=cfg.app_name, version=cfg.version)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    return app
```

- [ ] **Step 5: Verify everything passes**

Run: `cd apps/api && uv run pytest -v`
Expected: 7 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/core/errors.py apps/api/src/augura_api/main.py apps/api/tests/core/test_errors.py
git commit -m "feat(core): AppError hierarchy + RFC 9457 responses"
```

---

### Task 6: Quality locks — pyright strict, ruff, import-linter

**Files:**
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1: Add the tooling configuration to pyproject.toml**

Add to `apps/api/pyproject.toml`:

```toml
[tool.pyright]
include = ["src", "tests"]
typeCheckingMode = "strict"
pythonVersion = "3.12"

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TID252"]

[tool.importlinter]
root_package = "augura_api"

[[tool.importlinter.contracts]]
name = "core is independent of modules and jobs"
type = "forbidden"
source_modules = ["augura_api.core"]
forbidden_modules = ["augura_api.modules", "augura_api.jobs"]
```

(The "modules do not import each other" contract will be added in phase 2 once `modules/studies` exists — an `independence` contract on an empty package fails.)

- [ ] **Step 2: Run ruff and fix**

Run: `cd apps/api && uv run ruff format . && uv run ruff check --fix .`
Expected: `All checks passed!` (after any reformatting)

- [ ] **Step 3: Run pyright and fix**

Run: `cd apps/api && uv run pyright`
Expected: `0 errors, 0 warnings` — if errors come up, actually fix them (no `type: ignore` without a justifying comment, spec rule §9)

- [ ] **Step 4: Run import-linter**

Run: `cd apps/api && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 5: Verify the tests still pass**

Run: `cd apps/api && uv run pytest -q`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add apps/api/pyproject.toml apps/api/src apps/api/tests
git commit -m "chore(api): pyright strict + ruff + import-linter (core contract)"
```

---

### Task 7: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  api:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run pyright
      - run: uv run lint-imports
      - run: uv run pytest -q
```

- [ ] **Step 2: Replay the exact CI sequence locally**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: each command exits successfully (this is the guarantee that CI will be green on the first push)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + typecheck + import contracts + tests"
```

---

### Task 8: Modal deployment (dev environment)

**Files:**
- Create: `apps/api/modal_app.py`

- [ ] **Step 1: Verify Modal authentication**

Run: `cd apps/api && uv run modal profile current`
Expected: a profile/workspace name. On an authentication error: run `uv run modal setup` (opens the browser) then re-check.

- [ ] **Step 2: Create the dev environment if it does not exist**

Run: `uv run modal environment list`
If `dev` is missing: `uv run modal environment create dev`
Expected: `dev` appears in the list.

- [ ] **Step 3: Write modal_app.py**

Create `apps/api/modal_app.py`:

```python
import modal
from fastapi import FastAPI

# Phase 1: runtime deps listed explicitly (3 packages).
# Phase 2+: switch to uv.lock sync when the list grows.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi", "pydantic-settings", "structlog")
    .env({"AUGURA_ENV": "dev"})  # in prod: modal.Secret, not an image env
    .add_local_python_source("augura_api")
)

app = modal.App("augura-api")


@app.function(image=image)
@modal.asgi_app()
def api() -> FastAPI:
    from augura_api.main import create_app

    return create_app()
```

- [ ] **Step 4: Deploy to dev**

Run: `cd apps/api && uv run modal deploy -e dev modal_app.py`
Expected: output ending with a URL like `https://<workspace>--augura-api-api.modal.run`

- [ ] **Step 5: Verify the deployed healthcheck**

Run: `curl -s https://<workspace>--augura-api-api.modal.run/healthz`
Expected: `{"status":"ok","env":"dev","version":"0.1.0"}`

- [ ] **Step 6: Verify modal_app.py passes the quality locks**

Run: `cd apps/api && uv run ruff check . && uv run pyright`
Expected: success (modal_app.py is outside `src/` but ruff covers it; if pyright flags it, add it to `include`)

- [ ] **Step 7: Commit**

```bash
git add apps/api/modal_app.py
git commit -m "feat(deploy): Modal app — FastAPI API served in dev environment"
```

---

## Phase 1 completion criteria

- `uv run pytest`: 7 tests green
- `ruff format --check` + `ruff check` + `pyright` (strict) + `lint-imports`: all green
- CI workflow in place and replayed locally with success
- `curl <modal-url>/healthz` returns `{"status":"ok","env":"dev","version":"0.1.0"}`

## Follow-ups (separate plans, written after this phase)

- Phase 2: `core/db` + `core/auth` (JWKS) + `core/tenancy` + `studies` module + Alembic + generated TS client + `apps/web` migrated
- Phases 3-7: see spec §12
