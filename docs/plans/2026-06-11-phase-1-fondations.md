# Phase 1 — Fondations du monorepo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un monorepo `augura-platform` où la qualité est verrouillée (pyright strict, ruff, import-linter, pytest, CI) et où une app FastAPI minimale (healthcheck, config fail-fast, logging structuré, erreurs RFC 9457) est déployée sur Modal en environnement dev.

**Architecture:** Monolithe modulaire FastAPI (spec : `docs/specs/2026-06-11-augura-backend-architecture-design.md`). Cette phase ne construit que le socle `core/` (config, logging, erreurs) + la tuyauterie (uv, CI, Modal). Les packages `modules/` et `jobs/` sont créés vides pour que les contrats d'import soient actifs dès le premier jour.

**Tech Stack:** Python 3.12 · uv · FastAPI · pydantic-settings · structlog · pytest + pytest-asyncio + httpx · ruff · pyright (strict) · import-linter · Modal · GitHub Actions.

**Référence spec:** §4 (monorepo), §9 (règles), §10 (déploiement), §12 phase 1.

**Contexte d'exécution:** repo `/Users/quentin/Desktop/Augure/augura-platform` (déjà `git init`, branche `main`). Pas de worktree nécessaire : repo neuf dédié. Commits sans trailer co-author (préférence Quentin).

---

### Task 1: Scaffold du monorepo et du projet apps/api

**Files:**
- Create: `.gitignore`, `README.md`
- Create: `apps/api/` (projet uv, src layout), `apps/api/src/augura_api/{core,modules,jobs}/__init__.py`

- [ ] **Step 1: Créer le .gitignore racine**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
dist/

# Node (apps/web arrivera en phase 2)
node_modules/

# Env & outils
.env
.env.*
.DS_Store
```

- [ ] **Step 2: Créer le README racine**

```markdown
# Augura Platform

Monorepo de production d'Augura — plateforme de conception d'études cliniques.

- `apps/api` — backend FastAPI (monolithe modulaire), déployé sur Modal
- `apps/web` — frontend React (arrive en phase 2)
- `packages/api-client` — client TS généré depuis l'OpenAPI (arrive en phase 2)
- `docs/specs` — architecture validée · `docs/plans` — plans d'implémentation

Spec de référence : `docs/specs/2026-06-11-augura-backend-architecture-design.md`.
```

- [ ] **Step 3: Initialiser le projet uv en src layout**

```bash
cd /Users/quentin/Desktop/Augure/augura-platform
mkdir -p apps/api && cd apps/api
uv init --lib --name augura-api --python 3.12
```

Attendu : `uv init` crée `pyproject.toml`, `src/augura_api/__init__.py`, `.python-version`.
Puis vider le `__init__.py` généré (supprimer la fonction d'exemple s'il y en a une) :

```bash
echo '' > src/augura_api/__init__.py
rm -f src/augura_api/py.typed && touch src/augura_api/py.typed
```

- [ ] **Step 4: Créer les packages core, modules, jobs (vides mais réels)**

```bash
mkdir -p src/augura_api/core src/augura_api/modules src/augura_api/jobs tests
touch src/augura_api/core/__init__.py src/augura_api/modules/__init__.py src/augura_api/jobs/__init__.py
```

- [ ] **Step 5: Ajouter les dépendances**

```bash
uv add fastapi "uvicorn[standard]" pydantic-settings structlog
uv add --dev pytest pytest-asyncio httpx ruff pyright import-linter modal
```

Attendu : `pyproject.toml` mis à jour + `uv.lock` créé, sans erreur de résolution.

- [ ] **Step 6: Vérifier que le package s'importe**

Run: `uv run python -c "import augura_api; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
cd /Users/quentin/Desktop/Augure/augura-platform
git add .gitignore README.md apps/api
git commit -m "chore: scaffold monorepo + projet apps/api (uv, src layout)"
```

---

### Task 2: Settings fail-fast (core/config.py)

**Files:**
- Create: `apps/api/src/augura_api/core/config.py`
- Test: `apps/api/tests/core/test_config.py`

- [ ] **Step 1: Configurer pytest dans pyproject.toml**

Ajouter à `apps/api/pyproject.toml` :

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `apps/api/tests/__init__.py` vide, `apps/api/tests/core/__init__.py` vide, puis `apps/api/tests/core/test_config.py` :

```python
import pytest
from pydantic import ValidationError

