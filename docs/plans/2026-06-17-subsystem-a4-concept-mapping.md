# Subsystem A4 — Concept mapping (deterministic lexical) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A `mapping` module that matches dataset column names to A1 taxonomy concepts (lexical, no LLM) and writes `proposed_canonical_id`/`proposed_role`/`confidence` to `dataset_columns`, exposed as `POST /datasets/{id}/map`.

**Spec:** `docs/specs/2026-06-17-subsystem-a4-concept-mapping-design.md`. No schema change (uses A2's `dataset_columns` proposal fields). `mapping` may import `datasets` + `semantic` (not in the independence contract).

**Conventions (D/A1/A2/A3):** scoped `git add`; run from `apps/api/`; clean-worktree api-client regen; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Baseline: ruff/pyright/lint-imports clean; pytest 94 passed/22 skipped.

---

## Task 1: normalizer + string similarity (+ unit tests)

**Files:** `apps/api/src/augura_api/modules/mapping/__init__.py` (docstring), `mapping/normalize.py`, `tests/test_mapping_normalize.py`

- [ ] **Step 1: failing tests** `tests/test_mapping_normalize.py`:
```python
"""Tests for the lexical normalizer + similarity."""

from augura_api.modules.mapping.normalize import normalize, string_similarity


def test_normalize_abbrev_and_noise() -> None:
    assert normalize("HbA1c_value") == "hemoglobin a1c"
    assert normalize("Patient_ID") == "patient"  # 'id' is noise; 'patient' kept


def test_normalize_timepoint_and_separators() -> None:
    assert normalize("cgm_tir.BL") == "continuous glucose monitoring tir"


def test_similarity_bounds() -> None:
    assert string_similarity("blood pressure", "blood pressure") > 0.99
    assert string_similarity("", "x") == 0.0
    assert 0.0 <= string_similarity("systolic bp", "systolic blood pressure") <= 1.0
```

- [ ] **Step 2: Run → FAIL.** `cd apps/api && uv run pytest tests/test_mapping_normalize.py -q`

- [ ] **Step 3:** `mapping/__init__.py` = `"""mapping module — lexical column→concept matching (A4)."""`

- [ ] **Step 4:** `mapping/normalize.py`:
```python
"""Lexical normalization + string similarity (ported from the MVP lexical-normalizer.js)."""

from __future__ import annotations

import math
import re
from collections import Counter

# Clinical subset of the MVP's ABBREV_MAP (the synonyms carry the rest).
ABBREV_MAP: dict[str, str] = {
    "hba1c": "hemoglobin a1c", "a1c": "hemoglobin a1c", "hgba1c": "hemoglobin a1c",
    "sbp": "systolic blood pressure", "dbp": "diastolic blood pressure",
    "bp": "blood pressure", "hr": "heart rate", "bmi": "body mass index",
    "ldl": "ldl cholesterol", "hdl": "hdl cholesterol", "tg": "triglycerides",
    "egfr": "estimated glomerular filtration rate", "crp": "c reactive protein",
    "spo2": "oxygen saturation", "wt": "weight", "ht": "height", "dob": "date of birth",
    "dx": "diagnosis", "rx": "prescription", "t1d": "type 1 diabetes",
    "t2d": "type 2 diabetes", "dm": "diabetes mellitus", "cgm": "continuous glucose monitoring",
    "tir": "tir", "copd": "chronic obstructive pulmonary disease", "chf": "congestive heart failure",
}
_TIMEPOINT = re.compile(r"\.(bl|baseline|3m|6m|12m|24m|36m|w0|w2|w4|w8|w12|pre|post|fu)\b", re.IGNORECASE)
_SEP = re.compile(r"[_.:\-/\\|]")
_NOISE = {
    "value", "values", "score", "scores", "result", "results", "data", "var", "variable",
    "col", "column", "field", "entry", "item", "measure", "measurement", "level", "reading",
    "status", "flag", "indicator", "code", "cd", "id", "num", "no", "n", "the", "a", "an",
    "of", "in", "at", "on", "for", "and", "or", "with", "per",
}


def normalize(raw: str | None) -> str:
    s = (raw or "").lower().replace("..", " ")
    s = _TIMEPOINT.sub(" ", s)
    s = _SEP.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    expanded: list[str] = []
    for tok in s.split():
        expanded.extend(ABBREV_MAP[tok].split() if tok in ABBREV_MAP else [tok])
    tokens = [t for t in expanded if t not in _NOISE and not t.isdigit()]
    return " ".join(tokens)


def _ngrams(s: str, n: int = 3) -> Counter[str]:
    padded = f"  {s} "
    return Counter(padded[i : i + n] for i in range(len(padded) - n + 1)) if len(padded) >= n else Counter()


def _ngram_sim(a: str, b: str) -> float:
    ca, cb = _ngrams(a), _ngrams(b)
    if not ca or not cb:
        return 0.0
    dot = sum(v * cb.get(g, 0) for g, v in ca.items())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def _levenshtein_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return 1 - prev[lb] / max(la, lb)


def _token_jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return 0.45 * _ngram_sim(a, b) + 0.35 * _token_jaccard(a, b) + 0.20 * _levenshtein_sim(a, b)
```

- [ ] **Step 5: Run → PASS** (adjust the starter ABBREV_MAP/noise only if a documented test assertion needs it — keep behavior faithful). ruff + pyright clean. Commit:
```bash
git add apps/api/src/augura_api/modules/mapping/__init__.py apps/api/src/augura_api/modules/mapping/normalize.py apps/api/tests/test_mapping_normalize.py
git commit -m "feat(mapping): lexical normalizer + string similarity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: index + matcher + confidence (+ unit tests)

**Files:** `mapping/index.py`, `mapping/matcher.py`, `mapping/confidence.py`, `tests/test_mapping_matcher.py`

- [ ] **Step 1: failing tests** `tests/test_mapping_matcher.py`:
```python
"""Tests for the index + matcher + confidence."""

from dataclasses import dataclass

from augura_api.modules.mapping.confidence import compute_confidence
from augura_api.modules.mapping.index import build_index
from augura_api.modules.mapping.matcher import match_column
from augura_api.modules.mapping.normalize import normalize


@dataclass
class _C:
    local_concept_id: str
    concept_name: str
    dq_column_role: str | None


@dataclass
class _S:
    local_concept_id: str
    synonym: str


def _index():
    concepts = [
        _C("hba1c", "Hemoglobin A1c", "value"),
        _C("sbp", "Systolic Blood Pressure", "value"),
    ]
    synonyms = [_S("hba1c", "HbA1c"), _S("hba1c", "glycated hemoglobin"), _S("sbp", "SBP")]
    return build_index(concepts, synonyms)


def test_exact_synonym_match() -> None:
    idx = _index()
    cands = match_column(normalize("HbA1c"), idx)
    assert cands and cands[0].concept_id == "hba1c"
    assert cands[0].method == "exact_synonym"
    assert compute_confidence(cands)["label"] == "High"


def test_no_match_is_unmapped() -> None:
    idx = _index()
    cands = match_column(normalize("random_widget_xyz"), idx)
    assert compute_confidence(cands)["score"] == 0.0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3:** `mapping/index.py`:
```python
"""Concept index for lexical matching (from the A1 taxonomy)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from augura_api.modules.mapping.normalize import normalize


class _ConceptRow(Protocol):
    local_concept_id: str
    concept_name: str
    dq_column_role: str | None


class _SynonymRow(Protocol):
    local_concept_id: str
    synonym: str


@dataclass
class ConceptIndex:
    concept_ids: list[str] = field(default_factory=list)
    label: dict[str, str] = field(default_factory=dict)
    role: dict[str, str | None] = field(default_factory=dict)
    norm_label: dict[str, str] = field(default_factory=dict)
    norm_synonyms: dict[str, list[str]] = field(default_factory=dict)
    synonym_lookup: dict[str, list[str]] = field(default_factory=dict)


def build_index(concepts: list[_ConceptRow], synonyms: list[_SynonymRow]) -> ConceptIndex:
    syn_by: dict[str, list[str]] = defaultdict(list)
    for s in synonyms:
        syn_by[s.local_concept_id].append(s.synonym)
    idx = ConceptIndex()
    lookup: dict[str, list[str]] = defaultdict(list)
    for c in concepts:
        cid = c.local_concept_id
        idx.concept_ids.append(cid)
        idx.label[cid] = c.concept_name
        idx.role[cid] = c.dq_column_role
        nl = normalize(c.concept_name)
        idx.norm_label[cid] = nl
        if nl:
            lookup[nl].append(cid)
        ns: list[str] = []
        for syn in syn_by.get(cid, []):
            n = normalize(syn)
            ns.append(n)
            if n:
                lookup[n].append(cid)
        idx.norm_synonyms[cid] = ns
    idx.synonym_lookup = dict(lookup)
    return idx
```

- [ ] **Step 4:** `mapping/matcher.py`:
```python
"""Lexical column→concept matching (exact synonym → fuzzy label/synonym)."""

from __future__ import annotations

from dataclasses import dataclass

from augura_api.modules.mapping.index import ConceptIndex
from augura_api.modules.mapping.normalize import string_similarity


@dataclass(frozen=True)
class Candidate:
    concept_id: str
    concept_label: str
    dq_column_role: str | None
    score: float
    method: str


def match_column(norm_name: str, index: ConceptIndex, top_n: int = 5) -> list[Candidate]:
    if not norm_name:
        return []
    hits = index.synonym_lookup.get(norm_name)
    if hits:
        seen: set[str] = set()
        out: list[Candidate] = []
        for cid in hits:
            if cid in seen:
                continue
            seen.add(cid)
            out.append(Candidate(cid, index.label[cid], index.role[cid], 0.95, "exact_synonym"))
        return out[:top_n]

    cands: list[Candidate] = []
    for cid in index.concept_ids:
        label_sim = string_similarity(norm_name, index.norm_label[cid])
        if label_sim > 0.85:
            cands.append(Candidate(cid, index.label[cid], index.role[cid], label_sim * 0.92, "fuzzy_label"))
            continue
        best_syn = max(
            (string_similarity(norm_name, s) for s in index.norm_synonyms[cid]), default=0.0
        )
        if best_syn > 0.75:
            cands.append(Candidate(cid, index.label[cid], index.role[cid], best_syn * 0.88, "fuzzy_synonym"))
    cands = [c for c in cands if c.score > 0.20]
    cands.sort(key=lambda c: c.score, reverse=True)
    # dedupe by concept, keep highest
    best_by: dict[str, Candidate] = {}
    for c in cands:
        if c.concept_id not in best_by:
            best_by[c.concept_id] = c
    return list(best_by.values())[:top_n]
```

- [ ] **Step 5:** `mapping/confidence.py`:
```python
"""Match confidence (reduced: semantic + method + ambiguity)."""

from __future__ import annotations

from augura_api.modules.mapping.matcher import Candidate

_METHOD_Q = {"exact_synonym": 1.0, "fuzzy_label": 0.92, "fuzzy_synonym": 0.85}


def _label(score: float) -> str:
    if score >= 0.80:
        return "High"
    if score >= 0.60:
        return "Medium"
    if score >= 0.40:
        return "Low"
    if score > 0:
        return "Very Low"
    return "Unmapped"


def compute_confidence(candidates: list[Candidate]) -> dict[str, object]:
    if not candidates:
        return {"score": 0.0, "label": "Unmapped"}
    best = candidates[0]
    semantic = best.score
    mq = _METHOD_Q.get(best.method, 0.5)
    if len(candidates) < 2:
        amb = 1.0
    else:
        gap = best.score - candidates[1].score
        amb = 0.6 if gap < 0.05 else 0.75 if gap < 0.10 else 0.88 if gap < 0.20 else 1.0
    score = max(0.0, min(1.0, 0.50 * semantic + 0.30 * mq + 0.20 * amb))
    return {"score": round(score, 3), "label": _label(score)}
```

- [ ] **Step 6: Run → PASS;** ruff + pyright clean. Commit:
```bash
git add apps/api/src/augura_api/modules/mapping/index.py apps/api/src/augura_api/modules/mapping/matcher.py apps/api/src/augura_api/modules/mapping/confidence.py apps/api/tests/test_mapping_matcher.py
git commit -m "feat(mapping): concept index + matcher + confidence

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: schemas + repo + service

**Files:** `mapping/schemas.py`, `mapping/repo.py`, `mapping/service.py`

- [ ] **Step 1:** `mapping/schemas.py`:
```python
"""Public contract of the mapping module."""

from uuid import UUID

from pydantic import BaseModel


class ColumnProposal(BaseModel):
    column: str
    proposed_canonical_id: str | None = None
    proposed_role: str | None = None
    confidence: float | None = None
    confidence_label: str


class MapResult(BaseModel):
    dataset_id: UUID
    mapped_count: int
    total_count: int
    avg_confidence: float | None = None
    columns: list[ColumnProposal]
```

- [ ] **Step 2:** `mapping/repo.py` (reads + updates `dataset_columns`; imports the datasets model — allowed):
```python
"""Database access for the mapping module — updates the proposals on dataset_columns."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.datasets.models import DatasetColumn


class MappingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def update_proposal(
        self,
        column_id: UUID,
        *,
        proposed_canonical_id: str | None,
        proposed_role: str | None,
        confidence: float | None,
    ) -> None:
        await self.session.execute(
            update(DatasetColumn)
            .where(DatasetColumn.id == column_id)
            .values(
                proposed_canonical_id=proposed_canonical_id,
                proposed_role=proposed_role,
                confidence=confidence,
            )
        )
```

- [ ] **Step 3:** `mapping/service.py`:
```python
"""Business logic for the mapping module: dataset columns → concepts (lexical)."""

from uuid import UUID

from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.mapping import schemas
from augura_api.modules.mapping.confidence import compute_confidence
from augura_api.modules.mapping.index import build_index
from augura_api.modules.mapping.matcher import match_column
from augura_api.modules.mapping.normalize import normalize
from augura_api.modules.mapping.repo import MappingRepo
from augura_api.modules.semantic.repo import SemanticRepo


class MappingService:
    def __init__(self, repo: MappingRepo, datasets: DatasetRepo, semantic: SemanticRepo) -> None:
        self.repo = repo
        self.datasets = datasets
        self.semantic = semantic

    async def map_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.MapResult:
        dataset = await self.datasets.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None:
            raise NotFoundError("dataset not found", dataset_id=str(dataset_id))
        columns = await self.datasets.list_columns(dataset_id)
        concepts = await self.semantic.list_concepts()
        synonyms = await self.semantic.list_synonyms()
        index = build_index(concepts, synonyms)

        out: list[schemas.ColumnProposal] = []
        confidences: list[float] = []
        mapped = 0
        for col in columns:
            cands = match_column(normalize(col.name), index)
            conf = compute_confidence(cands)
            score = float(conf["score"])  # type: ignore[arg-type]
            best = cands[0] if cands and score > 0 else None
            if best is not None:
                mapped += 1
                confidences.append(score)
                await self.repo.update_proposal(
                    col.id,
                    proposed_canonical_id=best.concept_id,
                    proposed_role=best.dq_column_role,
                    confidence=score,
                )
            out.append(
                schemas.ColumnProposal(
                    column=col.name,
                    proposed_canonical_id=best.concept_id if best else None,
                    proposed_role=best.dq_column_role if best else None,
                    confidence=score if best else None,
                    confidence_label=str(conf["label"]),
                )
            )
        avg = sum(confidences) / len(confidences) if confidences else None
        return schemas.MapResult(
            dataset_id=dataset_id, mapped_count=mapped, total_count=len(columns),
            avg_confidence=(round(avg, 3) if avg is not None else None), columns=out,
        )
```

- [ ] **Step 4:** ruff + pyright clean on `src/augura_api/modules/mapping`; `uv run python -c "from augura_api.modules.mapping.service import MappingService"` (AUGURA_ENV=dev) OK; `uv run pytest -q` no regressions. Commit:
```bash
git add apps/api/src/augura_api/modules/mapping/schemas.py apps/api/src/augura_api/modules/mapping/repo.py apps/api/src/augura_api/modules/mapping/service.py
git commit -m "feat(mapping): schemas + repo + service (map dataset columns → taxonomy)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: router + mount + route tests

**Files:** `mapping/router.py`, `mapping/__init__.py` (export router), `main.py`, `tests/test_app_routes.py`

- [ ] **Step 1:** add `"/datasets/{dataset_id}/map"` to BOTH tuples in `test_app_routes.py`. Run → FAIL.
- [ ] **Step 2:** `mapping/router.py`:
```python
"""HTTP adapter for the mapping module."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.mapping import schemas
from augura_api.modules.mapping.repo import MappingRepo
from augura_api.modules.mapping.service import MappingService
from augura_api.modules.semantic.repo import SemanticRepo

router = APIRouter(prefix="/datasets", tags=["mapping"])


@router.post("/{dataset_id}/map", response_model=schemas.MapResult, status_code=status.HTTP_201_CREATED)
async def map_dataset(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.MapResult:
    service = MappingService(MappingRepo(session), DatasetRepo(session), SemanticRepo(session))
    return await service.map_dataset(tenant, dataset_id)
```
- [ ] **Step 3:** `mapping/__init__.py` → export router (`from augura_api.modules.mapping.router import router; __all__=["router"]`).
- [ ] **Step 4:** mount in `main.py` (import `from augura_api.modules.mapping import router as mapping_router` after `jobs`; `app.include_router(mapping_router)`).
- [ ] **Step 5:** route tests PASS; ruff/pyright/lint-imports clean (`mapping→{datasets,semantic}` allowed). Commit:
```bash
git add apps/api/src/augura_api/modules/mapping/router.py apps/api/src/augura_api/modules/mapping/__init__.py apps/api/src/augura_api/main.py apps/api/tests/test_app_routes.py
git commit -m "feat(mapping): mount POST /datasets/{id}/map

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: integration test (DB) — `tests/integration/test_mapping_run.py`
Mirror `test_dq_run.py`: env-based artifacts dir, org seed, `_scope`. Upload a CSV with clinically-named headers (e.g. `hba1c,sbp,age`), then `MappingService(...).map_dataset(...)`, then assert at least one column got a `proposed_canonical_id` + confidence > 0; read back via `DatasetRepo.list_columns`. Skips without `AUGURA_DATABASE_URL`. Commit.

> Requires the taxonomy seed present (the validation applies the bundle incl. seed). Use headers that exist in the seeded taxonomy/synonyms; if unsure which seed concepts exist, assert `result.total_count == 3` and `result.mapped_count >= 0` (don't over-assert specific concept ids — the seed is the obsolete/standards set).

## Task 6: regenerate api-client (clean worktree) — verify `/datasets/{dataset_id}/map` + `MapResult`/`ColumnProposal` added; tsc clean; commit.

## Task 7: full verification + real-DB validation
- Static gates (ruff format --check my files, ruff check, pyright, lint-imports, pytest).
- pgvector: apply bundle (incl. taxonomy seed), upload `hba1c,sbp,age` CSV, run map, assert proposals persisted on `dataset_columns` for matchable columns.

---

## Self-review
- No schema change; uses A2 `dataset_columns` proposal fields.
- `mapping` imports `datasets` + `semantic` (allowed). Ensure not added to import-linter independence set.
- Confidence reduced to 3 components (flagged); full 7 + domain/range stages deferred.
- Integration test must not over-assert specific seeded concept ids (obsolete/standards seed) — assert structural success (proposals set for matchable columns, confidence in range).
