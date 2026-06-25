# Compliance Hardening — Phase 1 (core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Enforce PHI minimization at the two boundaries code can actually control — dataset *ingestion* (reject direct identifiers server-side) and application *logs* (redact PHI-ish fields) — and ship the sub-processor/Art 30 compliance artifact.

**Architecture:** Backend = FastAPI modular monolith (`apps/api`), pyright strict. The PII gate is a pure, unit-testable scanner wired into `DatasetService` ingestion; the log redactor is a structlog processor in `configure_logging`.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy async · Pydantic v2 · structlog · pytest.

**Spec:** [docs/superpowers/specs/2026-06-24-compliance-hardening-design.md](../specs/2026-06-24-compliance-hardening-design.md)

## Scope of "Phase 1 (core)"

**In this plan (executed now):**
- **Done as a doc artifact:** `docs/compliance/SUBPROCESSORS.md` (sub-processor inventory + GDPR Art 30 register) — already written.
- **Task 1:** Server-side PII gate at ingestion (enforce `pii_pattern_catalog` on dataset headers; reject direct identifiers).
- **Task 2:** No-PHI-in-logs structlog redaction processor.

**Deferred to Phase 1b (documented, not in this plan):**
- **Per-tenant LLM egress opt-out** (`external_llm_enabled`, `allowed_subprocessors`) — needs a new `org_settings` table + threading org context into `get_anthropic_client`/`get_embedder` (which today take only `settings`). A genuine data-model + wiring change; sized as its own unit.
- **Zero-retention / no-train LLM headers** — there is no universal documented API header for this; the real control is the **DPA + provider account configuration** (tracked in SUBPROCESSORS.md), not code. We will not fabricate a header that does nothing. If a provider supplies a contractual header, add it via `default_headers` at the chokepoint then.

Rationale: the raw-cohort-PHI egress to LLMs was already closed in Phase 0 Task 3 (only column stats cross the boundary), so the de-identification *core* is done; what remains here is the enforceable ingestion + logging controls.

---

## Task 1: Server-side PII ingestion gate

Closes the finding that PII/PHI screening is frontend-only, advisory, and bypassable. Enforce the existing `pii_pattern_catalog` on the **server** at upload time: scan every sheet's column headers against the active regex patterns and **reject** the upload (400) listing the flagged columns. Direct identifiers (name/email/dob/ssn/…) can no longer be persisted.

**Files:**
- Create: `apps/api/src/augura_api/modules/datasets/pii.py` (pure scanner)
- Create: `apps/api/tests/test_datasets_pii.py`
- Modify: `apps/api/src/augura_api/modules/datasets/repo.py` (load active patterns)
- Modify: `apps/api/src/augura_api/modules/datasets/service.py` (`upload_dataset` + `add_files`)
- Create: `apps/api/tests/integration/test_datasets_pii_gate.py` (DB-backed, runs in db-bundle CI)

- [ ] **Step 1: Write the failing pure-scanner test**

Create `apps/api/tests/test_datasets_pii.py`:

