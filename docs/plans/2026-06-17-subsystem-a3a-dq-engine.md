# Subsystem A3a — DQ engine (skeleton + starter checks) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A new `dq` module that re-parses a stored dataset, computes a full DQ profile, runs 4 data-only checks via a registry, scores the result, and persists a `dq_bundles` row — exposed as `POST /datasets/{id}/dq` (synchronous) + `GET /datasets/{id}/dq`.

**Architecture:** Vertical-slice `dq` module reusing A2's `parse_upload` + `core.storage` and A2's `DatasetRepo` to load the dataset. **Synchronous** run (job-engine async deferred). **Registry-based** runner (dq_constraints-gated planner deferred to A3b). Exact MVP formulas for profiler/scorer/findings.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, Postgres+RLS, pytest.

**Spec:** `docs/specs/2026-06-17-subsystem-a3-dq-engine-design.md`. MVP ref: `/tmp/augura-src/src/dq/`.

**Conventions (from D/A1/A2):** scoped `git add` only; run from `apps/api/`; api-client regen via clean worktree at HEAD; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Baseline: ruff/pyright/lint-imports clean; pytest 83 passed/21 skipped. RLS reference/tenant patterns as established. `dq` may import `datasets` (not in the data-module independence contract).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/api/supabase/schema.sql` + `policies.sql` (modify) | `dq_bundles` table (tenant-scoped) + RLS |
| `apps/api/tests/db/test_supabase_bundle.py` (modify) | `dq_bundles` in `EXPECTED_TABLES` + `RLS_REQUIRED` |
| `apps/api/src/augura_api/modules/dq/{__init__,models,schemas,config,provenance,profiler,scorer,checks,registry,engine,repo,service,router}.py` (create) | the `dq` module |
| `apps/api/src/augura_api/main.py` (modify) | mount `dq_router` |
| `apps/api/tests/test_dq_profiler.py`, `test_dq_scorer.py`, `test_dq_engine.py` (create) | unit tests |
| `apps/api/tests/test_app_routes.py` (modify) | `/datasets/{dataset_id}/dq` in OpenAPI + 401 |
| `apps/api/tests/integration/test_dq_run.py` (create) | DB integration |
| `packages/api-client/{openapi.json,src/schema.d.ts}` (regen) | contract |

---

## Task 1: dq_bundles table + RLS

- [ ] **Step 1: Bundle test** — in `tests/db/test_supabase_bundle.py` add `"dq_bundles"` to BOTH `EXPECTED_TABLES` and `RLS_REQUIRED`. Run `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q` → FAIL.

- [ ] **Step 2: schema.sql** — append (after `dataset_columns`, since it FKs `datasets`):
```sql
create table if not exists dq_bundles (
    id                  uuid primary key default gen_random_uuid(),
    org_id              uuid not null references orgs(id) on delete cascade,
    dataset_id          uuid not null references datasets(id) on delete cascade,
    score_profile       text not null default 'exploratory',
    overall_score       numeric,
    status              text not null default 'draft' check (status in ('draft', 'sealed')),
    requires_resolution boolean not null default false,
    bundle              jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists dq_bundles_dataset_idx on dq_bundles (dataset_id, created_at desc);
```

- [ ] **Step 3: policies.sql** — `dq_bundles` is tenant-scoped via `org_id`. Add it to the existing `array[...]` tenant-isolation loop (the first do-block with `tenant_isolation`), OR add explicit alter/policy mirroring `datasets`:
```sql
alter table dq_bundles enable row level security;
alter table dq_bundles force row level security;
create policy tenant_isolation on dq_bundles
    using (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
```

- [ ] **Step 4:** Run bundle tests → PASS. Commit:
```bash
git add apps/api/supabase/schema.sql apps/api/supabase/policies.sql apps/api/tests/db/test_supabase_bundle.py
git commit -m "feat(dq): dq_bundles table + tenant RLS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: profiler + config + provenance + scorer (+ unit tests)

**Files:** `dq/__init__.py` (docstring placeholder), `dq/config.py`, `dq/provenance.py`, `dq/profiler.py`, `dq/scorer.py`, `tests/test_dq_profiler.py`, `tests/test_dq_scorer.py`

- [ ] **Step 1: Write failing unit tests**

`tests/test_dq_profiler.py`:
```python
"""Tests for the full DQ profiler (quartiles, sentinels, vectors)."""

from augura_api.modules.dq.profiler import profile_column


def test_numeric_summary_quartiles() -> None:
    p = profile_column("x", [str(i) for i in range(1, 101)])  # 1..100
    assert p.is_numeric
    assert p.num_summary is not None
    assert p.num_summary.min == 1.0
    assert p.num_summary.max == 100.0
    assert p.num_summary.iqr is not None and p.num_summary.iqr > 0


def test_missing_and_sentinel() -> None:
    p = profile_column("v", ["1", "2", "", "-999", "5"])
    assert p.missing_count == 1
    assert abs(p.missing_rate - 0.2) < 1e-9
    assert p.sentinel_count == 1  # -999 is a numeric sentinel
```

`tests/test_dq_scorer.py`:
```python
"""Tests for the DQ scorer (deductions + weighted score)."""

from augura_api.modules.dq.provenance import make_finding
from augura_api.modules.dq.scorer import compute_dq_score


def test_perfect_score_no_findings() -> None:
    s = compute_dq_score([], "exploratory")
    assert s["overall"] == 1.0
    assert s["dimensions"]["completeness"]["score"] == 1.0


def test_hard_missing_finding_deducts_completeness() -> None:
    f = make_finding(check_id="DQ_MISS_003", category="missing", scope="column", severity="hard", message="x")
    s = compute_dq_score([f], "exploratory")
    # completeness loses 0.10 → 0.90; overall = 0.90*0.25 + 1.0*(0.75)
    assert s["dimensions"]["completeness"]["score"] == 0.9
    assert abs(s["overall"] - (0.9 * 0.25 + 1.0 * 0.75)) < 1e-6
```

- [ ] **Step 2: Run → FAIL.** `cd apps/api && uv run pytest tests/test_dq_profiler.py tests/test_dq_scorer.py -q`

- [ ] **Step 3: `dq/__init__.py`** = `"""dq module — data-quality engine (A3)."""`

- [ ] **Step 4: `dq/config.py`** (exact MVP values):
```python
"""DQ constants — weight profiles, dimensions, thresholds, deductions (MVP dq-config.js)."""

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "exploratory": {
        "completeness": 0.25, "validity": 0.25, "consistency": 0.20,
        "coherence": 0.15, "labelling": 0.15,
    },
    "regulatory": {
        "completeness": 0.20, "validity": 0.35, "consistency": 0.30,
        "coherence": 0.10, "labelling": 0.05,
    },
}
DIMENSION_CATEGORIES: dict[str, list[str]] = {
    "completeness": ["missing"],
    "validity": ["type", "unit", "range"],
    "consistency": ["consistency"],
    "coherence": ["coherence"],
    "labelling": ["labelling"],
}
THRESHOLDS = {"mostly_missing": 0.70, "outlier_iqr_factor": 3.0, "max_evidence_rows": 10}
SEVERITY_DEDUCTIONS = {"hard": 0.10, "soft": 0.03, "info": 0.0}
POLICY_VERSION = "1.0.0"
```

- [ ] **Step 5: `dq/provenance.py`**:
```python
"""DQ findings factory (exact shape, traceability)."""

from __future__ import annotations

from typing import Any

from augura_api.modules.dq.config import POLICY_VERSION


def make_finding(
    *,
    check_id: str,
    category: str,
    scope: str,
    severity: str,
    message: str,
    table: str | None = None,
    column: str | None = None,
    columns: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    affected_count: int | None = None,
    affected_proportion: float | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "scope": scope,
        "table": table,
        "column": column,
        "columns": columns,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
        "affected_count": affected_count,
        "affected_proportion": affected_proportion,
        "handling_status": "open",
        "policy_version": POLICY_VERSION,
    }
```

- [ ] **Step 6: `dq/profiler.py`** (full port of MVP `profiler.js`):
```python
"""Full DQ profiler — ported from the MVP profiler.js (transient, not persisted)."""

from __future__ import annotations

from dataclasses import dataclass

_MISSING = {"", "na", "n/a"}
_SAMPLE = 200
_SENTINEL_NUMERIC = {-1, -99, -999, 999, 9999, 99999, -9999}
_SENTINEL_STRING = {
    "na", "n/a", "unknown", "unk", "missing", "none", "null",
    "not applicable", "not available", "nr", "nd", "refused",
}


@dataclass(frozen=True)
class NumSummary:
    n: int
    min: float
    max: float
    mean: float
    median: float
    q1: float | None
    q3: float | None
    iqr: float | None
    std_dev: float | None


@dataclass(frozen=True)
class ColumnDQProfile:
    col_name: str
    total_count: int
    is_numeric: bool
    is_categorical: bool
    is_date: bool
    missing_count: int
    missing_rate: float
    sentinel_count: int
    numeric_values: list[float] | None
    num_summary: NumSummary | None
    unique_values: list[str] | None
    unique_count: int
    sample_values: list[str]


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_date_like(s: str) -> bool:
    import re

    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", s) or re.match(r"^\d{1,2}[/.]\d{1,2}[/.]\d{2,4}", s))


def profile_column(col_name: str, values: list[str]) -> ColumnDQProfile:
    vals = [("" if v is None else str(v)) for v in values]
    total = len(vals)
    sample = vals[:_SAMPLE]

    def frac(pred) -> float:  # noqa: ANN001
        return sum(1 for v in sample if v.strip() and pred(v)) / len(sample) if sample else 0.0

    is_numeric = frac(_is_float) >= 0.8
    is_date = (not is_numeric) and frac(_is_date_like) >= 0.8
    non_missing = [v for v in vals if v.strip().lower() not in _MISSING]
    unique_count = len(set(non_missing))
    is_categorical = (not is_numeric) and (not is_date) and bool(non_missing) and unique_count <= 50

    missing_count = sum(1 for v in vals if v.strip().lower() in _MISSING)
    missing_rate = missing_count / total if total else 0.0

    def _is_sentinel(v: str) -> bool:
        s = v.strip().lower()
        if s in _SENTINEL_STRING:
            return True
        if _is_float(v) and float(v) in _SENTINEL_NUMERIC:
            return True
        return False

    sentinel_count = sum(1 for v in vals if v.strip() and _is_sentinel(v))

    numeric_values: list[float] | None = None
    num_summary: NumSummary | None = None
    if is_numeric:
        nums = sorted(float(v) for v in non_missing if _is_float(v))
        numeric_values = nums
        if nums:
            n = len(nums)
            mean = sum(nums) / n
            q1 = nums[int(n * 0.25)]
            q3 = nums[int(n * 0.75)]
            var = sum((x - mean) ** 2 for x in nums) / (n - 1) if n > 1 else None
            num_summary = NumSummary(
                n=n, min=nums[0], max=nums[-1], mean=round(mean, 4),
                median=nums[n // 2], q1=q1, q3=q3, iqr=q3 - q1,
                std_dev=(var**0.5 if var is not None else None),
            )

    return ColumnDQProfile(
        col_name=col_name, total_count=total, is_numeric=is_numeric,
        is_categorical=is_categorical, is_date=is_date, missing_count=missing_count,
        missing_rate=missing_rate, sentinel_count=sentinel_count,
        numeric_values=numeric_values, num_summary=num_summary,
        unique_values=(sorted(set(non_missing)) if is_categorical else None),
        unique_count=unique_count, sample_values=non_missing[:5],
    )
```

- [ ] **Step 7: `dq/scorer.py`**:
```python
"""DQ scoring — per dimension + weighted overall (MVP dq-scorer.js)."""

from __future__ import annotations

from typing import Any

from augura_api.modules.dq.config import (
    DIMENSION_CATEGORIES,
    SEVERITY_DEDUCTIONS,
    WEIGHT_PROFILES,
)


def compute_dq_score(findings: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    weights = WEIGHT_PROFILES[profile]
    dimensions: dict[str, Any] = {}
    for dim, weight in weights.items():
        cats = DIMENSION_CATEGORIES[dim]
        dim_findings = [f for f in findings if f["category"] in cats]
        score = 1.0
        counts = {"hard": 0, "soft": 0, "info": 0}
        for f in dim_findings:
            sev = f["severity"]
            score = max(0.0, score - SEVERITY_DEDUCTIONS.get(sev, 0.0))
            counts[sev] = counts.get(sev, 0) + 1
        dimensions[dim] = {
            "score": round(score, 3),
            "weight": weight,
            "finding_counts": counts,
        }
    overall = sum(d["score"] * d["weight"] for d in dimensions.values())
    return {"overall": round(overall, 3), "dimensions": dimensions}
```

- [ ] **Step 8: Run unit tests → PASS** (`pytest tests/test_dq_profiler.py tests/test_dq_scorer.py -q`); `ruff check` + `pyright` on `src/augura_api/modules/dq`.

- [ ] **Step 9: Commit**
```bash
git add apps/api/src/augura_api/modules/dq/__init__.py apps/api/src/augura_api/modules/dq/config.py apps/api/src/augura_api/modules/dq/provenance.py apps/api/src/augura_api/modules/dq/profiler.py apps/api/src/augura_api/modules/dq/scorer.py apps/api/tests/test_dq_profiler.py apps/api/tests/test_dq_scorer.py
git commit -m "feat(dq): profiler + config + provenance + scorer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: checks + registry + engine (+ unit test)

**Files:** `dq/checks.py`, `dq/registry.py`, `dq/engine.py`, `tests/test_dq_engine.py`

- [ ] **Step 1: Write failing engine unit test** `tests/test_dq_engine.py`:
```python
"""End-to-end test of the DQ engine on in-memory sheets (no database)."""

from augura_api.modules.dq.engine import run_dq

SHEETS = [
    {
        "name": "data",
        "headers": ["id", "val", "flag"],
        "rows": [
            ["1", "10", "Y"], ["2", "11", "Y"], ["3", "", "N"],
            ["4", "9", "Y"], ["5", "1000", "Y"],  # 1000 = IQR outlier
        ],
    }
]


def test_run_dq_produces_scored_bundle() -> None:
    bundle = run_dq(SHEETS, raw_bytes=b"id,val,flag\n", weight_profile="exploratory")
    assert bundle["meta"]["score_profile"] == "exploratory"
    assert "dataset_fingerprint" in bundle["meta"]
    assert 0.0 <= bundle["summary"]["overall_score"] <= 1.0
    # missing-rate finding for "val" (1/5 = 20% → soft) and an IQR outlier finding
    cats = {f["category"] for f in bundle["provenance"]}
    assert "missing" in cats
    assert "range" in cats
    assert bundle["check_plan"]["execution"]["total_registered"] >= 4
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: `dq/checks.py`** (the 4 starter checks + registry entries):
```python
"""Data-only DQ checks (A3a). Each check: trigger(ctx) + run(ctx)->findings."""

from __future__ import annotations

import hashlib
from typing import Any

from augura_api.modules.dq.config import THRESHOLDS
from augura_api.modules.dq.profiler import ColumnDQProfile
from augura_api.modules.dq.provenance import make_finding


# ── File scope ────────────────────────────────────────────────────────────
def file_fingerprint(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    digest = hashlib.sha256(ctx["raw_bytes"]).hexdigest()
    return [
        make_finding(
            check_id="DQ_FILE_002", category="file", scope="file", severity="info",
            message=f"File fingerprint: {digest[:16]}…", evidence={"sha256": digest},
        )
    ]


# ── Column scope ──────────────────────────────────────────────────────────
def missing_rate(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    rate = p.missing_rate
    severity = "hard" if rate > 0.50 else "soft" if rate > 0.05 else "info"
    return [
        make_finding(
            check_id="DQ_MISS_001", category="missing", scope="column", severity=severity,
            table=ctx["table"], column=p.col_name,
            message=f'"{p.col_name}": {rate * 100:.1f}% missing',
            evidence={"missing_count": p.missing_count, "total_count": p.total_count, "missing_rate": rate},
            affected_count=p.missing_count, affected_proportion=rate,
        )
    ]


def mostly_missing(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    return [
        make_finding(
            check_id="DQ_MISS_003", category="missing", scope="column", severity="hard",
            table=ctx["table"], column=p.col_name,
            message=f'"{p.col_name}" is {p.missing_rate * 100:.0f}% missing — handling policy required',
            evidence={"missing_rate": p.missing_rate, "policy_options": ["exclude", "flag", "keep"]},
            affected_count=p.missing_count, affected_proportion=p.missing_rate,
        )
    ]


def iqr_outliers(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    ns = p.num_summary
    assert ns is not None and ns.iqr is not None and p.numeric_values is not None
    k = THRESHOLDS["outlier_iqr_factor"]
    lower, upper = ns.q1 - k * ns.iqr, ns.q3 + k * ns.iqr  # type: ignore[operator]
    low = [v for v in p.numeric_values if v < lower]
    high = [v for v in p.numeric_values if v > upper]
    total = len(low) + len(high)
    if total == 0:
        return []
    return [
        make_finding(
            check_id="DQ_RANGE_002", category="range", scope="column", severity="soft",
            table=ctx["table"], column=p.col_name,
            message=f'"{p.col_name}": {total} outlier(s) beyond Q1/Q3 ± {k}×IQR',
            evidence={
                "lower_fence": round(lower, 3), "upper_fence": round(upper, 3),
                "low_count": len(low), "high_count": len(high),
                "low_sample": low[:5], "high_sample": high[:5],
            },
            affected_count=total, affected_proportion=total / len(p.numeric_values),
        )
    ]


# id, category, scope, severity, trigger, run
REGISTRY: list[dict[str, Any]] = [
    {"id": "DQ_FILE_002", "category": "file", "scope": "file", "severity": "info",
     "trigger": lambda ctx: True, "run": file_fingerprint},
    {"id": "DQ_MISS_001", "category": "missing", "scope": "column", "severity": "info",
     "trigger": lambda ctx: True, "run": missing_rate},
    {"id": "DQ_MISS_003", "category": "missing", "scope": "column", "severity": "hard",
     "trigger": lambda ctx: ctx["profile"].missing_rate > THRESHOLDS["mostly_missing"], "run": mostly_missing},
    {"id": "DQ_RANGE_002", "category": "range", "scope": "column", "severity": "soft",
     "trigger": lambda ctx: ctx["profile"].is_numeric
     and ctx["profile"].num_summary is not None and ctx["profile"].num_summary.iqr is not None,
     "run": iqr_outliers},
]
```

- [ ] **Step 4: `dq/registry.py`** (dispatch + audit):
```python
"""DQ checks dispatch + execution audit."""

from __future__ import annotations

from typing import Any


def evaluate_check(check: dict[str, Any], ctx: dict[str, Any], audit: dict[str, Any]) -> list[dict[str, Any]]:
    item = audit.setdefault(
        check["id"], {"check_id": check["id"], "scope": check["scope"],
                      "evaluations": 0, "triggered": 0, "findings": 0, "errors": []}
    )
    item["evaluations"] += 1
    try:
        triggered = bool(check["trigger"](ctx))
    except Exception as exc:  # noqa: BLE001
        item["errors"].append(f"trigger: {exc}")
        return []
    if not triggered:
        return []
    item["triggered"] += 1
    try:
        findings = check["run"](ctx)
    except Exception as exc:  # noqa: BLE001
        item["errors"].append(f"run: {exc}")
        return []
    for f in findings:
        f.setdefault("severity", check["severity"])
    item["findings"] += len(findings)
    return findings
```

- [ ] **Step 5: `dq/engine.py`** (orchestration + bundle assembly + scoring):
```python
"""DQ engine: profile → checks (file/column) → scored bundle (A3a, sync, concept-free)."""

from __future__ import annotations

import hashlib
from typing import Any

from augura_api.modules.dq.checks import REGISTRY
from augura_api.modules.dq.config import POLICY_VERSION
from augura_api.modules.dq.profiler import profile_column
from augura_api.modules.dq.registry import evaluate_check
from augura_api.modules.dq.scorer import compute_dq_score


def run_dq(
    sheets: list[dict[str, Any]], *, raw_bytes: bytes, weight_profile: str = "exploratory"
) -> dict[str, Any]:
    audit: dict[str, Any] = {}
    fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    all_findings: list[dict[str, Any]] = []

    # File scope
    file_ctx = {"raw_bytes": raw_bytes}
    for check in (c for c in REGISTRY if c["scope"] == "file"):
        all_findings.extend(evaluate_check(check, file_ctx, audit))

    # Column scope (per sheet, per column)
    tables: list[dict[str, Any]] = []
    for sheet in sheets:
        headers: list[str] = sheet["headers"]
        rows: list[list[str]] = sheet["rows"]
        table_cols: list[dict[str, Any]] = []
        for idx, header in enumerate(headers):
            values = [r[idx] if idx < len(r) else "" for r in rows]
            profile = profile_column(header, values)
            ctx = {"table": sheet["name"], "column": header, "profile": profile}
            col_findings: list[dict[str, Any]] = []
            for check in (c for c in REGISTRY if c["scope"] == "column"):
                col_findings.extend(evaluate_check(check, ctx, audit))
            all_findings.extend(col_findings)
            outliers = next(
                (f["affected_count"] for f in col_findings if f["check_id"] == "DQ_RANGE_002"), 0
            )
            table_cols.append({
                "column": header,
                "type": ("numeric" if profile.is_numeric else "date" if profile.is_date
                         else "categorical" if profile.is_categorical else "text"),
                "missing_rate": profile.missing_rate,
                "outlier_count": outliers or 0,
                "findings": col_findings,
            })
        tables.append({
            "table_label": sheet["name"], "grain": None, "columns": table_cols,
            "cross_column_findings": [], "table_findings": [],
        })

    score = compute_dq_score(all_findings, weight_profile)
    hard_total = sum(1 for f in all_findings if f["severity"] == "hard")
    return {
        "meta": {
            "policy_version": POLICY_VERSION, "dataset_fingerprint": fingerprint,
            "score_profile": weight_profile, "status": "draft",
        },
        "summary": {
            "overall_score": score["overall"], "dimensions": score["dimensions"],
            "hard_findings_total": hard_total, "requires_resolution": hard_total > 0,
        },
        "check_plan": {
            "by_scope": {"file": 1, "column": 3},
            "execution": {"total_registered": len(REGISTRY), "checks": list(audit.values())},
        },
        "tables": tables,
        "cross_table_findings": [],
        "provenance": all_findings,
    }
```

- [ ] **Step 6: Run engine test → PASS**; ruff + pyright on the module. Commit:
```bash
git add apps/api/src/augura_api/modules/dq/checks.py apps/api/src/augura_api/modules/dq/registry.py apps/api/src/augura_api/modules/dq/engine.py apps/api/tests/test_dq_engine.py
git commit -m "feat(dq): registry + engine + 4 data-only checks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: models + schemas + repo + service

**Files:** `dq/models.py`, `dq/schemas.py`, `dq/repo.py`, `dq/service.py`

- [ ] **Step 1: `dq/models.py`**:
```python
"""SQLAlchemy model for the dq module."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class DqBundle(Base):
    __tablename__ = "dq_bundles"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    dataset_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    score_profile: Mapped[str] = mapped_column(Text, server_default=text("'exploratory'"))
    overall_score: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    requires_resolution: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bundle: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: `dq/schemas.py`**:
```python
"""Public contract of the dq module."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DqBundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    score_profile: str
    overall_score: float | None = None
    status: str
    requires_resolution: bool
    bundle: dict[str, Any]
    created_at: datetime


class DqRunResult(BaseModel):
    bundle_id: UUID
    status: str
    overall_score: float | None = None
```

- [ ] **Step 3: `dq/repo.py`**:
```python
"""Database access for the dq module."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from augura_api.core.ids import TenantId
from augura_api.modules.dq.models import DqBundle


class DqRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_bundle(
        self, tenant_id: TenantId, *, dataset_id: UUID, score_profile: str,
        overall_score: float | None, status: str, requires_resolution: bool, bundle: dict[str, Any],
    ) -> DqBundle:
        row = DqBundle(
            org_id=tenant_id, dataset_id=dataset_id, score_profile=score_profile,
            overall_score=overall_score, status=status,
            requires_resolution=requires_resolution, bundle=bundle,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def latest_for_dataset(self, tenant_id: TenantId, dataset_id: UUID) -> DqBundle | None:
        res = await self.session.execute(
            select(DqBundle)
            .where(DqBundle.org_id == tenant_id, DqBundle.dataset_id == dataset_id)
            .order_by(DqBundle.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()
```

- [ ] **Step 4: `dq/service.py`** (load dataset → read file → parse → engine → persist):
```python
"""Business logic for the dq module."""

from uuid import UUID

from augura_api.core.config import Settings
from augura_api.core.errors import NotFoundError
from augura_api.core.storage import read_bytes
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.dq import schemas
from augura_api.modules.dq.engine import run_dq
from augura_api.modules.dq.repo import DqRepo
from augura_api.modules.datasets.parsing import parse_upload
from augura_api.modules.datasets.repo import DatasetRepo


class DqService:
    def __init__(self, repo: DqRepo, datasets: DatasetRepo) -> None:
        self.repo = repo
        self.datasets = datasets

    async def run(
        self, tenant: CurrentTenant, settings: Settings, dataset_id: UUID,
        *, weight_profile: str = "exploratory",
    ) -> schemas.DqRunResult:
        dataset = await self.datasets.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None or not dataset.storage_path:
            raise NotFoundError("dataset not found or without a file", dataset_id=str(dataset_id))
        data = read_bytes(settings, dataset.storage_path)
        sheets = parse_upload(dataset.name, data)
        bundle = run_dq(
            [{"name": s.name, "headers": s.headers, "rows": s.rows} for s in sheets],
            raw_bytes=data, weight_profile=weight_profile,
        )
        row = await self.repo.create_bundle(
            tenant.tenant_id, dataset_id=dataset_id, score_profile=weight_profile,
            overall_score=bundle["summary"]["overall_score"], status=bundle["meta"]["status"],
            requires_resolution=bundle["summary"]["requires_resolution"], bundle=bundle,
        )
        return schemas.DqRunResult(
            bundle_id=row.id, status=row.status, overall_score=float(row.overall_score)
            if row.overall_score is not None else None,
        )

    async def latest(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.DqBundleOut:
        row = await self.repo.latest_for_dataset(tenant.tenant_id, dataset_id)
        if row is None:
            raise NotFoundError("no DQ bundle for this dataset", dataset_id=str(dataset_id))
        return schemas.DqBundleOut.model_validate(row)
```

- [ ] **Step 5:** `ruff check` + `pyright` on the module → clean. (No new unit test here; covered by integration + route.) Commit:
```bash
git add apps/api/src/augura_api/modules/dq/models.py apps/api/src/augura_api/modules/dq/schemas.py apps/api/src/augura_api/modules/dq/repo.py apps/api/src/augura_api/modules/dq/service.py
git commit -m "feat(dq): models + schemas + repo + service (load→parse→run→persist)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: router + mount + route tests

**Files:** `dq/router.py`, `dq/__init__.py` (export router), `main.py`, `tests/test_app_routes.py`

- [ ] **Step 1:** Add `"/datasets/{dataset_id}/dq"` to BOTH tuples in `test_app_routes.py`. Run → FAIL.

- [ ] **Step 2: `dq/router.py`**:
```python
"""HTTP adapter for the dq module."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.dq import schemas
from augura_api.modules.dq.repo import DqRepo
from augura_api.modules.dq.service import DqService

router = APIRouter(prefix="/datasets", tags=["dq"])


def _service(session: SessionDep) -> DqService:
    return DqService(DqRepo(session), DatasetRepo(session))


@router.post("/{dataset_id}/dq", response_model=schemas.DqRunResult, status_code=status.HTTP_201_CREATED)
async def run_dq(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep, settings: SettingsDep
) -> schemas.DqRunResult:
    return await _service(session).run(tenant, settings, dataset_id)


@router.get("/{dataset_id}/dq", response_model=schemas.DqBundleOut)
async def latest_dq(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.DqBundleOut:
    return await _service(session).latest(tenant, dataset_id)
```

- [ ] **Step 3:** `dq/__init__.py` → export router:
```python
"""Public interface of the dq module."""

from augura_api.modules.dq.router import router

__all__ = ["router"]
```

- [ ] **Step 4:** Mount in `main.py` (import after `documents` alphabetically: `from augura_api.modules.dq import router as dq_router`; `app.include_router(dq_router)`).

- [ ] **Step 5:** Run route tests → PASS; `ruff check`, `pyright`, `lint-imports` (dq→datasets allowed) → clean. Commit:
```bash
git add apps/api/src/augura_api/modules/dq/router.py apps/api/src/augura_api/modules/dq/__init__.py apps/api/src/augura_api/main.py apps/api/tests/test_app_routes.py
git commit -m "feat(dq): mount POST/GET /datasets/{id}/dq

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: integration test (DB)

**Files:** `tests/integration/test_dq_run.py`

- [ ] **Step 1:** Write the integration test — upload (A2 service) then run DQ, assert a `dq_bundles` row + score. Mirror `test_datasets_upload.py`'s fixture, env-based `AUGURA_ARTIFACTS_DIR` override, org seed, and `_scope`. Key body:
```python
    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await session.execute(text("insert into orgs (id, name, slug) values (cast(:i as uuid),'IT',:s)").bindparams(i=str(tenant), s="it-" + uuid4().hex[:8]))
        up = await DatasetService(DatasetRepo(session)).upload_dataset(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"), settings,
            filename="c.csv", data=b"id,val\n1,10\n2,11\n3,\n4,9\n5,1000\n", name=None, study_id=None,
        )
        res = await DqService(DqRepo(session), DatasetRepo(session)).run(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"), settings, up.dataset.id,
        )
    assert res.overall_score is not None and 0.0 <= res.overall_score <= 1.0
    async with sm() as session, session.begin():
        await _scope(session, tenant)
        latest = await DqService(DqRepo(session), DatasetRepo(session)).latest(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"), up.dataset.id,
        )
    assert latest.bundle["provenance"]
```
(Use the same imports/fixtures as `test_datasets_upload.py`; skips without `AUGURA_DATABASE_URL`.)

- [ ] **Step 2:** Run locally → SKIPPED; ruff + pyright clean. Commit:
```bash
git add apps/api/tests/integration/test_dq_run.py
git commit -m "test(dq): integration — upload → run DQ → bundle persisted

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: regenerate api-client (clean worktree) — as A1-T6/A2-T6. Verify `/datasets/{dataset_id}/dq` + `DqBundleOut`/`DqRunResult` added; tsc clean; commit.

## Task 8: full verification + real-DB validation
- Static gates (ruff format --check my files, ruff check, pyright, lint-imports, pytest — expect baseline + new dq tests passed, +1 skipped).
- pgvector: apply bundle, upload a CSV, run DQ, assert a `dq_bundles` row with `overall_score` in [0,1] + findings. (Extend the A2 validation script with the DQ run.)

---

## Self-Review (completed during planning)
- **Spec coverage:** dq_bundles+RLS (T1), profiler/config/provenance/scorer (T2), checks/registry/engine (T3), models/schemas/repo/service (T4), router+mount (T5), integration (T6), api-client (T7), validation (T8). Concept-coupled checks + constraint-planner + job-async explicitly deferred.
- **Deviations from spec (intentional, noted):** A3a runs **synchronously** (no job kind) and uses a **registry-based** runner (dq_constraints planner → A3b). Documented in the plan header.
- **Placeholders:** none — full code for every module.
- **Type/shape consistency:** finding shape (provenance) ↔ scorer category filter ↔ engine assembly ↔ bundle jsonb; `DqService.run` returns `DqRunResult`, `latest` returns `DqBundleOut`; `dq→datasets` import allowed (not in independence contract); `read_bytes(settings, storage_path)` + `parse_upload(name, data)` signatures match A2.
