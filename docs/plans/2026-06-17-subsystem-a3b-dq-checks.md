# Subsystem A3b — remaining data-only DQ checks + table scope — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Additive to A3a (no schema/endpoint/contract change).

**Goal:** Add 5 more data-only checks to the DQ registry and extend the engine to run **table-scope** checks. Bundle shape unchanged (more findings); no DB/contract change.

**Spec:** `docs/specs/2026-06-17-subsystem-a3-dq-engine-design.md` (A3b section). MVP ref: `/tmp/augura-src/src/dq/checks/*`.

**Checks added:** `DQ_FILE_003` (non-ASCII, file), `DQ_TYPE_002` (mixed date formats, column), `DQ_MISS_002` (sentinels, column), `DQ_MISS_004` (co-missingness, table), `DQ_MISS_005` (site-concentrated missingness, table).
**Deferred:** `DQ_FILE_001` (needs parser to report unparseable rows), `DQ_MISS_007` (dataset/multi-table FK), the `dq_constraints`-gated planner, and async job → a later A3c.

**Conventions:** scoped `git add`; run from `apps/api/`; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Baseline: ruff/pyright clean, pytest 89 passed/22 skipped.

---

## Task 1: new checks + engine table-scope + unit tests (single cohesive task)

**Files:** `apps/api/src/augura_api/modules/dq/checks.py` (modify), `apps/api/src/augura_api/modules/dq/engine.py` (modify), `apps/api/tests/test_dq_checks_a3b.py` (create)

- [ ] **Step 1: Write the failing unit test** `apps/api/tests/test_dq_checks_a3b.py`:
```python
"""Tests for the A3b DQ checks (file/column/table data-only)."""

from augura_api.modules.dq.engine import run_dq
from augura_api.modules.dq.profiler import profile_column


def _ctx_col(values: list[str]):
    return {"table": "t", "column": "c", "profile": profile_column("c", values), "values": values}


def test_sentinel_check_flags_minus999() -> None:
    from augura_api.modules.dq.checks import sentinel_values

    out = sentinel_values(_ctx_col(["1", "2", "-999", "3"]))
    assert out and out[0]["check_id"] == "DQ_MISS_002"


def test_mixed_date_formats() -> None:
    from augura_api.modules.dq.checks import mixed_date_formats

    out = mixed_date_formats(_ctx_col(["2024-01-01", "01/02/2024", "2024-03-03", "04/05/2024"]))
    assert out and out[0]["check_id"] == "DQ_TYPE_002"


def test_non_ascii() -> None:
    from augura_api.modules.dq.checks import non_ascii_encoding

    out = non_ascii_encoding({"raw_bytes": "café\n".encode("utf-8")})
    assert out and out[0]["check_id"] == "DQ_FILE_003"


def test_co_missingness_table_scope() -> None:
    # two numeric columns missing on the same rows → high correlation
    sheets = [{
        "name": "data",
        "headers": ["a", "b"],
        "rows": [["1", "10"], ["", ""], ["3", "30"], ["", ""], ["5", "50"]],
    }]
    bundle = run_dq(sheets, raw_bytes=b"a,b\n", weight_profile="exploratory")
    ids = {f["check_id"] for f in bundle["provenance"]}
    assert "DQ_MISS_004" in ids


def test_engine_runs_table_scope() -> None:
    bundle = run_dq(
        [{"name": "data", "headers": ["x"], "rows": [["1"], ["2"]]}],
        raw_bytes=b"x\n", weight_profile="exploratory",
    )
    assert "table" in bundle["check_plan"]["by_scope"]
```

- [ ] **Step 2: Run → FAIL.** `cd apps/api && uv run pytest tests/test_dq_checks_a3b.py -q`

- [ ] **Step 3: Edit `checks.py`** — (a) add `import re` to the imports; (b) insert the new check functions + a `_is_missing` helper after `iqr_outliers` (before `_trigger_mostly_missing`); (c) add their registry entries.