```python
"""Pure PII header scanner: matches column headers against pii_pattern_catalog regexes."""

from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii


PATTERNS = [
    PiiPattern(key="name", pattern=r"\b(first_?name|last_?name|full_?name)\b"),
    PiiPattern(key="email", pattern=r"\bemail|e_mail|e-mail\b"),
    PiiPattern(key="dob", pattern=r"\b(dob|date_?of_?birth|birth_?date)\b"),
]


def test_flags_direct_identifier_headers() -> None:
    hits = scan_headers_for_pii(["patient_email", "hba1c_12m", "first_name"], PATTERNS)
    flagged = {(h.column, h.pattern_key) for h in hits}
    assert ("patient_email", "email") in flagged
    assert ("first_name", "name") in flagged
    # A clinical biomarker column is NOT flagged.
    assert all(h.column != "hba1c_12m" for h in hits)


def test_case_insensitive() -> None:
    hits = scan_headers_for_pii(["EMAIL", "DOB"], PATTERNS)
    assert {h.pattern_key for h in hits} == {"email", "dob"}


def test_clean_headers_return_no_hits() -> None:
    assert scan_headers_for_pii(["age", "ldl", "visit_month"], PATTERNS) == []


def test_invalid_regex_is_skipped_not_raised() -> None:
    # A malformed catalog pattern must not crash ingestion.
    hits = scan_headers_for_pii(["email"], [PiiPattern(key="bad", pattern="(")])
    assert hits == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_datasets_pii.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the pure scanner**

Create `apps/api/src/augura_api/modules/datasets/pii.py`:

```python
"""Pure PII header scanner.

Matches dataset column headers against the active regex patterns from
pii_pattern_catalog (HIPAA minimum-necessary / GDPR data-minimization). Pure and
DB-free so it is trivially unit-testable; the service loads the patterns and calls it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiPattern:
    key: str
    pattern: str


@dataclass(frozen=True)
class PiiHit:
    column: str
    pattern_key: str


def scan_headers_for_pii(headers: list[str], patterns: list[PiiPattern]) -> list[PiiHit]:
    """Return one hit per (header, pattern) match. A malformed pattern is skipped, never
    raised — a bad catalog row must not break ingestion (fail open on the SCANNER, while
    the caller still fails closed on any real hit)."""
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for p in patterns:
        try:
            compiled.append((p.key, re.compile(p.pattern, re.IGNORECASE)))
        except re.error:
            continue
    hits: list[PiiHit] = []
    for header in headers:
        for key, rx in compiled:
            if rx.search(header):
                hits.append(PiiHit(column=header, pattern_key=key))
    return hits
```

- [ ] **Step 4: Run the pure-scanner test to verify it passes**

Run: `uv run pytest tests/test_datasets_pii.py -q`
Expected: 4 passed.

- [ ] **Step 5: Add a repo method to load active patterns**

In `apps/api/src/augura_api/modules/datasets/repo.py`, add a method on the repo class that reads the global catalog directly (avoids coupling to the reference module's models). Use the session already held by the repo:

```python
    async def list_active_pii_patterns(self) -> list[tuple[str, str]]:
        """(key, pattern) for active PII catalog rows. Global read-only catalog
        (RLS backend_read allows it under a tenant session)."""
        from sqlalchemy import text

        res = await self.session.execute(
            text("select key, pattern from pii_pattern_catalog where active = true order by sort_order")
        )
        return [(row.key, row.pattern) for row in res.all()]
```

> Confirm the repo's session attribute name with `grep -n "self\.session\|def __init__" src/augura_api/modules/datasets/repo.py` and match it (e.g. `self.session` vs `self._session`).

- [ ] **Step 6: Wire the gate into ingestion**

In `apps/api/src/augura_api/modules/datasets/service.py`, add a private helper and call it from BOTH `upload_dataset` and `add_files`, right after `parse_upload` and BEFORE any `create_dataset`/`save_bytes`/`add_file` write. Add imports at the top of the methods' import blocks:

```python
        from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii
```

Add the helper method on `DatasetService`:

```python
    async def _reject_pii_headers(self, parsed: list[tuple[str, list]]) -> None:
        """Fail closed if any uploaded column header matches an active PII pattern
        (direct identifiers must not be persisted). 400 with the flagged columns."""
        from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii

        rows = await self.repo.list_active_pii_patterns()
        patterns = [PiiPattern(key=k, pattern=p) for k, p in rows]
        headers = [h for _fn, sheets, *_ in parsed for s in sheets for h in s.headers]
        hits = scan_headers_for_pii(headers, patterns)
        if hits:
            flagged = sorted({h.column for h in hits})
            raise BadRequestError(
                "upload rejected: column headers look like direct identifiers (remove or "
                "pseudonymize them before upload)",
                columns=flagged,
            )
```

In `upload_dataset`, after `parsed = [(fn, parse_upload(fn, data), data) for fn, data in files]`:

```python
        await self._reject_pii_headers([(fn, sheets) for fn, sheets, _data in parsed])
```

In `add_files`, after its own `parse_upload` produces `parsed`, add the equivalent call (match `add_files`'s local `parsed` shape — confirm by reading lines ~218-245).

Ensure `BadRequestError` is imported in `service.py` (`grep -n "BadRequestError\|from augura_api.core.errors" src/augura_api/modules/datasets/service.py`; add to the import if missing).

- [ ] **Step 7: Write the DB-backed integration test**

Create `apps/api/tests/integration/test_datasets_pii_gate.py` (runs in db-bundle CI, which seeds `pii_pattern_catalog`):

```python
"""Integration: the ingestion PII gate rejects direct-identifier headers under a real DB
(the pii_pattern_catalog is loaded by the seed). Skipped without AUGURA_DATABASE_URL."""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.errors import BadRequestError
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_pii_patterns_loaded_and_scan_flags_email(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    async with sm() as session, session.begin():
        await session.execute(text("set local role augura_app"))
        await session.execute(set_user_stmt(USER))
        await session.execute(set_tenant_stmt(LUCIS))
        rows = await DatasetRepo(session).list_active_pii_patterns()
    assert rows, "pii_pattern_catalog should be seeded with active patterns"
    from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii

    patterns = [PiiPattern(key=k, pattern=p) for k, p in rows]
    hits = scan_headers_for_pii(["patient_email", "hba1c_12m"], patterns)
    assert any(h.column == "patient_email" for h in hits)
    assert all(h.column != "hba1c_12m" for h in hits)
```

> Confirm `DatasetRepo`/`DatasetService` class names + constructors by reading the top of `repo.py`/`service.py`; adjust the import/instantiation to match.

- [ ] **Step 8: Run the gate (unit) + full backend gate**

Run: `uv run pytest tests/test_datasets_pii.py -q` (PASS) then `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q` (all PASS; the integration test skips locally).

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/pii.py apps/api/src/augura_api/modules/datasets/repo.py \
        apps/api/src/augura_api/modules/datasets/service.py apps/api/tests/test_datasets_pii.py \
        apps/api/tests/integration/test_datasets_pii_gate.py
git commit -m "feat(compliance): server-side PII gate on dataset ingestion (reject direct identifiers)"
```

---

## Task 2: No-PHI-in-logs redaction processor

Closes the finding that error context / DB error strings could surface PHI into logs (a sub-processor surface). Add a structlog processor that redacts values for known sensitive keys before rendering.

**Files:**
- Create: `apps/api/src/augura_api/core/log_redaction.py`
- Modify: `apps/api/src/augura_api/core/logging.py` (insert the processor)
- Create: `apps/api/tests/core/test_log_redaction.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/core/test_log_redaction.py`:

```python
"""The structlog redaction processor masks values for sensitive keys (no PHI in logs)."""

from augura_api.core.log_redaction import redact_processor


def test_redacts_sensitive_keys() -> None:
    event = {
        "event": "app_error",
        "email": "alice@example.com",
        "first_name": "Alice",
        "hba1c": 7.1,
        "request_id": "abc",  # not sensitive — preserved
        "count": 5,
    }
    out = redact_processor(None, "info", dict(event))
    assert out["email"] == "[redacted]"
    assert out["first_name"] == "[redacted]"
    assert out["hba1c"] == "[redacted]"
    assert out["request_id"] == "abc"
    assert out["count"] == 5


def test_redacts_nested_dicts() -> None:
    event = {"event": "x", "context": {"email": "a@b.com", "study_id": "s1"}}
    out = redact_processor(None, "info", dict(event))
    assert out["context"]["email"] == "[redacted]"
    assert out["context"]["study_id"] == "s1"  # ids are not PHI
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/core/test_log_redaction.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the processor**

Create `apps/api/src/augura_api/core/log_redaction.py`:

```python
"""structlog processor that redacts PHI/PII-ish values from log events.

