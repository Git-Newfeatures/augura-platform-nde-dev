# Literature Ad-hoc Search Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simple PubMed ad-hoc query on the Literature page with the rich multi-source search workbench from the old `lucis-dashboard` prototype (sources, date + study-type filters, recent queries, saved evidence, keep/dismiss, save-to-study, add-to-corpus), and remove the Browse sub-tab — wired 100 % to the real FastAPI backend.

**Architecture:** Backend = extend the existing `corpus` module: add `date_range` + `study_types` to `POST /corpus/literature/retrieve` (pure mappers in a new `filters.py`, threaded into the PubMed/CT.gov clients), add `GET /corpus/literature/snapshots` (list) and `POST /corpus/literature/ingest` (by PMIDs). Frontend = remove Browse from `CorpusPage`, add a `workspace/literature/` folder porting the old workbench, adapted to the platform's NDJSON stream (`meta → group → done`), nested `item.record` shape, and server-backed sessions/snapshots (no localStorage, no demo, no agent-activity panel, single Search button).

**Tech Stack:** Backend — FastAPI, SQLAlchemy async, Pydantic, `uv`, pytest (`httpx.MockTransport` + fake clients). Frontend — React 19, Tailwind 4, radix/shadcn primitives (`@/components/ui/*`), lucide-react, `apiFetch`/`apiJson` from `@/api`.

**Reference spec:** [docs/superpowers/specs/2026-06-19-literature-adhoc-search-port-design.md](../specs/2026-06-19-literature-adhoc-search-port-design.md)

**Old source of truth (read-only, branch `origin/corpus-live` of the sibling repo):**
```bash
git -C ~/Desktop/Augure/lucis-dashboard show origin/corpus-live:src/literature/<file>
```

**Conventions (from CLAUDE.md):**
- Comments/docstrings in French (match existing style).
- ruff line length 100; rules `E,F,I,UP,B,SIM,TID252`. pyright strict.
- CI gate (run before pushing): `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q` (in `apps/api`); `npm run lint` (in `apps/web`).
- **No commit/push/deploy unless the user explicitly asks.** Steps below include `git commit` for traceability; if the user has not authorized commits, stage the work and skip the commit step.
- No mock/demo/fallback data in `apps/web`.

---

## Phase A — Backend: date + study-type filters on `retrieve`

### Task 1: Pure filter mappers (`corpus/filters.py`)

**Files:**
- Create: `apps/api/src/augura_api/modules/corpus/filters.py`
- Test: `apps/api/tests/test_corpus_filters.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_corpus_filters.py
"""Mappers de filtres (date + type d'étude) — purs, sans réseau."""

from datetime import date

from augura_api.modules.corpus.filters import (
    SearchFilters,
    build_pubmed_term,
    ctgov_filter_params,
    pubmed_date_params,
)

TODAY = date(2026, 6, 19)


def test_empty_filters_are_noop() -> None:
    f = SearchFilters()
    assert build_pubmed_term("hba1c", f) == "hba1c"
    assert pubmed_date_params(f, TODAY) == {}
    assert ctgov_filter_params(f, TODAY) == {}
    # None aussi (chemin sans filtres)
    assert build_pubmed_term("hba1c", None) == "hba1c"
    assert pubmed_date_params(None, TODAY) == {}
    assert ctgov_filter_params(None, TODAY) == {}


def test_pubmed_term_appends_publication_types() -> None:
    f = SearchFilters(study_types=("rct", "meta_analysis"))
    assert build_pubmed_term("hba1c", f) == (
        "(hba1c) AND (Randomized Controlled Trial[pt] OR Meta-Analysis[pt])"
    )


def test_pubmed_date_params_use_year_window() -> None:
    f = SearchFilters(date_range="5y")
    assert pubmed_date_params(f, TODAY) == {
        "datetype": "pdat",
        "mindate": "2021",
        "maxdate": "2026",
    }


def test_ctgov_single_study_type_maps_to_aggfilter() -> None:
    assert ctgov_filter_params(SearchFilters(study_types=("observational",)), TODAY) == {
        "aggFilters": "studyType:obs"
    }
    assert ctgov_filter_params(SearchFilters(study_types=("rct",)), TODAY) == {
        "aggFilters": "studyType:int"
    }


def test_ctgov_both_or_unmappable_types_skip_studytype() -> None:
    # rct + observational ⇒ les deux types ⇒ pas de filtre studyType
    assert "aggFilters" not in ctgov_filter_params(
        SearchFilters(study_types=("rct", "observational")), TODAY
    )
    # systematic_review/meta_analysis n'existent pas côté CT.gov
    assert ctgov_filter_params(SearchFilters(study_types=("systematic_review",)), TODAY) == {}


def test_ctgov_date_uses_advanced_range() -> None:
    assert ctgov_filter_params(SearchFilters(date_range="10y"), TODAY) == {
        "filter.advanced": "AREA[StudyFirstPostDate]RANGE[2016-01-01,MAX]"
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_filters.py -q`
Expected: FAIL — `ModuleNotFoundError: augura_api.modules.corpus.filters`

- [ ] **Step 3: Write minimal implementation**

```python
# apps/api/src/augura_api/modules/corpus/filters.py
"""Filtres de recherche live (date + type d'étude) — mapping PUR, source-spécifique.

Aucune I/O ⇒ testable sans réseau. Le routeur construit `SearchFilters` depuis la
requête ; le retriever le passe aux clients PubMed/CT.gov, qui appliquent ces
mappers. Un filtre vide (date_range='any', study_types=()) est un no-op : la requête
part inchangée — préserve le comportement existant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

VALID_DATE_RANGES = ("any", "1y", "5y", "10y")
_YEARS_BACK = {"1y": 1, "5y": 5, "10y": 10}

# study_type Augura → terme PubMed Publication Type ([pt]).
_PUBMED_PT = {
    "rct": "Randomized Controlled Trial[pt]",
    "observational": "Observational Study[pt]",
    "systematic_review": "Systematic Review[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
}
VALID_STUDY_TYPES = tuple(_PUBMED_PT.keys())

# study_type Augura → studyType CT.gov (aggFilters). Revues/méta-analyses ne sont
# pas des types d'essai CT.gov → ignorées côté CT.gov.
_CTGOV_STUDY_TYPE = {"rct": "int", "observational": "obs"}


@dataclass(frozen=True)
class SearchFilters:
    date_range: str = "any"
    study_types: tuple[str, ...] = ()


def _from_year(date_range: str, today: date) -> int | None:
    back = _YEARS_BACK.get(date_range)
    return None if back is None else today.year - back


def build_pubmed_term(query: str, filters: SearchFilters | None) -> str:
    """Terme esearch : `(query) AND (pt OR pt)`. Sans study_types → `query` inchangée."""
    if not filters or not filters.study_types:
        return query
    pts = [_PUBMED_PT[t] for t in filters.study_types if t in _PUBMED_PT]
    if not pts:
        return query
    return f"({query}) AND ({' OR '.join(pts)})"


def pubmed_date_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """Params esearch de date (granularité année). Vide si date_range='any'."""
    if not filters:
        return {}
    year = _from_year(filters.date_range, today)
    if year is None:
        return {}
    return {"datetype": "pdat", "mindate": str(year), "maxdate": str(today.year)}


def ctgov_filter_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """Params CT.gov v2 : aggFilters studyType (1 seul type mappable) + range de date.
    Deux types int+obs sélectionnés, ou type non mappable seul → pas de studyType."""
    if not filters:
        return {}
    params: dict[str, str] = {}
    cts = {_CTGOV_STUDY_TYPE[t] for t in filters.study_types if t in _CTGOV_STUDY_TYPE}
    if len(cts) == 1:
        params["aggFilters"] = f"studyType:{next(iter(cts))}"
    year = _from_year(filters.date_range, today)
    if year is not None:
        params["filter.advanced"] = f"AREA[StudyFirstPostDate]RANGE[{year}-01-01,MAX]"
    return params
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_filters.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/filters.py apps/api/tests/test_corpus_filters.py
git commit -m "feat(corpus): pure date/study-type filter mappers for live retrieve"
```

---

### Task 2: Apply filters in the PubMed client

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/pubmed.py`
- Test: `apps/api/tests/test_corpus_pubmed.py` (add cases)

- [ ] **Step 1: Write the failing test** (append to `test_corpus_pubmed.py`)

```python
from datetime import date as _date

from augura_api.modules.corpus.filters import SearchFilters


async def test_search_applies_filters_to_term_and_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "esearch" in request.url.path:
            captured.update(dict(request.url.params))
            return httpx.Response(200, json=_ESEARCH)
        if "efetch" in request.url.path:
            return httpx.Response(200, text=_EFETCH_XML)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await NCBIPubMedClient(http).search(
            "digital engagement",
            5,
            filters=SearchFilters(date_range="5y", study_types=("rct",)),
            today=_date(2026, 6, 19),
        )

    assert captured["term"] == "(digital engagement) AND (Randomized Controlled Trial[pt])"
    assert captured["datetype"] == "pdat"
    assert captured["mindate"] == "2021"
    assert captured["maxdate"] == "2026"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_pubmed.py::test_search_applies_filters_to_term_and_params -q`
Expected: FAIL — `TypeError: search() got an unexpected keyword argument 'filters'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/pubmed.py`, update the imports line 13 (`from datetime import date`) to:

```python
from datetime import UTC, date, datetime
```

Add to the imports block (after the `import httpx` line):

```python
from augura_api.modules.corpus.filters import (
    SearchFilters,
    build_pubmed_term,
    pubmed_date_params,
)
```

Update the `PubMedClient` Protocol `search` signature:

```python
class PubMedClient(Protocol):
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[PubMedArticle]: ...

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]: ...
```

Update `_esearch` to accept extra params, and `search` to build the term + date params:

```python
    async def _esearch(self, term: str, retmax: int, *, extra: dict[str, str] | None = None) -> list[str]:
        esearch = await self._http.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=self._params(
                term=term, retmax=str(retmax), retmode="json", sort="relevance", **(extra or {})
            ),
        )
        esearch.raise_for_status()
        idlist: list[str] = esearch.json().get("esearchresult", {}).get("idlist", [])
        return idlist