Insert these functions:
```python
_MISSING = {"", "na", "n/a"}
_SENTINEL_NUMERIC = {-1, -99, -999, 999, 9999, 99999, -9999}
_DATE_PATTERNS = [
    ("ISO", re.compile(r"^\d{4}-\d{2}-\d{2}")),
    ("US", re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}")),
    ("European", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}")),
    ("Compact", re.compile(r"^\d{8}$")),
]


def _is_missing(v: str) -> bool:
    return v.strip().lower() in _MISSING


# ── File scope ────────────────────────────────────────────────────────────
def non_ascii_encoding(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    raw: bytes = ctx["raw_bytes"][:10240]
    positions = [i for i, b in enumerate(raw) if b > 127]
    if not positions:
        return []
    return [
        make_finding(
            check_id="DQ_FILE_003", category="file", scope="file", severity="soft",
            message="Non-ASCII characters detected — possible encoding issue",
            evidence={"count": len(positions), "first_positions": positions[:5]},
        )
    ]


# ── Column scope ──────────────────────────────────────────────────────────
def mixed_date_formats(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[str] = [v for v in ctx["values"] if v and not _is_missing(v)]
    detected: set[str] = set()
    for v in values[:200]:
        for name, pat in _DATE_PATTERNS:
            if pat.match(v.strip()):
                detected.add(name)
                break
    if len(detected) <= 1:
        return []
    return [
        make_finding(
            check_id="DQ_TYPE_002", category="type", scope="column", severity="soft",
            table=ctx["table"], column=ctx["column"],
            message=f"Mixed date formats: {', '.join(sorted(detected))}",
            evidence={"patterns": sorted(detected)},
        )
    ]


def sentinel_values(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    if p.sentinel_count == 0:
        return []
    return [
        make_finding(
            check_id="DQ_MISS_002", category="missing", scope="column", severity="soft",
            table=ctx["table"], column=p.col_name,
            message=f'"{p.col_name}": {p.sentinel_count} sentinel value(s) detected',
            evidence={"sentinel_count": p.sentinel_count},
            affected_count=p.sentinel_count,
        )
    ]


# ── Table scope ───────────────────────────────────────────────────────────
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def co_missingness(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    numeric = [c for c in ctx["columns"] if c["profile"].is_numeric]
    findings: list[dict[str, Any]] = []
    for i in range(len(numeric)):
        for j in range(i + 1, len(numeric)):
            a, b = numeric[i], numeric[j]
            av = [1.0 if _is_missing(v) else 0.0 for v in a["values"]]
            bv = [1.0 if _is_missing(v) else 0.0 for v in b["values"]]
            corr = _pearson(av, bv)
            if corr is not None and corr > 0.80:
                findings.append(
                    make_finding(
                        check_id="DQ_MISS_004", category="missing", scope="table", severity="soft",
                        table=ctx["table"], columns=[a["column"], b["column"]],
                        message=f'"{a["column"]}" and "{b["column"]}" are co-missing (r={corr:.2f})',
                        evidence={"columns": [a["column"], b["column"]], "correlation": round(corr, 3)},
                    )
                )
    return findings


def site_concentrated_missingness(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    site = next(
        (c for c in ctx["columns"] if re.search(r"site|center|arm|group", c["column"], re.I)), None
    )
    if site is None:
        return []
    findings: list[dict[str, Any]] = []
    groups = sorted({v.strip() for v in site["values"] if not _is_missing(v)})
    if len(groups) < 2:
        return []
    for col in ctx["columns"]:
        if col is site or not col["profile"].is_numeric:
            continue
        rates: dict[str, float] = {}
        for g in groups:
            idxs = [k for k, v in enumerate(site["values"]) if v.strip() == g]
            if not idxs:
                continue
            miss = sum(1 for k in idxs if _is_missing(col["values"][k]))
            rates[g] = miss / len(idxs)
        if rates and (max(rates.values()) - min(rates.values())) > 0.20:
            findings.append(
                make_finding(
                    check_id="DQ_MISS_005", category="missing", scope="table", severity="soft",
                    table=ctx["table"], column=col["column"],
                    message=f'"{col["column"]}" missing rate varies by {site["column"]}',
                    evidence={"site_column": site["column"], "by_site": rates},
                )
            )
    return findings


def _trigger_co_missing(ctx: dict[str, Any]) -> bool:
    return sum(1 for c in ctx["columns"] if c["profile"].is_numeric) >= 2


def _trigger_has_site(ctx: dict[str, Any]) -> bool:
    return any(re.search(r"site|center|arm|group", c["column"], re.I) for c in ctx["columns"])
```