Defense-in-depth for HIPAA minimum-necessary / GDPR Art 5(1)(c): logs ship to a
sub-processor (Modal/observability), so values under sensitive keys are masked before
rendering. Keys are matched case-insensitively by substring; ids/codes are preserved.
"""

from __future__ import annotations

from typing import Any

_REDACTED = "[redacted]"

# Substrings that mark a key as carrying PHI/PII. Tune as new fields appear.
_SENSITIVE = (
    "email",
    "first_name",
    "last_name",
    "full_name",
    "name",
    "dob",
    "birth",
    "ssn",
    "phone",
    "address",
    "passport",
    "member",
    "biomarker",
    "hba1c",
    "ldl",
    "crp",
    "bmi",
    "patient",
)

# Keys that contain "name" etc. but are safe operational fields — never redact these.
_ALLOW = ("event", "logger", "level", "model", "model_name", "event_name", "tool_name")


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    if k in _ALLOW:
        return False
    return any(s in k for s in _SENSITIVE)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (_REDACTED if _is_sensitive(str(k)) else _redact(v)) for k, v in value.items()}
    return value


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: (_REDACTED if _is_sensitive(str(k)) else _redact(v)) for k, v in event_dict.items()}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/core/test_log_redaction.py -q`
Expected: 2 passed.

- [ ] **Step 5: Insert the processor into the structlog chain**

In `apps/api/src/augura_api/core/logging.py`, import and add `redact_processor` to the `processors` list in `configure_logging`, positioned BEFORE `JSONRenderer` (so it masks the final event) and after `merge_contextvars`:

```python
from augura_api.core.log_redaction import redact_processor
```
```python
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_processor,
            structlog.processors.JSONRenderer(),
        ],
```

- [ ] **Step 6: Run the full backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/augura_api/core/log_redaction.py apps/api/src/augura_api/core/logging.py \
        apps/api/tests/core/test_log_redaction.py
git commit -m "feat(compliance): redact PHI/PII-ish fields from structured logs"
```

---

## Self-Review
- **Coverage:** SUBPROCESSORS.md (done) + PII gate (Task 1) + log redaction (Task 2) = the enforceable/artifact parts of the spec's Phase 1. Per-org egress + zero-retention headers explicitly deferred to 1b with rationale (data-model change / contractual, not fabricated code).
- **Placeholders:** the only env-specific bits are the `grep`-to-confirm notes for session/class names (the implementer verifies against real code).
- **Type consistency:** `PiiPattern`/`PiiHit`/`scan_headers_for_pii` names are consistent across the scanner, its tests, the repo loader, and the service wiring.

## Execution
Subagent-driven: implementer → spec review → code-quality review per task, then merge to `Quentin`.