```

```python
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[PubMedArticle]:
        n = max(1, min(50, max_results))
        day = today or datetime.now(UTC).date()
        term = build_pubmed_term(query, filters)
        pmids = await self._esearch(term, n, extra=pubmed_date_params(filters, day))
        if not pmids:
            return []
        return await self.fetch_by_ids(pmids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_pubmed.py -q`
Expected: PASS (all, including the 2 existing tests — they call `search` with no filters, default `None`)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/pubmed.py apps/api/tests/test_corpus_pubmed.py
git commit -m "feat(corpus): apply date/study-type filters in PubMed client"
```

---

### Task 3: Apply filters in the CT.gov client

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/ctgov.py`
- Test: `apps/api/tests/test_corpus_ctgov.py` (add a case)

- [ ] **Step 1: Write the failing test** (append to `test_corpus_ctgov.py`)

```python
from datetime import date as _date

from augura_api.modules.corpus.filters import SearchFilters


async def test_search_applies_filters_to_params() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        await client.search(
            "diabetes",
            5,
            filters=SearchFilters(date_range="1y", study_types=("observational",)),
            today=_date(2026, 6, 19),
        )

    params = record[0].url.params
    assert params.get("query.term") == "diabetes"
    assert params.get("aggFilters") == "studyType:obs"
    assert params.get("filter.advanced") == "AREA[StudyFirstPostDate]RANGE[2025-01-01,MAX]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_ctgov.py::test_search_applies_filters_to_params -q`
Expected: FAIL — `TypeError: search() got an unexpected keyword argument 'filters'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/ctgov.py`, update imports — change line 16 (`from dataclasses import dataclass`) area to also import datetime and filters:

```python
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol, cast

import httpx

from augura_api.modules.corpus.filters import SearchFilters, ctgov_filter_params
```

Update the `CTGovClient` Protocol `search` signature:

```python
class CTGovClient(Protocol):
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[CTGovStudy]: ...

    async def fetch_by_nct(self, nct_id: str) -> CTGovStudy | None: ...
```

Update the real `search`:

```python
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[CTGovStudy]:
        n = max(1, min(50, max_results))
        day = today or datetime.now(UTC).date()
        params: dict[str, str] = {"query.term": query, "pageSize": str(n), "format": "json"}
        params.update(ctgov_filter_params(filters, day))
        resp = await self._http.get(CTGOV_BASE, params=params)
        resp.raise_for_status()
        studies = _as_list(_as_dict(resp.json()).get("studies"))
        parsed = [_parse_study(_as_dict(s.get("protocolSection"))) for s in studies]
        return [s for s in parsed if s is not None]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_ctgov.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/ctgov.py apps/api/tests/test_corpus_ctgov.py
git commit -m "feat(corpus): apply date/study-type filters in CT.gov client"
```

---

### Task 4: Thread filters through the retriever

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/retrieval.py`
- Test: `apps/api/tests/test_corpus_retrieval.py` (update fakes + add a case)

- [ ] **Step 1: Update the fakes and write the failing test**

In `apps/api/tests/test_corpus_retrieval.py`, replace the two fake `search` methods so they accept (and record) the new keyword args. Change `FakePubMed.search` (lines 57-59) to:

```python
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: object = None,
        today: object = None,
    ) -> list[PubMedArticle]:
        self.calls.append(("search", query, max_results))
        self.last_filters = filters
        return self.search_res
```

Change `FakeCTGov.search` (lines 74-76) to:

```python
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: object = None,
        today: object = None,
    ) -> list[CTGovStudy]:
        self.calls.append(("search", query, max_results))
        self.last_filters = filters
        return self.search_res
```

Add `self.last_filters = None` to both `__init__` bodies (after the `self.calls = []` line). Then add this test at the end of the file:

```python
from augura_api.modules.corpus.filters import SearchFilters