from augura_api.core.config import Settings, get_settings


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    s = Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
    assert s.env == "dev"
    assert s.app_name == "augura-api"
    assert s.version == "0.1.0"


def test_settings_fails_fast_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUGURA_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue] -- l'absence d'env doit lever


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    assert get_settings() is get_settings()
```

- [ ] **Step 3: Vérifier que les tests échouent**

Run: `cd apps/api && uv run pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.core.config'`

- [ ] **Step 4: Implémenter Settings**

Créer `apps/api/src/augura_api/core/config.py` :

```python
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables AUGURA_*.

    Tout champ requis manquant fait échouer le boot (fail-fast).
    """

    model_config = SettingsConfigDict(env_prefix="AUGURA_", frozen=True)

    env: Literal["dev", "prod"]
    app_name: str = "augura-api"
    version: str = "0.1.0"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
```

- [ ] **Step 5: Vérifier que les tests passent**

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

- [ ] **Step 1: Créer la fixture d'environnement partagée**

Créer `apps/api/tests/conftest.py` :

```python
import pytest

from augura_api.core.config import get_settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chaque test démarre avec un environnement dev propre et un cache settings vide."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

Note : `test_settings_fails_fast_without_env` (Task 2) reste correct — son `delenv` s'exécute après la fixture autouse.

- [ ] **Step 2: Écrire le test qui échoue**

Créer `apps/api/tests/test_app.py` :

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

- [ ] **Step 3: Vérifier que le test échoue**

Run: `cd apps/api && uv run pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.main'`

- [ ] **Step 4: Implémenter create_app**

Créer `apps/api/src/augura_api/main.py` :

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

- [ ] **Step 5: Vérifier que le test passe**

Run: `cd apps/api && uv run pytest -v`
Expected: tous PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/conftest.py apps/api/tests/test_app.py apps/api/src/augura_api/main.py
git commit -m "feat(api): app factory + healthcheck /healthz"
```

---

### Task 4: Logging structuré + middleware request_id

**Files:**
- Create: `apps/api/src/augura_api/core/logging.py`
- Modify: `apps/api/src/augura_api/main.py`
- Test: `apps/api/tests/core/test_logging.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `apps/api/tests/core/test_logging.py` :

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

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd apps/api && uv run pytest tests/core/test_logging.py -v`
Expected: FAIL — `assert 'x-request-id' in r.headers`

- [ ] **Step 3: Implémenter le logging et le middleware (ASGI pur — pas BaseHTTPMiddleware, qui casserait le streaming SSE en phase 4)**

Créer `apps/api/src/augura_api/core/logging.py` :

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
    """Propage X-Request-ID (entrant ou généré) dans la réponse et le contexte de log."""

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

- [ ] **Step 4: Brancher dans create_app**

Remplacer le contenu de `apps/api/src/augura_api/main.py` par :

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

- [ ] **Step 5: Vérifier que tout passe**

Run: `cd apps/api && uv run pytest -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/core/logging.py apps/api/src/augura_api/main.py apps/api/tests/core/test_logging.py
git commit -m "feat(core): structlog JSON + middleware ASGI request_id"
```

---

### Task 5: Hiérarchie AppError + réponses Problem Details (RFC 9457)

**Files:**
- Create: `apps/api/src/augura_api/core/errors.py`
- Modify: `apps/api/src/augura_api/main.py`
- Test: `apps/api/tests/core/test_errors.py`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `apps/api/tests/core/test_errors.py` :

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

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd apps/api && uv run pytest tests/core/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'augura_api.core.errors'`

- [ ] **Step 3: Implémenter la hiérarchie et le handler**

Créer `apps/api/src/augura_api/core/errors.py` :

```python
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Erreur applicative de base. Sous-classer, ne jamais lever directement."""

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

- [ ] **Step 4: Brancher dans create_app**

Remplacer le contenu de `apps/api/src/augura_api/main.py` par :

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

- [ ] **Step 5: Vérifier que tout passe**

Run: `cd apps/api && uv run pytest -v`
Expected: 7 PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/core/errors.py apps/api/src/augura_api/main.py apps/api/tests/core/test_errors.py
git commit -m "feat(core): hiérarchie AppError + réponses RFC 9457"
```

---

### Task 6: Verrous qualité — pyright strict, ruff, import-linter

**Files:**
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1: Ajouter la configuration outillage à pyproject.toml**