Then add to `REGISTRY` (append entries):
```python
    {"id": "DQ_FILE_003", "category": "file", "scope": "file", "severity": "soft",
     "trigger": _trigger_true, "run": non_ascii_encoding},
    {"id": "DQ_TYPE_002", "category": "type", "scope": "column", "severity": "soft",
     "trigger": _trigger_true, "run": mixed_date_formats},
    {"id": "DQ_MISS_002", "category": "missing", "scope": "column", "severity": "soft",
     "trigger": _trigger_true, "run": sentinel_values},
    {"id": "DQ_MISS_004", "category": "missing", "scope": "table", "severity": "soft",
     "trigger": _trigger_co_missing, "run": co_missingness},
    {"id": "DQ_MISS_005", "category": "missing", "scope": "table", "severity": "soft",
     "trigger": _trigger_has_site, "run": site_concentrated_missingness},
```

- [ ] **Step 4: Edit `engine.py`** — (a) add `"values": values` to the column `ctx`; (b) collect `col_data` per sheet and run table-scope checks; (c) set `table_findings` + update `by_scope`.

In the column loop, change the ctx line and collect col_data:
```python
        col_data: list[dict[str, Any]] = []
        for idx, header in enumerate(headers):
            values: list[str | None] = [r[idx] if idx < len(r) else "" for r in rows]
            profile = profile_column(header, values)
            ctx = {"table": sheet["name"], "column": header, "profile": profile, "values": values}
            ...
            col_data.append({"column": header, "profile": profile, "values": values})
            table_cols.append({...})  # unchanged
        # Table scope
        table_ctx = {"table": sheet["name"], "columns": col_data}
        table_findings: list[dict[str, Any]] = []
        for check in (c for c in REGISTRY if c["scope"] == "table"):
            table_findings.extend(evaluate_check(check, table_ctx, audit))
        all_findings.extend(table_findings)
        tables.append({
            "table_label": sheet["name"], "grain": None, "columns": table_cols,
            "cross_column_findings": [], "table_findings": table_findings,
        })
```
And update `by_scope`:
```python
        "check_plan": {
            "by_scope": {"file": 2, "column": 5, "table": 2},
            "execution": {"total_registered": len(REGISTRY), "checks": list(audit.values())},
        },
```
(Note: the column `values` typing is `list[str | None]` from the engine; the checks treat them as strings — coerce with `str(v or "")` inside helpers if pyright flags `None`. Adjust `_is_missing`/loops to accept `str | None` if needed, e.g. `(v or "").strip()`.)

- [ ] **Step 5: Run tests → PASS.** `cd apps/api && uv run pytest tests/test_dq_checks_a3b.py tests/test_dq_engine.py -q`. Then `uv run ruff check src/augura_api/modules/dq tests/test_dq_checks_a3b.py`, `uv run pyright src/augura_api/modules/dq`, `uv run pytest -q` (no regressions). Run `uv run ruff format src/augura_api/modules/dq/checks.py src/augura_api/modules/dq/engine.py tests/test_dq_checks_a3b.py` and re-check.

- [ ] **Step 6: Commit**
```bash
git add apps/api/src/augura_api/modules/dq/checks.py apps/api/src/augura_api/modules/dq/engine.py apps/api/tests/test_dq_checks_a3b.py
git commit -m "feat(dq): A3b data-only checks (non-ascii, mixed-dates, sentinels, co-missing, site-missing) + table scope

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-review
- Additive only; no schema/endpoint/contract change → no api-client regen, no migration.
- `values` typing: engine yields `list[str | None]`; helpers must tolerate `None` (use `(v or "")`). Implementer adjusts to keep pyright clean.
- Table-scope checks added to engine; `by_scope` reflects file:2/column:5/table:2.
- Deferred (noted): DQ_FILE_001, DQ_MISS_007, constraint-gated planner, async job → A3c.