async def test_topical_passes_filters_to_clients_and_captures_term() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    filters = SearchFilters(date_range="5y", study_types=("rct",))
    r = await _retriever(pm, ct).retrieve(
        "engagement and hba1c", max_results=5, today=DAY, filters=filters
    )

    # les filtres atteignent les deux clients
    assert pm.last_filters == filters
    assert ct.last_filters == filters
    # le query_string capturé reflète le terme PubMed filtré (pour le gel)
    pmg = r.groups[0]
    assert pmg.query_string == (
        "(engagement and hba1c) AND (Randomized Controlled Trial[pt])"
    )
    assert pmg.items[0].query_string == pmg.query_string
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_retrieval.py::test_topical_passes_filters_to_clients_and_captures_term -q`
Expected: FAIL — `TypeError: retrieve() got an unexpected keyword argument 'filters'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/retrieval.py`, add the import (after the `pubmed` import line 37):

```python
from augura_api.modules.corpus.filters import SearchFilters, build_pubmed_term, ctgov_filter_params
```

Update `retrieve` to accept `filters` and pass it down (known-item path ignores filters by design):

```python
    async def retrieve(
        self,
        query: str,
        *,
        sources: set[str] | None = None,
        max_results: int = 10,
        today: date | None = None,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        srcs = _normalize_sources(sources)
        day = today or datetime.now(UTC).date()
        item = classify_known_item(query)
        if item is not None:
            # known-item = lookup exact : les filtres date/type ne s'appliquent pas.
            return await self._known_item(query, item, srcs, day)
        return await self._topical(query, srcs, max_results, day, filters)
```

Update `_topical` signature + the two builder calls:

```python
    async def _topical(
        self, query: str, srcs: set[str], max_results: int, day: date, filters: SearchFilters | None
    ) -> RetrievalResult:
        builders: list[Coroutine[Any, Any, SourceGroup]] = []
        order: list[str] = []
        if SOURCE_PUBMED in srcs:
            order.append(SOURCE_PUBMED)
            builders.append(self._pubmed_topical(query, max_results, day, filters))
        if SOURCE_CTGOV in srcs:
            order.append(SOURCE_CTGOV)
            builders.append(self._ctgov_topical(query, max_results, day, filters))
        groups: list[SourceGroup] = await asyncio.gather(*builders)
        return RetrievalResult(query, order, False, None, groups)
```

Update the two topical builders to apply + capture filters:

```python
    async def _pubmed_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        # Le terme réellement envoyé à esearch (avec filtres [pt]) EST le query_string.
        term = build_pubmed_term(query, filters)
        articles = await self._pubmed.search(query, max_results, filters=filters, today=day)
        items = [
            RetrievedItem(SOURCE_PUBMED, a.pmid, a.title, term, day, _pubmed_record(a))
            for a in articles
        ]
        return SourceGroup(SOURCE_PUBMED, term, items)

    async def _ctgov_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        extra = ctgov_filter_params(filters, day)
        suffix = "".join(f"&{k}={v}" for k, v in sorted(extra.items()))
        qs = f"query.term={query}{suffix}"  # chaîne API CT.gov réellement envoyée
        studies = await self._ctgov.search(query, max_results, filters=filters, today=day)
        items = [
            RetrievedItem(SOURCE_CTGOV, s.nct_id, s.title, qs, day, _ctgov_record(s))
            for s in studies
        ]
        return SourceGroup(SOURCE_CTGOV, qs, items)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_retrieval.py -q`
Expected: PASS (all — existing tests use no filters, so `build_pubmed_term`/`ctgov_filter_params` are no-ops and the old `query_string` assertions still hold)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/retrieval.py apps/api/tests/test_corpus_retrieval.py
git commit -m "feat(corpus): thread date/study-type filters through the retriever"
```

---

### Task 5: Expose filters on the retrieve endpoint

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py:129-133`
- Modify: `apps/api/src/augura_api/modules/corpus/router.py` (`literature_retrieve`, helpers)
- Test: `apps/api/tests/test_corpus_retrieve_request.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_corpus_retrieve_request.py
"""Validation de la requête retrieve + construction des SearchFilters côté routeur."""

import pytest

from augura_api.core.errors import BadRequestError
from augura_api.modules.corpus.filters import SearchFilters
from augura_api.modules.corpus.router import _build_filters


def test_build_filters_defaults_to_any() -> None:
    assert _build_filters("any", []) == SearchFilters(date_range="any", study_types=())


def test_build_filters_normalizes_lists_to_tuples() -> None:
    f = _build_filters("5y", ["rct", "observational"])
    assert f == SearchFilters(date_range="5y", study_types=("rct", "observational"))


def test_build_filters_rejects_bad_date_range() -> None:
    with pytest.raises(BadRequestError):
        _build_filters("yesterday", [])


def test_build_filters_rejects_bad_study_type() -> None:
    with pytest.raises(BadRequestError):
        _build_filters("any", ["cohort"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_retrieve_request.py -q`
Expected: FAIL — `ImportError: cannot import name '_build_filters'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/schemas.py`, extend `LiteratureRetrieveRequest` (lines 129-133):

```python
class LiteratureRetrieveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    # Défaut : les deux sources. Validé côté service (source inconnue → 400).
    sources: list[str] | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    # Filtres v0 : fenêtre de date + types d'étude. Validés côté routeur (_build_filters).
    date_range: str = "any"
    study_types: list[str] = Field(default_factory=list)
```

In `apps/api/src/augura_api/modules/corpus/router.py`, add the import (in the corpus imports block):

```python
from augura_api.modules.corpus.filters import (
    VALID_DATE_RANGES,
    VALID_STUDY_TYPES,
    SearchFilters,
)
```

Add the helper near `_validate_sources` (after line 44):

```python
def _build_filters(date_range: str, study_types: list[str]) -> SearchFilters:
    if date_range not in VALID_DATE_RANGES:
        raise BadRequestError("date_range invalide", value=date_range)
    unknown = [t for t in study_types if t not in VALID_STUDY_TYPES]
    if unknown:
        raise BadRequestError("study_type inconnu", value=unknown)
    return SearchFilters(date_range=date_range, study_types=tuple(study_types))
```

Update `literature_retrieve` (the body around lines 156-166) to build and pass filters:

```python
    _validate_sources(req.sources)  # 400 avant le stream si source inconnue
    filters = _build_filters(req.date_range, req.study_types)
    sources = set(req.sources) if req.sources else None

    async def gen() -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=20.0) as http:
            retriever = LiteratureRetriever(
                NCBIPubMedClient(http, api_key=settings.ncbi_api_key), CTGovApiClient(http)
            )
            result = await retriever.retrieve(
                req.query, sources=sources, max_results=req.max_results, filters=filters
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_retrieve_request.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/schemas.py apps/api/src/augura_api/modules/corpus/router.py apps/api/tests/test_corpus_retrieve_request.py
git commit -m "feat(corpus): accept date_range/study_types on POST /corpus/literature/retrieve"
```

---

## Phase B — Backend: list snapshots + ingest by PMIDs

### Task 6: List saved snapshots (`GET /corpus/literature/snapshots`)

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/live_repo.py` (add `list_snapshots`)
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py` (add `SnapshotSummary`)
- Modify: `apps/api/src/augura_api/modules/corpus/snapshot_service.py` (add `list_snapshots`)
- Modify: `apps/api/src/augura_api/modules/corpus/router.py` (add route)
- Test: `apps/api/tests/test_corpus_snapshot_list.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_corpus_snapshot_list.py
"""LiteratureSnapshotService.list_snapshots : mappe les lignes en SnapshotSummary."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus.live_repo import LiveRepo
from augura_api.modules.corpus.models import LiteratureSnapshot
from augura_api.modules.corpus.snapshot_service import LiteratureSnapshotService

TENANT = CurrentTenant(
    tenant_id=TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44")),
    user_id=UserId(UUID("11111111-1111-4111-8111-111111111111")),
    role="member",
)


def _row(query: str, n: int) -> LiteratureSnapshot:
    row = LiteratureSnapshot()
    row.id = uuid4()
    row.org_id = TENANT.tenant_id
    row.study_id = None
    row.created_by = TENANT.user_id
    row.created_at = datetime(2026, 6, 19, tzinfo=UTC)
    row.content_hash = "abc"
    row.payload = {
        "query": query,
        "sources": ["pubmed"],
        "results": [{"id": str(i)} for i in range(n)],
    }
    return row


class FakeLiveRepo:
    def __init__(self, rows: list[LiteratureSnapshot]) -> None:
        self.rows = rows
        self.calls: list[object] = []

    async def list_snapshots(self, tenant_id: TenantId, *, study_id: object = None):
        self.calls.append((tenant_id, study_id))
        return self.rows


async def test_list_snapshots_maps_to_summaries() -> None:
    repo = FakeLiveRepo([_row("glp-1 in heart failure", 3), _row("hba1c", 0)])
    service = LiteratureSnapshotService(cast(LiveRepo, repo))
    out = await service.list_snapshots(TENANT)

    assert [s.query for s in out] == ["glp-1 in heart failure", "hba1c"]
    assert out[0].result_count == 3
    assert out[1].result_count == 0
    assert out[0].sources == ["pubmed"]
    assert repo.calls == [(TENANT.tenant_id, None)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_snapshot_list.py -q`
Expected: FAIL — `AttributeError: 'LiteratureSnapshotService' object has no attribute 'list_snapshots'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/schemas.py`, add after `LiteratureSnapshot` (after line 200):

```python
class SnapshotSummary(BaseModel):
    """Vue légère pour la liste « Saved evidence » : pas de results ni de hash."""

    id: UUID
    study_id: UUID | None = None
    query: str
    sources: list[str]
    result_count: int
    created_at: datetime
```

In `apps/api/src/augura_api/modules/corpus/live_repo.py`, add to `LiveRepo` (after `get_snapshot`, around line 62):

```python
    async def list_snapshots(
        self, tenant_id: TenantId, *, study_id: UUID | None = None
    ) -> list[LiteratureSnapshot]:
        stmt = select(LiteratureSnapshot).where(LiteratureSnapshot.org_id == tenant_id)
        if study_id is not None:
            stmt = stmt.where(LiteratureSnapshot.study_id == study_id)
        res = await self.session.execute(stmt.order_by(LiteratureSnapshot.created_at.desc()))
        return list(res.scalars().all())
```

In `apps/api/src/augura_api/modules/corpus/snapshot_service.py`, add to `LiteratureSnapshotService` (after `read_snapshot`, before `_to_snapshot`):

```python
    async def list_snapshots(
        self, tenant: CurrentTenant, *, study_id: UUID | None = None
    ) -> list[schemas.SnapshotSummary]:
        rows = await self.repo.list_snapshots(tenant.tenant_id, study_id=study_id)
        return [
            schemas.SnapshotSummary(
                id=r.id,
                study_id=r.study_id,
                query=r.payload["query"],
                sources=r.payload["sources"],
                result_count=len(r.payload.get("results", [])),
                created_at=r.created_at,
            )
            for r in rows
        ]
```

In `apps/api/src/augura_api/modules/corpus/router.py`, add the route immediately **before** `read_snapshot` (before line 191) so the static `/snapshots` path is declared before the `/{snapshot_id}` path:

```python
@router.get("/literature/snapshots", response_model=list[schemas.SnapshotSummary])
async def list_snapshots(
    tenant: CurrentTenantDep, session: SessionDep, study_id: UUID | None = None
) -> list[schemas.SnapshotSummary]:
    """Liste les preuves gelées du tenant (vue légère, sans results ni recalcul de hash)."""
    return await _live_service(session).list_snapshots(tenant, study_id=study_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_snapshot_list.py -q`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/live_repo.py apps/api/src/augura_api/modules/corpus/schemas.py apps/api/src/augura_api/modules/corpus/snapshot_service.py apps/api/src/augura_api/modules/corpus/router.py apps/api/tests/test_corpus_snapshot_list.py
git commit -m "feat(corpus): GET /corpus/literature/snapshots (saved-evidence list)"
```

---

### Task 7: Ingest specific PubMed records (`POST /corpus/literature/ingest`)

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/service.py` (refactor ingest loop into `_ingest_articles`, add `ingest_by_ids`)
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py` (add `LiteratureIngestRequest`)
- Modify: `apps/api/src/augura_api/modules/corpus/router.py` (add route)
- Test: `apps/api/tests/test_corpus_literature.py` (add a case)

- [ ] **Step 1: Write the failing test** (append to `test_corpus_literature.py`)

First extend the `FakePubMed` in that file to support `fetch_by_ids` — replace its body (lines 36-41) with:

```python
class FakePubMed:
    def __init__(self, articles: list[PubMedArticle]) -> None:
        self._articles = articles

    async def search(self, query: str, max_results: int, **_kw: object) -> list[PubMedArticle]:
        return self._articles[:max_results]

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]:
        return [a for a in self._articles if a.pmid in pmids]
```

Then add the test:

```python
async def test_ingest_by_ids_fetches_and_ingests() -> None:
    repo = FakeRepo()
    res = await _service(repo).ingest_by_ids(TENANT, pmids=["1"])
    assert (res.found, res.ingested) == (1, 1)
    assert {d.url for d in res.documents} == {"https://doi.org/10.1/a"}
    # idempotent : même PMID déjà ingéré ⇒ 0 nouvelle ingestion
    res2 = await _service(repo).ingest_by_ids(TENANT, pmids=["1"])
    assert (res2.found, res2.ingested) == (1, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_corpus_literature.py::test_ingest_by_ids_fetches_and_ingests -q`
Expected: FAIL — `AttributeError: 'LiteratureService' object has no attribute 'ingest_by_ids'`

- [ ] **Step 3: Write minimal implementation**

In `apps/api/src/augura_api/modules/corpus/service.py`, refactor `LiteratureService`. Replace the body of `search_and_ingest` (lines 273-326) so the ingestion loop becomes a shared helper, and add `ingest_by_ids`:

```python
    async def search_and_ingest(
        self,
        tenant: CurrentTenant,
        *,
        query: str,
        max_results: int,
        effective_query: str | None = None,
    ) -> schemas.LiteratureSearchResult:
        eq = (effective_query or query).strip()
        articles = await self.pubmed.search(eq, max_results)
        return await self._ingest_articles(tenant, articles, query=query, effective_query=eq)

    async def ingest_by_ids(
        self, tenant: CurrentTenant, *, pmids: list[str]
    ) -> schemas.LiteratureSearchResult:
        """Ingère des enregistrements PubMed précis (efetch par PMID), sans recherche.
        Sert « Add to corpus » sur des résultats de retrieve déjà sélectionnés."""
        articles = await self.pubmed.fetch_by_ids(pmids)
        return await self._ingest_articles(
            tenant, articles, query=",".join(pmids), effective_query=",".join(pmids)
        )

    async def _ingest_articles(
        self,
        tenant: CurrentTenant,
        articles: list[PubMedArticle],
        *,
        query: str,
        effective_query: str,
    ) -> schemas.LiteratureSearchResult:
        today = datetime.now(UTC).date()
        ingested: list[Document] = []
        embedded_any = False
        for art in articles:
            if art.url and await self.repo.find_document_by_url(tenant.tenant_id, art.url):
                continue  # déjà ingéré pour ce tenant
            doc = await self.repo.insert_document(
                tenant.tenant_id,
                source_id="pubmed",
                title=art.title,
                summary=art.abstract or None,
                url=art.url,
                evidence_type=art.evidence_type,
                published_at=art.published_at,
                is_new=True,
            )
            content = (art.title + (f"\n\n{art.abstract}" if art.abstract else "")).strip()
            embedding: list[float] | None = None
            if self.embedder is not None:
                try:
                    embedding = await self.embedder.embed(content)
                    embedded_any = True
                except (AgentUpstreamError, AgentInvalidOutput):
                    embedding = None
            await self.repo.add_chunk(
                doc.id, tenant.tenant_id, content=content, embedding=embedding
            )
            ingested.append(doc)
        documents = [
            schemas.FeedDocument(
                id=d.id,
                source_id=d.source_id,
                evidence_type=d.evidence_type,
                jurisdiction=d.jurisdiction,
                lifecycle=d.lifecycle,
                title=d.title,
                summary=d.summary,
                url=d.url,
                published_at=d.published_at,
                is_new=d.is_new,
                age_label=_age_label(d.published_at, today),
            )
            for d in ingested
        ]
        return schemas.LiteratureSearchResult(
            query=query,
            effective_query=effective_query,
            found=len(articles),
            ingested=len(ingested),
            embedded=embedded_any,
            documents=documents,
        )
```

Add the import for `PubMedArticle` at the top of `service.py` — change line 23 (`from augura_api.modules.corpus.pubmed import PubMedClient`) to:

```python
from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient
```

In `apps/api/src/augura_api/modules/corpus/schemas.py`, add after `LiteratureSearchResult` (after line 119):

```python
class LiteratureIngestRequest(BaseModel):
    pmids: list[str] = Field(min_length=1, max_length=50)
```

In `apps/api/src/augura_api/modules/corpus/router.py`, add a route after the `literature` endpoint (after line 141):

```python
@router.post("/literature/ingest", response_model=schemas.LiteratureSearchResult)
async def literature_ingest(
    req: schemas.LiteratureIngestRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.LiteratureSearchResult:
    """Ingère des enregistrements PubMed précis (par PMID) dans le corpus du tenant.
    Sert « Add to corpus » sur des résultats de retrieve gardés (PubMed only)."""
    embedder: Embedder | None = None
    try:
        embedder = get_embedder(settings)
    except AgentUpstreamError:
        embedder = None
    async with httpx.AsyncClient(timeout=20.0) as http:
        pubmed = NCBIPubMedClient(http, api_key=settings.ncbi_api_key)
        service = LiteratureService(CorpusRepo(session), pubmed, embedder=embedder)
        return await service.ingest_by_ids(tenant, pmids=req.pmids)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_corpus_literature.py -q`
Expected: PASS (all, incl. the new ingest test)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/corpus/service.py apps/api/src/augura_api/modules/corpus/schemas.py apps/api/src/augura_api/modules/corpus/router.py apps/api/tests/test_corpus_literature.py
git commit -m "feat(corpus): POST /corpus/literature/ingest (add-to-corpus by PMIDs)"
```

---

### Task 8: Full backend gate + OpenAPI regen

**Files:**
- Modify: `packages/api-client/openapi.json` (generated)
- Modify: `packages/api-client/src/schema.d.ts` (generated)

- [ ] **Step 1: Run the full API gate**

Run: `cd apps/api && uv run ruff format . && uv run ruff check --fix . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all green. Fix any ruff/pyright issues surfaced (e.g. unused imports) before continuing.

- [ ] **Step 2: Regenerate the OpenAPI contract**

Run: `cd apps/api && uv run python scripts/dump_openapi.py`
Expected: `packages/api-client/openapi.json` updated (new `date_range`/`study_types` on retrieve, `SnapshotSummary`, `/literature/snapshots` GET, `/literature/ingest` POST).

- [ ] **Step 3: Regenerate the TS client**

Run: `npm --prefix packages/api-client run generate`
Expected: `packages/api-client/src/schema.d.ts` updated. **Never hand-edit it.**

- [ ] **Step 4: Verify the drift check would pass**

Run: `cd apps/api && uv run python scripts/dump_openapi.py && git diff --stat packages/api-client/openapi.json`
Expected: no further diff after a second dump (contract is stable).

- [ ] **Step 5: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate OpenAPI for corpus literature filters + endpoints"
```

---

## Phase C — Frontend: remove Browse

### Task 9: Strip the Browse sub-tab from CorpusPage

**Files:**
- Modify: `apps/web/src/workspace/CorpusPage.jsx`

This task only removes Browse and rewires the page shell; the `AdHocQuery` function is replaced in Task 16. After this task the page keeps two tabs (Ad-hoc query default + Study matches) and no longer fetches `corpus_coverage`.

- [ ] **Step 1: Replace `CorpusPage.jsx` with the Browse-free shell**

Replace the entire file `apps/web/src/workspace/CorpusPage.jsx` with the following (this keeps `AdHocQuery` and `SemanticSearch` as-is for now; Task 16 swaps `AdHocQuery` for `LiteratureWorkbench`):

```jsx
import { useState } from 'react'
import { Target, Search as SearchIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SubTabs } from '@/cockpit/SubTabs'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { Loading } from '@/workspace/CollectionStates'
import { openSearch } from '@/shell/searchBus'
import { AdHocQuery } from '@/workspace/literature/AdHocQuery'
import { SemanticSearch } from '@/workspace/literature/SemanticSearch'

export function CorpusPage() {
  const { data: sources, loading } = useCollection('corpus_sources')
  const total = sources.reduce((sum, s) => sum + (s.count || 0), 0)
  const [sub, setSub] = useState('query')

  return (
    <WorkspacePage
      eyebrow="Evidence base"
      title="Literature"
      sub={
        loading
          ? 'Loading…'
          : total
            ? `${total.toLocaleString()} indexed documents across ${sources.length} sources`
            : 'Tenant-wide evidence knowledge base'
      }
      action={<Button variant="outline" onClick={openSearch}>Search</Button>}
    >
      {loading && sources.length === 0 ? (
        <Loading />
      ) : (
        <>
          <SubTabs
            tabs={[
              { id: 'query',   label: 'Ad-hoc query',  icon: <SearchIcon size={14} /> },
              { id: 'matches', label: 'Study matches', icon: <Target size={14} /> },
            ]}
            active={sub}
            onChange={setSub}
          />
          {sub === 'query' && <AdHocQuery />}
          {sub === 'matches' && <SemanticSearch />}
        </>
      )}
    </WorkspacePage>
  )
}
```

> Note: this shell imports only what it uses (`Loading`, `Target`, `SearchIcon`, `Button`, `SubTabs`, `WorkspacePage`, `useCollection`, `openSearch`, `AdHocQuery`, `SemanticSearch`). The old Browse-only imports (`Library`, `EmptyState`, `corpus_coverage` fetch, `CORPUS_ICON`, `BookOpen`/`FlaskConical`/`Shield`/`FileText`) are gone. `AdHocQuery` resolves only after Task 14 — the app builds after Phase D.

- [ ] **Step 2: Move `SemanticSearch` into the literature folder**

The old `SemanticSearch` function currently lives inline in `CorpusPage.jsx`. Recover it from git and extract it:

Run: `git show HEAD:apps/web/src/workspace/CorpusPage.jsx > /tmp/old_corpus_page.jsx`

Create `apps/web/src/workspace/literature/SemanticSearch.jsx` containing the `SemanticSearch` function (lines 121-202 of the old file) plus its imports. Exact content:

```jsx
import { useState } from 'react'
import { Target, Search as SearchIcon } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/workspace/CollectionStates'
import { apiJson } from '@/api'

// ── Recherche sémantique (pgvector) ───────────────────────────────────────────
// POST /corpus/search : embed-on-server puis match vectoriel scopé tenant.
export function SemanticSearch() {
  const [q, setQ] = useState('')
  const [running, setRunning] = useState(false)
  const [hits, setHits] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    if (!q.trim() || running) return
    setRunning(true); setError(null); setHits(null)
    try {
      const res = await apiJson('/corpus/search', {
        method: 'POST',
        body: JSON.stringify({ query: q.trim(), match_count: 20 }),
      })
      setHits(Array.isArray(res) ? res : [])
    } catch (e) {
      const m = String(e?.message || '')
      setError(m.includes('503')
        ? 'Semantic search unavailable: the embedding API key isn\'t configured yet.'
        : 'Search failed — check your connection.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Semantic search across your corpus.</strong>{' '}
        Find the most relevant indexed passages by meaning (pgvector), scoped to your tenant.
      </div>
      <Card className="gap-0 rounded-xl border p-5">
        <textarea
          rows={2}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
          placeholder="e.g. effect of engagement on HbA1c reduction"
          className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setQ(''); setHits(null); setError(null) }}>Clear</Button>
          <Button onClick={run} disabled={running || !q.trim()}>
            <SearchIcon className="h-3.5 w-3.5" /> {running ? 'Searching…' : 'Search corpus'}
          </Button>
        </div>
      </Card>
      {error && (
        <Card className="gap-0 rounded-xl border p-4 text-[12.5px] text-[#C0392B]" style={{ borderLeft: '3px solid #C0392B' }}>
          {error}
        </Card>
      )}
      {hits && (hits.length === 0 ? (
        <EmptyState icon={Target} title="No matches" subtitle="No indexed passages matched this query." />
      ) : (
        <Card className="gap-0 rounded-xl border p-5">
          <div className="flex flex-col gap-3">
            {hits.map((h) => (
              <div key={h.id} className="flex items-start gap-2.5 border-b border-border/60 pb-3 last:border-0 last:pb-0">
                <Badge variant="outline" className="mt-px flex-shrink-0 text-[10px] font-normal text-muted-foreground">
                  {h.source_id || 'corpus'}
                </Badge>
                <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-foreground/85">
                  {h.title && <span className="font-medium text-foreground">{h.title} · </span>}
                  {String(h.content || '').slice(0, 240)}
                </span>
                {h.similarity != null && (
                  <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground/70">
                    {Math.round(h.similarity * 100)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
```

> The `CorpusPage.jsx` from Step 1 imports `AdHocQuery` and `SemanticSearch` from `@/workspace/literature/*`. `SemanticSearch` exists after this step; `AdHocQuery` is created in Task 16. The app will not build cleanly until Task 16 — that's expected; complete Phase D before running the app.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/CorpusPage.jsx apps/web/src/workspace/literature/SemanticSearch.jsx
git commit -m "refactor(web): remove Browse tab; extract SemanticSearch to literature/"
```

---

## Phase D — Frontend: literature workbench

All files in this phase live under `apps/web/src/workspace/literature/`. Ported components keep the platform's shadcn imports (`@/components/ui/{card,button,badge}`, `@/lib/utils` `cn`) — identical to the old repo, so imports need no change unless noted.

### Task 10: Literature API client + record helpers

**Files:**
- Create: `apps/web/src/workspace/literature/literatureClient.js`

- [ ] **Step 1: Create the client**

```js
// apps/web/src/workspace/literature/literatureClient.js
//
// Client du workbench Littérature, branché sur le vrai backend FastAPI :
//   - retrieve  → POST /corpus/literature/retrieve (stream NDJSON: meta|group|done)
//   - sessions  → POST/GET /corpus/literature/sessions(+events)   (Recent queries + audit)
//   - snapshots → POST/GET /corpus/literature/snapshots(/{id})    (Saved evidence)
//   - ingest    → POST /corpus/literature/ingest                  (Add to corpus, PubMed)
// Pas de mode démo, pas de localStorage : tout vient du backend (règle no-mock).
import { apiFetch, apiJson } from '@/api'

// id stable d'un résultat across sources (pmid pour PubMed, nct_id pour CT.gov).
export const resultId = (r) => r.pmid || r.nct_id || r.id || ''

// Aplati un item backend (record imbriqué) → forme plate attendue par les cartes
// (r.pmid, r.abstract…). Conserve source/id/query_string/retrieval_date/record pour
// reconstruire un FrozenResult au moment du Save.
export function flattenItem(item) {
  const rec = item.record || {}
  return {
    source: item.source,
    id: item.id,
    title: item.title,
    query_string: item.query_string,
    retrieval_date: item.retrieval_date,
    record: rec,
    annotation: item.annotation ?? null,
    ...rec,
    publication_date: rec.published_at ?? null,
  }
}

// Stream NDJSON du retrieve. onEvent reçoit {type:'meta'|'group'|'done'|'error', ...}.
export async function streamRetrieve({ query, sources, dateRange, studyTypes, maxResults = 10, signal, onEvent }) {
  const body = JSON.stringify({
    query,
    sources: sources && sources.length ? sources : undefined,
    date_range: dateRange || 'any',
    study_types: studyTypes || [],
    max_results: maxResults,
  })
  let res
  try {
    res = await apiFetch('/corpus/literature/retrieve', { method: 'POST', body, signal })
  } catch (e) {
    if (e?.name === 'AbortError') return
    onEvent({ type: 'error', text: String(e?.message || e) })
    return
  }
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    onEvent({ type: 'error', text: `HTTP ${res.status} ${detail.slice(0, 200)}` })
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  const emit = (raw) => { try { onEvent(JSON.parse(raw)) } catch { /* ligne partielle */ } }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) { const raw = line.trim(); if (raw) emit(raw) }
    }
    if (buf.trim()) emit(buf.trim())
  } catch (e) {
    if (e?.name !== 'AbortError') onEvent({ type: 'error', text: String(e?.message || e) })
  }
}

// ── Sessions (Recent queries) — historique serveur ───────────────────────────
export const createSession = (query, studyId = null) =>
  apiJson('/corpus/literature/sessions', {
    method: 'POST',
    body: JSON.stringify({ query, study_id: studyId }),
  })

export const listSessions = () => apiJson('/corpus/literature/sessions')

// Best-effort : ne jette jamais (l'audit ne doit pas casser le flux).
export const logEvent = (sessionId, eventType, payload = {}) =>
  apiFetch(`/corpus/literature/sessions/${sessionId}/events`, {
    method: 'POST',
    body: JSON.stringify({ event_type: eventType, payload }),
  }).then((r) => r.ok).catch(() => false)

// ── Snapshots (Saved evidence) ────────────────────────────────────────────────
const MODEL_VERSION = 'retrieve'
const PROMPT_VERSION = 'v1'

export function saveSnapshot({ query, sources, studyId = null, items }) {
  const results = items.map((r) => ({
    source: r.source,
    id: r.id,
    title: r.title,
    query_string: r.query_string,
    retrieval_date: r.retrieval_date,
    record: r.record,
    annotation: r.annotation ?? null,
  }))
  return apiJson('/corpus/literature/snapshots', {
    method: 'POST',
    body: JSON.stringify({
      query,
      sources,
      model_version: MODEL_VERSION,
      prompt_version: PROMPT_VERSION,
      study_id: studyId,
      results,
    }),
  })
}

export const listSnapshots = () => apiJson('/corpus/literature/snapshots')
export const getSnapshot = (id) => apiJson(`/corpus/literature/snapshots/${id}`)

// ── Add to corpus (PubMed only) ───────────────────────────────────────────────
export const ingestPmids = (pmids) =>
  apiJson('/corpus/literature/ingest', { method: 'POST', body: JSON.stringify({ pmids }) })
```

- [ ] **Step 2: Sanity-check imports compile**

Run: `cd apps/web && npx eslint src/workspace/literature/literatureClient.js`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/literature/literatureClient.js
git commit -m "feat(web): literature workbench API client (retrieve/sessions/snapshots/ingest)"
```

---

### Task 11: ResultCard (ported, + Add-to-corpus)

**Files:**
- Create: `apps/web/src/workspace/literature/ResultCard.jsx`

- [ ] **Step 1: Create the adapted ResultCard**

Adapted from `origin/corpus-live:src/literature/AdHocQuery/ResultCard.jsx`. Changes vs the old file: import `resultId` from `./literatureClient` (not `../recordUtils`); add an **Add to corpus** button (PubMed only) driven by `onAddToCorpus` + `ingestState`.

```jsx
import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Check, X, ChevronDown, ChevronRight, ExternalLink, Undo2, BookPlus } from 'lucide-react'
import { resultId } from './literatureClient'

const pubmedUrl = (pmid) => `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
const doiUrl = (doi) => `https://doi.org/${doi}`
const ctgovUrl = (nct) => `https://clinicaltrials.gov/study/${nct}`

// Dismissed → ligne repliée (conservé pour l'audit). Kept → carte pleine.
// readOnly (snapshot gelé) masque les actions. `ingestState` ∈ undefined|'busy'|'done'|'error'.
export function ResultCard({ result, position, status, onKeep, onDismiss, onAddToCorpus, ingestState, readOnly }) {
  const [showAbstract, setShowAbstract] = useState(false)
  const isCtgov = result.source === 'ctgov'
  const kept = status === 'kept'
  const dismissed = status === 'dismissed'
  const id = resultId(result)

  if (dismissed && !readOnly) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2">
        <span className="min-w-0 truncate text-[12px] text-muted-foreground">
          Dismissed · <span className="font-mono">{id}</span> — {result.title}
        </span>
        <Button variant="ghost" size="sm" className="h-6 flex-shrink-0 px-2 text-[11px]" onClick={onDismiss}>
          <Undo2 size={12} /> Undo
        </Button>
      </div>
    )
  }

  return (
    <Card className={cn('gap-0 rounded-xl border p-4', kept && 'border-primary/50 bg-secondary/40', dismissed && readOnly && 'opacity-60')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[11px] font-semibold text-muted-foreground">{position}.</span>
            <h4 className="text-[13.5px] font-semibold leading-snug">
              <a
                href={isCtgov ? ctgovUrl(result.nct_id) : pubmedUrl(result.pmid)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground hover:text-primary hover:underline"
              >
                {result.title}
              </a>
            </h4>
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            {isCtgov ? (
              <>
                {result.status && <span className="font-medium">{titleCase(result.status)}</span>}
                {result.phase && <> · {result.phase.replace(/PHASE/gi, 'Phase ')}</>}
                {result.interventions?.length ? <> · {result.interventions.slice(0, 3).join(', ')}</> : null}
              </>
            ) : (
              <>
                {result.journal ? <span className="italic">{result.journal}</span> : null}
                {result.publication_date ? ` · ${result.publication_date}` : ''}
              </>
            )}
          </div>
        </div>
        {!readOnly && (
          <div className="flex flex-shrink-0 items-center gap-1.5">
            <Button variant={kept ? 'default' : 'outline'} size="sm" className="h-7 px-2.5 text-[12px]" onClick={onKeep} title={kept ? 'Kept — click to undo' : 'Keep this result'}>
              <Check size={13} /> {kept ? 'Kept' : 'Keep'}
            </Button>
            <Button variant="ghost" size="sm" className="h-7 px-2.5 text-[12px] text-muted-foreground" onClick={onDismiss} title="Dismiss">
              <X size={13} /> Dismiss
            </Button>
            {!isCtgov && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2.5 text-[12px] text-muted-foreground"
                disabled={ingestState === 'busy' || ingestState === 'done'}
                onClick={() => onAddToCorpus?.(result)}
                title={ingestState === 'done' ? 'Added to corpus' : 'Index this article into your corpus'}
              >
                <BookPlus size={13} />{' '}
                {ingestState === 'done' ? 'Added' : ingestState === 'busy' ? 'Adding…' : 'Add to corpus'}
              </Button>
            )}
          </div>
        )}
        {readOnly && kept && <Badge variant="secondary" className="flex-shrink-0 text-[10.5px] text-primary">Kept</Badge>}
        {readOnly && dismissed && <Badge variant="outline" className="flex-shrink-0 text-[10.5px] text-muted-foreground">Dismissed</Badge>}
      </div>

      {isCtgov && result.conditions?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {result.conditions.slice(0, 6).map((c) => (
            <Badge key={c} variant="outline" className="text-[10px] font-normal text-muted-foreground">{c}</Badge>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border pt-2.5 text-[11.5px]">
        {result.abstract && (
          <button type="button" onClick={() => setShowAbstract((s) => !s)} className="flex items-center gap-1 font-medium text-primary hover:underline">
            {showAbstract ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {isCtgov ? 'Summary' : 'Abstract'}
          </button>
        )}
        {isCtgov ? (
          <a href={ctgovUrl(result.nct_id)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
            ClinicalTrials.gov <span className="font-mono">{result.nct_id}</span> <ExternalLink size={11} />
          </a>
        ) : (
          <>
            <a href={pubmedUrl(result.pmid)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
              PubMed <span className="font-mono">{result.pmid}</span> <ExternalLink size={11} />
            </a>
            {result.doi && (
              <a href={doiUrl(result.doi)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
                DOI <ExternalLink size={11} />
              </a>
            )}
          </>
        )}
      </div>

      {showAbstract && result.abstract && (
        <p className="mt-2 text-[12px] leading-relaxed text-foreground/75">{result.abstract}</p>
      )}
    </Card>
  )
}

function titleCase(s) {
  return String(s).toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
```

> Removed vs old: `authors`/`mesh_terms`/`relevance_rationale` blocks (the platform `retrieve` record has no such fields — PubMed record = pmid/title/abstract/journal/doi/published_at/evidence_type/article_types/url; CT.gov = nct_id/title/status/phase/conditions/interventions/url).

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/workspace/literature/ResultCard.jsx
git commit -m "feat(web): literature ResultCard (keep/dismiss + add-to-corpus)"
```

---

### Task 12: ResultsList (ported)

**Files:**
- Create: `apps/web/src/workspace/literature/ResultsList.jsx`

- [ ] **Step 1: Create the adapted ResultsList**

Adapted from `origin/corpus-live:src/literature/AdHocQuery/ResultsList.jsx`. Changes: import `resultId` from `./literatureClient`; thread `onAddToCorpus` + `ingestStateFor` to `ResultCard`.

```jsx
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ResultCard } from './ResultCard'
import { resultId } from './literatureClient'
import { BookOpen, FlaskConical, AlertTriangle, Loader2 } from 'lucide-react'

const SOURCE_META = {
  pubmed: { label: 'PubMed', Icon: BookOpen },
  ctgov: { label: 'ClinicalTrials.gov', Icon: FlaskConical },
}

// Résultats groupés par source (un en-tête par source). `groups` est keyé par
// source → { results, note, error, loading }.
export function ResultsList({ sources, groups, statusFor, onKeep, onDismiss, onAddToCorpus, ingestStateFor, readOnly }) {
  return (
    <div className="flex flex-col gap-4">
      {sources.map((source) => {
        const g = groups[source] || {}
        const meta = SOURCE_META[source] || { label: source, Icon: BookOpen }
        return (
          <div key={source} className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
              <meta.Icon size={15} className="text-primary" /> {meta.label}
              {g.results?.length > 0 && <Badge variant="secondary" className="font-mono text-[11px] text-primary">{g.results.length}</Badge>}
              {g.loading && <Loader2 size={13} className="animate-spin text-muted-foreground" />}
            </div>

            {g.error ? (
              <Card className="flex flex-row items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive">
                <AlertTriangle size={14} className="mt-px flex-shrink-0" />
                <span>{meta.label} failed: {g.error}</span>
              </Card>
            ) : g.loading ? (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">Searching {meta.label}…</Card>
            ) : g.results?.length ? (
              g.results.map((r, i) => (
                <ResultCard
                  key={resultId(r) || i}
                  result={r}
                  position={i + 1}
                  status={statusFor(resultId(r))}
                  onKeep={() => onKeep(r)}
                  onDismiss={() => onDismiss(r)}
                  onAddToCorpus={onAddToCorpus}
                  ingestState={ingestStateFor?.(resultId(r))}
                  readOnly={readOnly}
                />
              ))
            ) : g.note ? (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">{g.note}</Card>
            ) : (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">No results from {meta.label}.</Card>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/workspace/literature/ResultsList.jsx
git commit -m "feat(web): literature ResultsList (grouped by source)"
```

---

### Task 13: RecentQueries, SavedEvidence, SessionActions, StudyPicker (ported)

**Files:**
- Create: `apps/web/src/workspace/literature/RecentQueries.jsx`
- Create: `apps/web/src/workspace/literature/SavedEvidence.jsx`
- Create: `apps/web/src/workspace/literature/SessionActions.jsx`
- Create: `apps/web/src/workspace/literature/StudyPicker.jsx`

- [ ] **Step 1: Create RecentQueries** (adapted: `resultCount` is optional — sessions don't carry a count; `createdAt` is an ISO string from the backend)

```jsx
import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { History, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

// Sessions de recherche récentes (serveur). Ré-ouverture = relance live ; pas un
// snapshot/audit. Replié par défaut ; masqué s'il n'y a pas d'historique.
export function RecentQueries({ entries, activeId, onOpen }) {
  const [open, setOpen] = useState(false)
  if (!entries?.length) return null

  return (
    <Card className="gap-0 rounded-xl border p-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-5 py-3 text-left text-[13px] font-semibold text-foreground"
      >
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <History size={14} className="text-primary" /> Recent queries
        <Badge variant="secondary" className="ml-1 font-mono text-[10.5px] text-primary">{entries.length}</Badge>
      </button>

      {open && (
        <div className="flex flex-col border-t border-border">
          {entries.map((e) => (
            <button
              key={e.id}
              type="button"
              onClick={() => onOpen(e.id, e.question)}
              className={cn(
                'flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-left last:border-b-0 hover:bg-muted/40',
                e.id === activeId && 'bg-secondary/40',
              )}
            >
              <span className="min-w-0 truncate text-[12.5px] text-foreground">{e.question || '(untitled query)'}</span>
              <span className="flex flex-shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                <span>{relativeTime(e.createdAt)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}

function relativeTime(iso) {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const m = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
```

- [ ] **Step 2: Create SavedEvidence** (adapted: entry shape `{ snapshotId, question, studyId, resultCount }`)

```jsx
import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Lock, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

// Snapshots gelés (Saved evidence) — ré-ouverture en lecture seule. Masqué si vide.
export function SavedEvidence({ entries, activeId, onOpen }) {
  const [open, setOpen] = useState(false)
  if (!entries?.length) return null

  return (
    <Card className="gap-0 rounded-xl border p-0">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-1.5 px-5 py-3 text-left text-[13px] font-semibold text-foreground">
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <Lock size={14} className="text-primary" /> Saved evidence
        <Badge variant="secondary" className="ml-1 font-mono text-[10.5px] text-primary">{entries.length}</Badge>
      </button>
      {open && (
        <div className="flex flex-col border-t border-border">
          {entries.map((e) => (
            <button
              key={e.snapshotId}
              type="button"
              onClick={() => onOpen(e.snapshotId)}
              className={cn('flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-left last:border-b-0 hover:bg-muted/40', e.snapshotId === activeId && 'bg-secondary/40')}
            >
              <span className="min-w-0 truncate text-[12.5px] text-foreground">{e.question || '(untitled)'}</span>
              <span className="flex flex-shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                <Badge variant="outline" className="text-[10px] font-normal">{e.studyId ? 'study' : 'standalone'}</Badge>
                <span className="font-mono">{e.resultCount} res</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 3: Create SessionActions** (adapted: drop the demo-preview banner; saving is real)

```jsx
import { Button } from '@/components/ui/button'
import { Plus, Trash2, Bookmark, BookmarkCheck, Check } from 'lucide-react'

// Actions de session : sauver (étude ou standalone) gèle un snapshot. `saved`
// (quand défini) affiche une confirmation à la place des boutons de sauvegarde.
export function SessionActions({ saved, onSaveToStudy, onSaveStandalone, onNewQuery, onDiscard }) {
  return (
    <div className="flex flex-col gap-3">
      {saved ? (
        <>
          <div className="flex items-center gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5 text-[12.5px] text-foreground">
            <Check size={15} className="flex-shrink-0 text-primary" />
            <span>{saved.label}</span>
            {saved.href && <a href={saved.href} className="ml-auto text-[12px] font-medium text-primary hover:underline">Open →</a>}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" onClick={onNewQuery}><Plus className="h-3.5 w-3.5" /> Start new query</Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={onDiscard}><Trash2 className="h-3.5 w-3.5" /> Discard</Button>
          <Button variant="outline" onClick={onNewQuery}><Plus className="h-3.5 w-3.5" /> New query</Button>
          <Button variant="outline" onClick={onSaveStandalone}><Bookmark className="h-3.5 w-3.5" /> Save as standalone</Button>
          <Button onClick={onSaveToStudy}><BookmarkCheck className="h-3.5 w-3.5" /> Save to study</Button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Create StudyPicker** (verbatim port — already uses the platform `useCollection('studies')`)

```jsx
import { useCollection } from '@/workspace/dataClient'
import { Button } from '@/components/ui/button'
import { Library, X } from 'lucide-react'

// Sélecteur d'étude pour « Save to study ». Lit la VRAIE liste d'études via le data
// client existant (jamais une liste mockée).
export function StudyPicker({ onPick, onClose }) {
  const { data: studies, loading } = useCollection('studies')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
            <Library size={15} className="text-primary" /> Save to study
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
        </div>
        <p className="mb-3 text-[12px] text-muted-foreground">Freeze this evidence against a study for audit. It stays reproducible even if PubMed changes.</p>

        {loading ? (
          <div className="py-6 text-center text-[12.5px] text-muted-foreground">Loading studies…</div>
        ) : studies.length === 0 ? (
          <div className="py-6 text-center text-[12.5px] text-muted-foreground">No studies available to link.</div>
        ) : (
          <div className="flex max-h-[320px] flex-col gap-1.5 overflow-y-auto">
            {studies.map((s) => (
              <button
                key={s.id}
                onClick={() => onPick(s)}
                className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5 text-left hover:bg-muted/50"
              >
                <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-primary text-[12px] font-semibold text-white">
                  {(s.name || '?').charAt(0)}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-foreground">{s.name}</span>
                  {s.tagline && <span className="block truncate text-[11px] text-muted-foreground">{s.tagline}</span>}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/workspace/literature/RecentQueries.jsx apps/web/src/workspace/literature/SavedEvidence.jsx apps/web/src/workspace/literature/SessionActions.jsx apps/web/src/workspace/literature/StudyPicker.jsx
git commit -m "feat(web): literature recent/saved/actions/study-picker panels"
```

---

### Task 14: AdHocQuery workbench container

**Files:**
- Create: `apps/web/src/workspace/literature/AdHocQuery.jsx`

This is the adapted port of the old `AdHocQueryTab` + `QueryInput`, rewritten for the platform stream (`meta/group/done`), server-backed recent/saved, no demo/agent-panel, single Search button.

- [ ] **Step 1: Create the workbench**

```jsx
import { useReducer, useRef, useEffect, useState, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { AlertTriangle, SearchX, Lock, RefreshCw, Search as SearchIcon } from 'lucide-react'
import { ResultsList } from './ResultsList'
import { RecentQueries } from './RecentQueries'
import { SavedEvidence } from './SavedEvidence'
import { SessionActions } from './SessionActions'
import { StudyPicker } from './StudyPicker'
import {
  streamRetrieve, createSession, listSessions, logEvent,
  saveSnapshot, listSnapshots, getSnapshot, ingestPmids, flattenItem, resultId,
} from './literatureClient'

const DATE_RANGES = [
  { id: 'any', label: 'Any time' },
  { id: '1y', label: 'Last year' },
  { id: '5y', label: 'Last 5 years' },
  { id: '10y', label: 'Last 10 years' },
]
const STUDY_TYPES = [
  { id: 'rct', label: 'RCT' },
  { id: 'observational', label: 'Observational' },
  { id: 'systematic_review', label: 'Systematic review' },
  { id: 'meta_analysis', label: 'Meta-analysis' },
]
const SOURCE_OPTIONS = [
  { id: 'pubmed', label: 'PubMed' },
  { id: 'ctgov', label: 'ClinicalTrials.gov' },
]

// status: idle | querying | complete | error | frozen
const initialState = {
  sessionId: null,
  status: 'idle',
  question: '',
  dateRange: 'any',
  studyTypes: [],
  sources: ['pubmed', 'ctgov'],
  knownItem: false,
  knownItemMiss: false,
  groups: {},      // source -> { results, note, error, loading }
  marks: {},       // resultId -> 'kept' | 'dismissed'
  error: null,
  saved: null,     // { label, href } après sauvegarde
  frozenAt: null,
}

const blankGroups = (sources) => Object.fromEntries(sources.map((s) => [s, { results: [], loading: true }]))

function reducer(state, action) {
  switch (action.type) {
    case 'set_question': return { ...state, question: action.value }
    case 'set_date':     return { ...state, dateRange: action.value }
    case 'set_types':    return { ...state, studyTypes: action.value }
    case 'set_sources':  return { ...state, sources: action.value }
    case 'submit':
      return { ...state, status: 'querying', sessionId: action.sessionId, groups: blankGroups(state.sources), knownItem: false, knownItemMiss: false, marks: {}, error: null, saved: null, frozenAt: null }
    case 'ev_meta':
      return { ...state, sources: action.sources || state.sources, knownItem: !!action.known_item, groups: blankGroups(action.sources || state.sources) }
    case 'ev_group': {
      const items = (action.items || []).map(flattenItem)
      return { ...state, groups: { ...state.groups, [action.source]: { results: items, note: action.note, loading: false } } }
    }
    case 'ev_done': {
      const empty = Object.values(state.groups).every((g) => !(g.results && g.results.length))
      return { ...state, status: 'complete', knownItemMiss: state.knownItem && empty }
    }
    case 'ev_error': return { ...state, status: 'error', error: action.text || 'Query failed' }
    case 'mark':     return { ...state, marks: { ...state.marks, [action.id]: action.value } }
    case 'saved':    return { ...state, saved: action.saved }
    case 'reset':    return { ...initialState, dateRange: state.dateRange, studyTypes: state.studyTypes, sources: state.sources }
    case 'restore_frozen': {
      const snap = action.snapshot
      const sources = snap.sources || ['pubmed', 'ctgov']
      const flat = (snap.results || []).map((r) => flattenItem(r))
      const groups = Object.fromEntries(sources.map((s) => [s, { results: flat.filter((r) => r.source === s), loading: false }]))
      const marks = Object.fromEntries(flat.filter((r) => r.annotation).map((r) => [resultId(r), r.annotation]))
      return { ...initialState, status: 'frozen', question: snap.query ?? '', sources, groups, marks, frozenAt: snap.created_at || null }
    }
    default: return state
  }
}

export function AdHocQuery() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [history, setHistory] = useState([])
  const [saved, setSavedList] = useState([])
  const [picking, setPicking] = useState(false)
  const [ingest, setIngest] = useState({}) // resultId -> 'busy'|'done'|'error'
  const abortRef = useRef(null)

  const refreshHistory = useCallback(async () => {
    try {
      const rows = await listSessions()
      setHistory(rows.map((s) => ({ id: s.id, question: s.query, createdAt: s.created_at })))
    } catch { /* non-bloquant */ }
  }, [])
  const refreshSaved = useCallback(async () => {
    try {
      const rows = await listSnapshots()
      setSavedList(rows.map((s) => ({ snapshotId: s.id, question: s.query, studyId: s.study_id, resultCount: s.result_count })))
    } catch { /* non-bloquant */ }
  }, [])

  useEffect(() => { refreshHistory(); refreshSaved() }, [refreshHistory, refreshSaved])
  useEffect(() => () => abortRef.current?.abort(), [])

  const busy = state.status === 'querying'
  const frozen = state.status === 'frozen'
  const showResults = state.status === 'complete' || frozen

  const run = async () => {
    if (!state.question.trim() || busy) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let sessionId = null
    try { const s = await createSession(state.question.trim()); sessionId = s.id } catch { /* session best-effort */ }
    dispatch({ type: 'submit', sessionId })
    refreshHistory()
    await streamRetrieve({
      query: state.question.trim(),
      sources: state.sources,
      dateRange: state.dateRange,
      studyTypes: state.studyTypes,
      signal: ctrl.signal,
      onEvent: (ev) => {
        if (ev.type === 'meta') dispatch({ type: 'ev_meta', sources: ev.sources, known_item: ev.known_item })
        else if (ev.type === 'group') dispatch({ type: 'ev_group', source: ev.source, items: ev.items, note: ev.note })
        else if (ev.type === 'done') dispatch({ type: 'ev_done' })
        else if (ev.type === 'error') dispatch({ type: 'ev_error', text: ev.text })
      },
    })
  }

  const mark = (result, value) => {
    const id = resultId(result)
    const next = state.marks[id] === value ? null : value
    dispatch({ type: 'mark', id, value: next })
    if (next && state.sessionId) {
      logEvent(state.sessionId, value === 'kept' ? 'result_kept' : 'result_dismissed', { id, source: result.source })
    }
  }

  const addToCorpus = async (result) => {
    if (result.source !== 'pubmed' || !result.pmid) return
    const id = resultId(result)
    setIngest((m) => ({ ...m, [id]: 'busy' }))
    try { await ingestPmids([result.pmid]); setIngest((m) => ({ ...m, [id]: 'done' })) }
    catch { setIngest((m) => ({ ...m, [id]: 'error' })) }
  }

  const allItems = () => Object.values(state.groups).flatMap((g) => (g.results || []).map((r) => ({ ...r, annotation: state.marks[resultId(r)] ?? null })))

  const doSave = async (scope, study) => {
    setPicking(false)
    try {
      await saveSnapshot({ query: state.question, sources: state.sources, studyId: scope === 'study' ? study?.id ?? null : null, items: allItems() })
      dispatch({ type: 'saved', saved: scope === 'study' ? { label: `Saved to ${study.name}.`, href: `/studies/${study.id}` } : { label: 'Saved to Literature (standalone).' } })
      refreshSaved()
    } catch (e) {
      dispatch({ type: 'saved', saved: { label: `Could not save (${String(e?.message || 'error').slice(0, 80)}).` } })
    }
  }

  const reopenRecent = (id, question) => { abortRef.current?.abort(); dispatch({ type: 'set_question', value: question || '' }) }
  const reopenSaved = async (id) => {
    abortRef.current?.abort()
    try { const snap = await getSnapshot(id); dispatch({ type: 'restore_frozen', snapshot: snap }) } catch { /* ignore */ }
  }
  const startNew = () => { abortRef.current?.abort(); setIngest({}); dispatch({ type: 'reset' }) }

  const toggleSource = (id) => {
    const set = new Set(state.sources)
    set.has(id) ? set.delete(id) : set.add(id)
    if (set.size) dispatch({ type: 'set_sources', value: [...set] })
  }
  const toggleType = (id) => {
    const set = new Set(state.studyTypes)
    set.has(id) ? set.delete(id) : set.add(id)
    dispatch({ type: 'set_types', value: [...set] })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Live evidence retrieval.</strong>{' '}
        Ask a clinical question; the agent searches PubMed and ClinicalTrials.gov and returns structured, cited evidence, grouped by source. A live search takes up to ~90 seconds.
      </div>

      <RecentQueries entries={history} activeId={state.sessionId} onOpen={reopenRecent} />
      <SavedEvidence entries={saved} activeId={null} onOpen={reopenSaved} />

      {!frozen && (
        <Card className="gap-0 rounded-xl border p-5">
          <div className="mb-1 text-[15px] font-semibold text-foreground">Ask a research question</div>
          <p className="mb-3 text-[12px] text-muted-foreground">Plain English — the agent searches the selected sources and returns structured, cited results.</p>
          <textarea
            rows={3}
            value={state.question}
            disabled={busy}
            onChange={(e) => dispatch({ type: 'set_question', value: e.target.value })}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
            placeholder="e.g. What is the evidence for GLP-1 agonists in heart failure?"
            className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
          />
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2.5">
            <Pills label="Sources" options={SOURCE_OPTIONS} active={state.sources} onToggle={toggleSource} busy={busy} />
            <div className="flex items-center gap-2">
              <span className="text-[11.5px] font-medium text-muted-foreground">Date</span>
              <div className="flex gap-0.5 rounded-lg border border-border p-0.5">
                {DATE_RANGES.map((d) => (
                  <button key={d.id} type="button" disabled={busy} onClick={() => dispatch({ type: 'set_date', value: d.id })}
                    className={cn('rounded-md px-2.5 py-1 text-[11.5px] font-medium transition-colors disabled:opacity-60', state.dateRange === d.id ? 'bg-secondary text-primary' : 'text-muted-foreground hover:text-foreground')}>
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
            <Pills label="Study types" options={STUDY_TYPES} active={state.studyTypes} onToggle={toggleType} busy={busy} />
          </div>
          <div className="mt-4 flex justify-end">
            <Button disabled={busy || !state.question.trim()} onClick={run}>
              <SearchIcon className="h-3.5 w-3.5" /> {busy ? 'Searching…' : 'Search sources'}
            </Button>
          </div>
        </Card>
      )}

      {frozen && (
        <Card className="flex flex-row items-center justify-between gap-3 rounded-xl border border-primary/40 bg-secondary/40 p-4 text-[12.5px]">
          <span className="flex items-center gap-2 text-foreground"><Lock size={15} className="flex-shrink-0 text-primary" /><span><strong>Frozen snapshot{state.frozenAt ? ` from ${new Date(state.frozenAt).toLocaleDateString()}` : ''}.</strong> Saved evidence — reproducible exactly.</span></span>
          <div className="flex flex-shrink-0 gap-2">
            <button type="button" onClick={() => { const q = state.question; dispatch({ type: 'reset' }); dispatch({ type: 'set_question', value: q }) }} className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted/50"><RefreshCw size={13} /> Re-run live</button>
            <button type="button" onClick={startNew} className="rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted/50">Close</button>
          </div>
        </Card>
      )}

      {state.status === 'error' && (
        <Card className="flex flex-row items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-[12.5px] text-destructive">
          <AlertTriangle size={15} className="mt-px flex-shrink-0" />
          <span><strong>Search failed.</strong> {state.error} — try again or adjust the question.</span>
        </Card>
      )}

      {showResults && (state.knownItemMiss ? (
        <Card className="flex flex-row items-start gap-2 rounded-xl border border-border bg-muted/30 p-4 text-[12.5px] text-foreground/80">
          <SearchX size={15} className="mt-px flex-shrink-0 text-muted-foreground" />
          <span><strong className="text-foreground">No exact match found.</strong> The record may be too recently indexed, or check the PMID / DOI / NCT id.</span>
        </Card>
      ) : (
        <>
          <ResultsList
            sources={state.sources}
            groups={state.groups}
            statusFor={(id) => state.marks[id]}
            onKeep={(r) => mark(r, 'kept')}
            onDismiss={(r) => mark(r, 'dismissed')}
            onAddToCorpus={addToCorpus}
            ingestStateFor={(id) => ingest[id]}
            readOnly={frozen}
          />
          {!frozen && (
            <SessionActions
              saved={state.saved}
              onSaveToStudy={() => setPicking(true)}
              onSaveStandalone={() => doSave('standalone')}
              onNewQuery={startNew}
              onDiscard={startNew}
            />
          )}
        </>
      ))}

      {picking && <StudyPicker onPick={(s) => doSave('study', s)} onClose={() => setPicking(false)} />}
    </div>
  )
}

function Pills({ label, options, active, onToggle, busy }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11.5px] font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = active.includes(o.id)
          return (
            <button key={o.id} type="button" disabled={busy} onClick={() => onToggle(o.id)}
              className={cn('rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors disabled:opacity-60', on ? 'border-primary bg-secondary text-primary' : 'border-border text-muted-foreground hover:text-foreground')}>
              {o.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Lint the literature folder**

Run: `cd apps/web && npx eslint src/workspace/literature`
Expected: no errors (fix any unused-var / hooks-deps warnings surfaced).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/workspace/literature/AdHocQuery.jsx
git commit -m "feat(web): literature ad-hoc workbench (retrieve stream + filters + save + add-to-corpus)"
```

---

### Task 15: Full frontend lint

**Files:** none (verification)

- [ ] **Step 1: Lint the whole web app**

Run: `cd apps/web && npm run lint`
Expected: passes. Resolve any unused imports left in `CorpusPage.jsx` from Task 9 (e.g. remove `Library`/`EmptyState` if eslint reports them unused now that the page no longer references them directly).

- [ ] **Step 2: Build**

Run: `cd apps/web && npm run build`
Expected: build succeeds (no unresolved imports — confirms `AdHocQuery`/`SemanticSearch` resolve from `@/workspace/literature/*`).

- [ ] **Step 3: Commit any lint fixups**

```bash
git add -A apps/web/src/workspace/CorpusPage.jsx
git commit -m "chore(web): lint fixups after literature port"
```

---

## Phase E — Verification

### Task 16: Verify end-to-end against the real backend

**Files:** none (manual/preview verification — the web CI is eslint only, so behavior is verified by running the app)

- [ ] **Step 1: Start the backend locally**

Run (loads `.env`, which is not auto-loaded per the local-dev gotcha):
```bash
cd apps/api && set -a && . ./.env && set +a && uv run uvicorn 'augura_api.main:create_app' --factory --reload
```
Expected: server on `http://localhost:8000`.

- [ ] **Step 2: Start the frontend pointed at local backend**

Ensure `apps/web/.env.local` has `VITE_API_URL=http://localhost:8000`, then use the preview workflow (`preview_start`) on `apps/web` (`npm run dev`, Vite :5173).

- [ ] **Step 3: Verify the flows via preview**

Check each, capturing a screenshot/snapshot as proof:
1. Literature page shows two tabs (Ad-hoc query default, Study matches) — **no Browse**.
2. Enter a question (e.g. "GLP-1 agonists in heart failure"), toggle PubMed+CT.gov, pick "Last 5 years" + "RCT", click **Search sources** → results stream grouped by source.
3. A new entry appears under **Recent queries**; clicking it refills the question.
4. **Keep** / **Dismiss** a result (no console error; event POST returns 200 in the network panel).
5. On a PubMed result, **Add to corpus** → button shows "Added"; the network panel shows `POST /corpus/literature/ingest` 200.
6. **Save as standalone** → confirmation; the snapshot appears under **Saved evidence**; reopening it shows the frozen, read-only view.
7. Paste a PMID (e.g. `35319473`) → known-item path returns the single PubMed record; paste a bogus NCT → "No exact match found".
8. **Study matches** tab still runs semantic search.

- [ ] **Step 4: Confirm no regressions in the API gate**

Run: `cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all green.

- [ ] **Step 5: Final commit (if any verification fixups were needed)**

```bash
git add -A
git commit -m "fix(web): literature workbench verification fixups"
```

---

## Notes & risks (carried from the spec)
- **CT.gov study-type mapping is partial** (only RCT→Interventional, Observational→Observational; systematic review / meta-analysis have no CT.gov equivalent) — by design, documented in `filters.py`.
- **PubMed `[pt]` filters can over-restrict** — verify at least one result returns for typed queries in Step 3.
- **NDJSON streaming over Modal/Vercel** — verify the stream arrives in prod; the client already tolerates the whole body arriving at once (it splits on newlines), so a non-chunked response still parses.
- **Deferred (hidden, not faked):** cache (so a single "Search sources" button, no "Refresh from source") and the agent-activity panel (no `intent`/`agent_activity` events in the stream). These can be added later behind new backend support without touching the no-mock rule.
- **Corpus may be empty** for "Study matches" until results are added via "Add to corpus" or the existing ingest endpoint — expected.
```