Ajouter à `apps/api/pyproject.toml` :

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
name = "core est indépendant des modules et des jobs"
type = "forbidden"
source_modules = ["augura_api.core"]
forbidden_modules = ["augura_api.modules", "augura_api.jobs"]
```

(Le contrat « les modules ne s'importent pas entre eux » sera ajouté en phase 2 quand `modules/studies` existera — un contrat `independence` sur un package vide échoue.)

- [ ] **Step 2: Lancer ruff et corriger**

Run: `cd apps/api && uv run ruff format . && uv run ruff check --fix .`
Expected: `All checks passed!` (après reformatage éventuel)

- [ ] **Step 3: Lancer pyright et corriger**

Run: `cd apps/api && uv run pyright`
Expected: `0 errors, 0 warnings` — si des erreurs sortent, les corriger réellement (pas de `type: ignore` sans commentaire justificatif, règle spec §9)

- [ ] **Step 4: Lancer import-linter**

Run: `cd apps/api && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 5: Vérifier que les tests passent toujours**

Run: `cd apps/api && uv run pytest -q`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add apps/api/pyproject.toml apps/api/src apps/api/tests
git commit -m "chore(api): pyright strict + ruff + import-linter (contrat core)"
```

---

### Task 7: CI GitHub Actions

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Écrire le workflow**

Créer `.github/workflows/ci.yml` :

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

- [ ] **Step 2: Rejouer localement la séquence exacte de la CI**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: chaque commande sort en succès (c'est la garantie que la CI sera verte au premier push)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + typecheck + import contracts + tests"
```

---

### Task 8: Déploiement Modal (environnement dev)

**Files:**
- Create: `apps/api/modal_app.py`

- [ ] **Step 1: Vérifier l'authentification Modal**

Run: `cd apps/api && uv run modal profile current`
Expected: un nom de profil/workspace. Si erreur d'authentification : exécuter `uv run modal setup` (ouvre le navigateur) puis revérifier.

- [ ] **Step 2: Créer l'environnement dev s'il n'existe pas**

Run: `uv run modal environment list`
Si `dev` absent : `uv run modal environment create dev`
Expected: `dev` apparaît dans la liste.

- [ ] **Step 3: Écrire modal_app.py**

Créer `apps/api/modal_app.py` :

```python
import modal
from fastapi import FastAPI

# Phase 1 : deps runtime listées explicitement (3 paquets).
# Phase 2+ : basculer sur la synchro uv.lock quand la liste grossit.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi", "pydantic-settings", "structlog")
    .env({"AUGURA_ENV": "dev"})  # en prod : modal.Secret, pas une env d'image
    .add_local_python_source("augura_api")
)

app = modal.App("augura-api")


@app.function(image=image)
@modal.asgi_app()
def api() -> FastAPI:
    from augura_api.main import create_app

    return create_app()
```

- [ ] **Step 4: Déployer en dev**

Run: `cd apps/api && uv run modal deploy -e dev modal_app.py`
Expected: sortie se terminant par une URL du type `https://<workspace>--augura-api-api.modal.run`

- [ ] **Step 5: Vérifier le healthcheck déployé**

Run: `curl -s https://<workspace>--augura-api-api.modal.run/healthz`
Expected: `{"status":"ok","env":"dev","version":"0.1.0"}`

- [ ] **Step 6: Vérifier que modal_app.py passe les verrous qualité**

Run: `cd apps/api && uv run ruff check . && uv run pyright`
Expected: succès (modal_app.py est hors `src/` mais ruff le couvre ; si pyright le signale, l'ajouter à `include`)

- [ ] **Step 7: Commit**

```bash
git add apps/api/modal_app.py
git commit -m "feat(deploy): app Modal — API FastAPI servie en environnement dev"
```

---

## Critère de fin de phase 1

- `uv run pytest` : 7 tests verts
- `ruff format --check` + `ruff check` + `pyright` (strict) + `lint-imports` : tous verts
- Workflow CI en place et rejoué localement avec succès
- `curl <url-modal>/healthz` retourne `{"status":"ok","env":"dev","version":"0.1.0"}`

## Suites (plans distincts, écrits après cette phase)

- Phase 2 : `core/db` + `core/auth` (JWKS) + `core/tenancy` + module `studies` + Alembic + client TS généré + `apps/web` migré
- Phases 3-7 : voir spec §12
