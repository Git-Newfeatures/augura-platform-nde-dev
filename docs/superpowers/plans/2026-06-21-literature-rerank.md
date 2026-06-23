# Abstract-based curation on `/corpus/literature/retrieve` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM curation (reading abstracts → ranked top-N + rationale) on the topical path of `retrieve`, two sources, always active with graceful degradation.

**Architecture:** New module `corpus/curation.py` (injectable `Curator` Protocol + `LLMCurator` reusing `run_structured_agent`). The `LiteratureRetriever` over-fetches a pool, calls the curator per source in parallel, reorders/filters the already-fetched records (the LLM only emits ids → zero fabrication), and attaches a `rationale`. No curator (key absent) or LLM failure → fall back to the current relevance top-N order. The `rationale` flows through to the frozen snapshot.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic · Anthropic SDK · pytest (asyncio) · React 19 · Vite. CI: `ruff format --check` · `ruff check` · `pyright` (strict) · `lint-imports` · `pytest` · OpenAPI drift-check.

**Spec reference:** `docs/superpowers/specs/2026-06-21-literature-rerank-design.md`

**Project convention:** comments/docstrings in English. Do NOT commit/push without an explicit request (`CLAUDE.md`) — the "Commit" steps below are to be run **only if the user has approved commits**; otherwise, skip the Commit step and stack the changes.

**All backend commands run from `apps/api/`.** The `@pytest.mark.integration` tests require a DB; the tests below are unit tests (no network, no DB).

---

### Task 1: `curation.py` — types + pure helper `apply_curation`

**Files:**
- Create: `apps/api/src/augura_api/modules/corpus/curation.py`
- Test: `apps/api/tests/test_corpus_curation.py`

- [ ] **Step 1: Write the failing test (pure mapping)**

Create `apps/api/tests/test_corpus_curation.py`:

```python
"""LLM curation (abstract-based re-ranking) — pure mapping helper + mocked LLMCurator.

No network: the mapping is pure; the LLMCurator is tested with a fake LLM client
(same pattern as test_agents_dag.py)."""

from augura_api.modules.corpus.curation import CuratedRef, apply_curation


def test_apply_curation_reorders_and_drops() -> None:
    by_id = {"a": "RecA", "b": "RecB", "c": "RecC"}
    refs = [CuratedRef(id="c", rationale="more relevant"), CuratedRef(id="a", rationale="ok")]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecC", "more relevant"), ("RecA", "ok")]  # 'b' dropped, LLM order


def test_apply_curation_ignores_hallucinated_and_dupes() -> None:
    by_id = {"a": "RecA"}
    refs = [CuratedRef(id="zzz", rationale="hallucinated"), CuratedRef(id="a", rationale="1"),
            CuratedRef(id="a", rationale="2")]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecA", "1")]  # id outside pool ignored, duplicate ignored


def test_apply_curation_caps_at_max_results() -> None:
    by_id = {"a": "A", "b": "B", "c": "C"}
    refs = [CuratedRef("a", ""), CuratedRef("b", ""), CuratedRef("c", "")]
    out = apply_curation(refs, by_id, max_results=2)
    assert [rec for rec, _ in out] == ["A", "B"]


def test_apply_curation_empty_when_nothing_matches() -> None:
    out = apply_curation([CuratedRef("zzz", "x")], {"a": "A"}, max_results=10)
    assert out == []
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: FAIL — `ModuleNotFoundError: ... corpus.curation` (the module does not exist).

- [ ] **Step 3: Create `curation.py` with the types + `apply_curation`**

Create `apps/api/src/augura_api/modules/corpus/curation.py`:

```python
"""LLM curation of live results (abstract-based re-ranking + rationale).

Sibling of `pubmed.py` / `ctgov.py`. `Curator` is an injectable Protocol (network-free
tests); `LLMCurator` reuses `run_structured_agent` (forced tool + Pydantic validation
+ 1 repair retry). The LLM returns ONLY ordered ids + rationale; the mapping onto the
already-fetched records is deterministic (`apply_curation`), so no content fabrication
is possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel
from anthropic.types import ToolParam

from augura_api.core.llm.runtime import LLMClient, run_structured_agent

# Curation prompt version — pinned in the snapshot provenance.
CURATION_PROMPT_VERSION = "curate-v1"

# Token bound: we truncate each candidate's text (abstract / CT.gov summary).
_MAX_TEXT = 1200


@dataclass(frozen=True)
class CurationCandidate:
    """Candidate submitted to the LLM: stable id + title + judgeable text (abstract or summary)."""

    id: str
    title: str
    text: str


@dataclass(frozen=True)
class CuratedRef:
    """Per-item curation output: the list order carries the ranking."""

    id: str
    rationale: str


def apply_curation[T](
    refs: list[CuratedRef], by_id: dict[str, T], *, max_results: int
) -> list[tuple[T, str]]:
    """Maps the LLM-ordered refs → (record, rationale), deterministically: ignores ids
    outside `by_id` (hallucinated) and duplicates, caps at `max_results`. Returns [] if
    nothing matches (the caller decides on the fallback)."""
    seen: set[str] = set()
    out: list[tuple[T, str]] = []
    for ref in refs:
        if ref.id in seen or ref.id not in by_id:
            continue
        seen.add(ref.id)
        out.append((by_id[ref.id], ref.rationale))
        if len(out) >= max_results:
            break
    return out
```

(The `BaseModel`/`ToolParam`/`run_structured_agent`/`LLMClient` imports are for Task 2; they are placed here to avoid a second header reshuffle. `ruff` may flag unused imports until Task 2 is done — run both tasks before the final lint, or add Task 2's code right after.)

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** *(only if commits approved by the user)*

```bash
git add apps/api/src/augura_api/modules/corpus/curation.py apps/api/tests/test_corpus_curation.py
git commit -m "feat(corpus): curation types + pure apply_curation (re-ranking)"
```

---

### Task 2: `curation.py` — `Curator` Protocol + `LLMCurator`

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/curation.py`
- Test: `apps/api/tests/test_corpus_curation.py`

- [ ] **Step 1: Add the failing tests (mocked LLMCurator)**

Add at the top of `tests/test_corpus_curation.py` (imports):

```python
from typing import Any

from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.modules.corpus.curation import (
    CuratedRef,
    CurationCandidate,
    LLMCurator,
    apply_curation,
)
```

> ⚠️ Task 1 has already created this file with
> `from augura_api.modules.corpus.curation import CuratedRef, apply_curation`.
> **Merge** into the block above (do not duplicate `CuratedRef`/`apply_curation`,
> otherwise ruff F811/F401).

The fake LLM client helpers (same pattern as `test_agents_dag.py`), in the same file:

```python
def _msg(tool_input: dict[str, Any]) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name="curate_results", input=tool_input)
    ]
    return Message(
        id="msg_1", content=content, model="claude-haiku-4-5-20251001", role="assistant",
        stop_reason="tool_use", type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


class _FakeMessages:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = responses
        self.calls = 0
        self.last_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Message:
        self.calls += 1
        self.last_kwargs = kwargs
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, *responses: Message) -> None:
        self.messages = _FakeMessages(list(responses))
```

Then the tests:

```python
async def test_llm_curator_returns_ordered_refs() -> None:
    client = _FakeClient(_msg({"selected": [
        {"id": "2", "rationale": "RCT directly on the question"},
        {"id": "1", "rationale": "relevant but observational"},
    ]}))
    curator = LLMCurator(client, "claude-haiku-4-5-20251001")  # type: ignore[arg-type]
    cands = [
        CurationCandidate("1", "Obs study", "abstract 1"),
        CurationCandidate("2", "RCT", "abstract 2"),
    ]
    refs = await curator.curate("hba1c", "pubmed", cands, max_results=5)
    assert [r.id for r in refs] == ["2", "1"]
    assert refs[0].rationale.startswith("RCT")


async def test_llm_curator_empty_candidates_skips_call() -> None:
    client = _FakeClient()  # no response → if called, would raise IndexError
    curator = LLMCurator(client, "m")  # type: ignore[arg-type]
    assert await curator.curate("q", "pubmed", [], max_results=5) == []
    assert client.messages.calls == 0
```

- [ ] **Step 2: Run, confirm it fails**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: FAIL — `ImportError: cannot import name 'LLMCurator'`.

- [ ] **Step 3: Implement `Curator` + `LLMCurator` in `curation.py`**

Add at the end of `curation.py`:

```python
class Curator(Protocol):
    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]: ...


class _CuratedItem(BaseModel):
    id: str
    rationale: str = ""


class _CurationOutput(BaseModel):
    selected: list[_CuratedItem]


_CURATION_TOOL: ToolParam = {
    "name": "curate_results",
    "description": "Returns the most relevant results, ranked from most to least "
    "relevant, each with a short rationale.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "exact id of a provided candidate"},
                        "rationale": {"type": "string", "description": "1-sentence justification"},
                    },
                    "required": ["id"],
                },
            }
        },
        "required": ["selected"],
    },
}

_SYSTEM = (
    "You are a biomedical information specialist. Given a research question and a list "
    "of results (id, title, text), select and RANK the most relevant ones, from most "
    "to least relevant. At equal relevance, promote the strongest evidence "
    "(meta-analyses / systematic reviews / RCT > observational > other). NEVER invent "
    "ids: use only the provided ids. Give a one-sentence rationale per retained result. "
    "Discard off-topic results."
)


def _render(candidates: list[CurationCandidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        text = c.text[:_MAX_TEXT]
        lines.append(f"[{c.id}] {c.title}\n{text}")
    return "\n\n".join(lines)


class LLMCurator:
    """Real implementation: one `run_structured_agent` call per source."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        if not candidates:
            return []
        user = (
            f"Question: {query}\nSource: {source}\n"
            f"Select at most {max_results} results among:\n\n{_render(candidates)}"
        )
        result = await run_structured_agent(
            self._client,
            model=self._model,
            system=_SYSTEM,
            tool=_CURATION_TOOL,
            messages=[{"role": "user", "content": user}],
            output_model=_CurationOutput,
        )
        return [CuratedRef(id=i.id, rationale=i.rationale) for i in result.output.selected]
```

- [ ] **Step 4: Run, confirm it passes**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint + types of the module**

Run: `uv run ruff check src/augura_api/modules/corpus/curation.py && uv run pyright src/augura_api/modules/corpus/curation.py`
Expected: no error (no more unused imports).

- [ ] **Step 6: Commit** *(if approved)*

```bash
git add apps/api/src/augura_api/modules/corpus/curation.py apps/api/tests/test_corpus_curation.py
git commit -m "feat(corpus): LLMCurator (abstract-based re-ranking via run_structured_agent)"
```

---

### Task 3: Contract — `rationale` on `RetrievedItemOut` + `FrozenResult`

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py:143-150` (`RetrievedItemOut`)
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py:171-181` (`FrozenResult`)

- [ ] **Step 1: Add the `rationale` field to `RetrievedItemOut`**

In `RetrievedItemOut`, after `annotation: str | None = None`, add:

```python
    rationale: str | None = None  # curation rationale (None if not curated)
```

- [ ] **Step 2: Add the `rationale` field to `FrozenResult`**

In `FrozenResult`, after `annotation: str | None = None`, add:

```python
    rationale: str | None = None  # frozen curation rationale (provenance)
```

- [ ] **Step 3: Check the types**

Run: `uv run pyright src/augura_api/modules/corpus/schemas.py`
Expected: no error.

- [ ] **Step 4: Commit** *(if approved)*

```bash
git add apps/api/src/augura_api/modules/corpus/schemas.py
git commit -m "feat(corpus): rationale field on RetrievedItemOut + FrozenResult"
```

---

### Task 4: `retrieval.py` — `RetrievedItem.rationale` + over-fetch + curation

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/retrieval.py`
- Test: `apps/api/tests/test_corpus_retrieval.py`

- [ ] **Step 1: Add the failing tests (curator stub)**

Add to `tests/test_corpus_retrieval.py` — first a curator stub at the bottom of the fakes area (after `FakeCTGov`):

```python
from augura_api.modules.corpus.curation import CurationCandidate, CuratedRef


class FakeCurator:
    """Returns the ids in reverse order of receipt, with a rationale, and can
    simulate a failure (raise) or a partial selection."""

    def __init__(self, *, error: Exception | None = None, only: list[str] | None = None) -> None:
        self.error = error
        self.only = only
        self.calls: list[tuple[str, str, int]] = []  # (source, first id, candidate count)

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        first = candidates[0].id if candidates else ""
        self.calls.append((source, first, len(candidates)))
        if self.error is not None:
            raise self.error
        ids = [c.id for c in candidates]
        if self.only is not None:
            ids = [i for i in ids if i in self.only]
        return [CuratedRef(id=i, rationale=f"rat-{i}") for i in reversed(ids)]
```

Then a `_retriever_c` helper and the tests (the existing `ART`/`STUDY` have ids `35319473` / `NCT01691846`; add a 2nd of each to test the reordering):

```python
ART2 = PubMedArticle(
    pmid="40000000", title="PubMed paper 2", abstract="abstract2",
    url="https://doi.org/10.1/y", evidence_type="review",
)
STUDY2 = CTGovStudy(
    nct_id="NCT02000000", title="CT study 2", status="RECRUITING", phase="PHASE2",
    conditions=("Hypertension",), interventions=("drug",),
    url="https://clinicaltrials.gov/study/NCT02000000",
)


def _retriever_c(pm: FakePubMed, ct: FakeCTGov, cur: "FakeCurator") -> LiteratureRetriever:
    return LiteratureRetriever(cast(PubMedClient, pm), cast(CTGovClient, ct), curator=cur)


async def test_curation_reorders_and_annotates_both_sources() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[STUDY, STUDY2])
    cur = FakeCurator()  # reverses the order
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["40000000", "35319473"]  # order reversed by the curator
    assert pmg.items[0].rationale == "rat-40000000"
    ctg = next(g for g in r.groups if g.source == SOURCE_CTGOV)
    assert [i.id for i in ctg.items] == ["NCT02000000", "NCT01691846"]
    assert ctg.items[0].rationale == "rat-NCT02000000"
    # over-fetch: pool = min(50, max(25, 5*2)) = 25
    assert pm.calls == [("search", "hba1c", 25)]
    assert ct.calls == [("search", "hba1c", 25)]


async def test_curation_failure_falls_back_to_relevance_order() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator(error=RuntimeError("LLM down"))
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]  # source order preserved
    assert all(i.rationale is None for i in pmg.items)  # no rationale on fallback


async def test_curation_empty_selection_falls_back() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[])
    cur = FakeCurator(only=["zzz"])  # nothing matches
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)
    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]  # relevance fallback
    assert all(i.rationale is None for i in pmg.items)


async def test_known_item_is_not_curated() -> None:
    pm = FakePubMed(fetch_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator()
    r = await _retriever_c(pm, ct, cur).retrieve("35319473", today=DAY)
    assert cur.calls == []  # known-item never curated
    assert r.groups[0].items[0].rationale is None
```

- [ ] **Step 2: Run, confirm it fails**

Run: `uv run pytest tests/test_corpus_retrieval.py -q`
Expected: FAIL — `TypeError: LiteratureRetriever.__init__() got an unexpected keyword argument 'curator'` (and `RetrievedItem` has no `rationale`).

- [ ] **Step 3: Modify `retrieval.py`**

3a. Header — add the import (after the `pubmed` import):

```python
from augura_api.core.llm.runtime import AgentInvalidOutput, AgentUpstreamError
from augura_api.modules.corpus.curation import (
    CurationCandidate,
    Curator,
    apply_curation,
)
```

3b. `RetrievedItem` (≈ line 53) — add the field after `annotation`:

```python
    rationale: str | None = None  # curation rationale (None if not curated)
```

3c. `LiteratureRetriever.__init__` (≈ line 121) — accept the curator:

```python
    def __init__(
        self, pubmed: PubMedClient, ctgov: CTGovClient, *, curator: Curator | None = None
    ) -> None:
        self._pubmed = pubmed
        self._ctgov = ctgov
        self._curator = curator
```

3d. Add the pool computation + two curation helpers (class methods):

```python
    def _pool(self, max_results: int) -> int:
        """Over-fetched pool size: no curation ⇒ exactly max_results (historical
        behavior unchanged); otherwise min(50, max(25, max_results*2))."""
        if self._curator is None:
            return max_results
        return min(50, max(25, max_results * 2))

    async def _curate_pubmed(
        self, query: str, articles: list[PubMedArticle], max_results: int
    ) -> list[tuple[PubMedArticle, str | None]]:
        if self._curator is None:
            return [(a, None) for a in articles[:max_results]]
        cands = [CurationCandidate(a.pmid, a.title, a.abstract) for a in articles]
        try:
            refs = await self._curator.curate(query, SOURCE_PUBMED, cands, max_results=max_results)
        except (AgentUpstreamError, AgentInvalidOutput) as exc:
            log.warning("curate.failed", source=SOURCE_PUBMED, error=str(exc))
            return [(a, None) for a in articles[:max_results]]
        applied = apply_curation(refs, {a.pmid: a for a in articles}, max_results=max_results)
        if not applied:
            return [(a, None) for a in articles[:max_results]]
        return [(a, rat or None) for a, rat in applied]

    async def _curate_ctgov(
        self, query: str, studies: list[CTGovStudy], max_results: int
    ) -> list[tuple[CTGovStudy, str | None]]:
        if self._curator is None:
            return [(s, None) for s in studies[:max_results]]
        cands = [
            CurationCandidate(
                s.nct_id,
                s.title,
                f"Conditions: {', '.join(s.conditions)}. Interventions: "
                f"{', '.join(s.interventions)}. Phase {s.phase}. Status {s.status}.",
            )
            for s in studies
        ]
        try:
            refs = await self._curator.curate(query, SOURCE_CTGOV, cands, max_results=max_results)
        except (AgentUpstreamError, AgentInvalidOutput) as exc:
            log.warning("curate.failed", source=SOURCE_CTGOV, error=str(exc))
            return [(s, None) for s in studies[:max_results]]
        applied = apply_curation(refs, {s.nct_id: s for s in studies}, max_results=max_results)
        if not applied:
            return [(s, None) for s in studies[:max_results]]
        return [(s, rat or None) for s, rat in applied]
```

3e. Rewrite `_pubmed_topical` (≈ line 211) to over-fetch then curate:

```python
    async def _pubmed_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        term = build_pubmed_term(query, filters)
        articles = await self._pubmed.search(
            query, self._pool(max_results), filters=filters, today=day
        )
        curated = await self._curate_pubmed(query, articles, max_results)
        items = [
            RetrievedItem(SOURCE_PUBMED, a.pmid, a.title, term, day, _pubmed_record(a), rationale=r)
            for a, r in curated
        ]
        return SourceGroup(SOURCE_PUBMED, term, items)
```

3f. Rewrite `_ctgov_topical` (≈ line 223) the same way:

```python
    async def _ctgov_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        extra = ctgov_filter_params(filters, day)
        suffix = "".join(f"&{k}={v}" for k, v in sorted(extra.items()))
        qs = f"query.term={query}{suffix}"
        studies = await self._ctgov.search(
            query, self._pool(max_results), filters=filters, today=day
        )
        curated = await self._curate_ctgov(query, studies, max_results)
        items = [
            RetrievedItem(SOURCE_CTGOV, s.nct_id, s.title, qs, day, _ctgov_record(s), rationale=r)
            for s, r in curated
        ]
        return SourceGroup(SOURCE_CTGOV, qs, items)
```

Note: `RetrievedItem(...)` is called here positionally (source, id, title, query_string, retrieval_date, record) + `rationale=` as a kwarg — aligned on the dataclass.

- [ ] **Step 4: Run the retrieval tests (old + new)**

Run: `uv run pytest tests/test_corpus_retrieval.py -q`
Expected: PASS. The old tests (`curator` absent → `_pool` = max_results) keep `pm.calls == [("search", query, 5)]`; the 4 new ones pass.

- [ ] **Step 5: Check types + import contracts**

Run: `uv run pyright src/augura_api/modules/corpus/retrieval.py && uv run lint-imports`
Expected: no error (`corpus` may import `core.llm`).

- [ ] **Step 6: Commit** *(if approved)*

```bash
git add apps/api/src/augura_api/modules/corpus/retrieval.py apps/api/tests/test_corpus_retrieval.py
git commit -m "feat(corpus): over-fetch + per-source curation in retrieve"
```

---

### Task 5: `snapshot_service.py` — propagate `rationale` (response + frozen payload)

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/snapshot_service.py:41-49` (`to_retrieve_response`)
- Modify: `apps/api/src/augura_api/modules/corpus/snapshot_service.py:70-81` (`_build_payload`)
- Test: `apps/api/tests/test_corpus_freeze.py`

- [ ] **Step 1: Write the failing test**

First check the style of `tests/test_corpus_freeze.py` (`uv run pytest tests/test_corpus_freeze.py -q` should already pass). Add a targeted `to_retrieve_response` test:

```python
from datetime import date

from augura_api.modules.corpus.retrieval import (
    RetrievalResult, RetrievedItem, SourceGroup,
)
from augura_api.modules.corpus.snapshot_service import to_retrieve_response


def test_to_retrieve_response_carries_rationale() -> None:
    item = RetrievedItem(
        "pubmed", "1", "T", "term", date(2026, 6, 21), {"pmid": "1"}, rationale="the most relevant",
    )
    res = RetrievalResult("q", ["pubmed"], False, None, [SourceGroup("pubmed", "term", [item])])
    out = to_retrieve_response(res)
    assert out.groups[0].items[0].rationale == "the most relevant"
```

- [ ] **Step 2: Run, confirm it fails**

Run: `uv run pytest tests/test_corpus_freeze.py::test_to_retrieve_response_carries_rationale -q`
Expected: FAIL — `AssertionError` (rationale is None because not propagated) or `TypeError` if the kwarg field is not recognized (depending on the state of the other tasks; Task 3 must be done first).

- [ ] **Step 3: Propagate `rationale` in `to_retrieve_response`**

In the `schemas.RetrievedItemOut(...)` construction, after `annotation=i.annotation,` add:

```python
                        rationale=i.rationale,
```

- [ ] **Step 4: Propagate `rationale` in `_build_payload`**

In each result's dict (`results: [...]`), after `"annotation": r.annotation,` add:

```python
                "rationale": r.rationale,
```

- [ ] **Step 5: Run, confirm it passes**

Run: `uv run pytest tests/test_corpus_freeze.py -q`
Expected: PASS (old + new). Compatibility note: old snapshots stored without a `rationale` key re-read via `FrozenResult(**r)` (optional `None` field) and `verify_content_hash` recomputes on the stored payload as-is → unchanged hash.

- [ ] **Step 6: Commit** *(if approved)*

```bash
git add apps/api/src/augura_api/modules/corpus/snapshot_service.py apps/api/tests/test_corpus_freeze.py
git commit -m "feat(corpus): rationale propagated in retrieve response + snapshot payload"
```

---

### Task 6: `router.py` — build the curator + enrich the `meta` event

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/router.py:18-36` (imports)
- Modify: `apps/api/src/augura_api/modules/corpus/router.py:192-242` (`literature_retrieve`)

- [ ] **Step 1: Add the imports**

After `from augura_api.modules.corpus.ctgov import CTGovApiClient`, add:

```python
from augura_api.modules.corpus.curation import CURATION_PROMPT_VERSION, Curator, LLMCurator
```

- [ ] **Step 2: Build the curator in `literature_retrieve`**

At the start of `literature_retrieve`, after `sources = set(req.sources) if req.sources else None`, add:

```python
    # Curator built once per request (reuses the Anthropic client). No key
    # ⇒ curator=None ⇒ retrieve behaves as before (zero regression).
    curator: Curator | None = None
    try:
        curator = LLMCurator(get_anthropic_client(settings), settings.agent_model_fast)
    except AgentUpstreamError:
        curator = None
```

- [ ] **Step 3: Pass the curator to the retriever + enrich `meta`**

In `gen()`, pass `curator=curator` to the `LiteratureRetriever(...)`:

```python
                retriever = LiteratureRetriever(
                    NCBIPubMedClient(http, api_key=settings.ncbi_api_key),
                    CTGovApiClient(ctgov_http, base_url=settings.ctgov_relay_url),
                    curator=curator,
                )
```

And enrich the `meta` event (curation only applies to the topical path):

```python
            yield _ndjson(
                "meta",
                query=resp.query,
                sources=resp.sources,
                known_item=resp.known_item,
                kind=resp.kind,
                curated=curator is not None and not resp.known_item,
                model_version=settings.agent_model_fast if curator else None,
                prompt_version=CURATION_PROMPT_VERSION if curator else None,
            )
```

- [ ] **Step 4: Check types + that the route is still mounted**

Run: `uv run pyright src/augura_api/modules/corpus/router.py && uv run pytest tests/test_app_routes.py -q`
Expected: no type errors; the route tests pass (route `/corpus/literature/retrieve` still registered). The curation logic is covered at the `retrieval.py` level (Task 4); this wiring is trivial.

- [ ] **Step 5: Commit** *(if approved)*

```bash
git add apps/api/src/augura_api/modules/corpus/router.py
git commit -m "feat(corpus): wire the curator into /literature/retrieve + enriched meta"
```

---

### Task 7: Regenerate the OpenAPI + the TS client (CI drift-check)

**Files:**
- Modify: `packages/api-client/openapi.json`
- Modify: `packages/api-client/src/schema.d.ts`

- [ ] **Step 1: Regenerate the OpenAPI**

Run (from the repo root): `uv run python apps/api/scripts/dump_openapi.py`
Expected: `packages/api-client/openapi.json` regenerated. `git diff --stat packages/api-client/openapi.json` should show the addition of `rationale` on the `FrozenResult` schemas (and `RetrievedItemOut` if it is reachable from the graph). If no diff: the models are not reachable ⇒ nothing to do, continue.

- [ ] **Step 2: Regenerate the TS client**

Run: `npm --prefix packages/api-client run generate`
Expected: `packages/api-client/src/schema.d.ts` regenerated (NEVER hand-edit it).

- [ ] **Step 3: Commit** *(if approved)*

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regen OpenAPI/client for curation rationale"
```

---

### Task 8: Frontend — show the rationale + freeze it + provenance

**Files:**
- Modify: `apps/web/src/workspace/literature/literatureClient.js:17-30` (`flattenItem`)
- Modify: `apps/web/src/workspace/literature/literatureClient.js:93-114` (`saveSnapshot`)
- Modify: `apps/web/src/workspace/literature/ResultCard.jsx`
- Modify: `apps/web/src/workspace/literature/AdHocQuery.jsx` (reducer + `doSave`)

- [ ] **Step 1: `flattenItem` carries the rationale**

In `literatureClient.js`, in the object returned by `flattenItem`, after `annotation: item.annotation ?? null,` add:

```javascript
    rationale: item.rationale ?? null,
```

(Placing this line BEFORE the `...rec` spread does not matter: `record` has no `rationale` key. Leaving it right after `annotation` is the most readable.)

- [ ] **Step 2: `saveSnapshot` freezes the rationale + accepts the provenance**

Modify the signature and the mapping of `saveSnapshot`:

```javascript
export function saveSnapshot({ query, sources, studyId = null, items, modelVersion = MODEL_VERSION, promptVersion = PROMPT_VERSION }) {
  const results = items.map((r) => ({
    source: r.source,
    id: r.id,
    title: r.title,
    query_string: r.query_string,
    retrieval_date: r.retrieval_date,
    record: r.record,
    annotation: r.annotation ?? null,
    rationale: r.rationale ?? null,
  }))
  return apiJson('/corpus/literature/snapshots', {
    method: 'POST',
    body: JSON.stringify({
      query,
      sources,
      model_version: modelVersion,
      prompt_version: promptVersion,
      study_id: studyId,
      results,
    }),
  })
}
```

- [ ] **Step 3: `ResultCard` shows the rationale**

In `ResultCard.jsx`, just before the `{showAbstract && result.abstract && (...)}` block (≈ line 113), insert a rationale callout (visible outside readOnly as in frozen):

```jsx
      {result.rationale && (
        <p className="mt-2 rounded-md bg-secondary/30 px-2.5 py-1.5 text-[11.5px] italic leading-relaxed text-muted-foreground">
          <span className="font-medium not-italic text-foreground/70">Why: </span>{result.rationale}
        </p>
      )}
```

- [ ] **Step 4: `AdHocQuery` captures the provenance from `meta` and passes it to Save**

4a. `initialState` (≈ line 34) — add after `frozenAt: null,`:

```javascript
  modelVersion: null,
  promptVersion: null,
```

4b. `ev_meta` reducer (≈ line 60) — capture the versions:

```javascript
    case 'ev_meta':
      return { ...state, sources: action.sources || state.sources, knownItem: !!action.known_item, modelVersion: action.model_version ?? null, promptVersion: action.prompt_version ?? null, groups: blankGroups(action.sources || state.sources) }
```

4c. `onEvent` of `meta` (≈ line 132) — forward the fields:

```javascript
        if (ev.type === 'meta') dispatch({ type: 'ev_meta', sources: ev.sources, known_item: ev.known_item, model_version: ev.model_version, prompt_version: ev.prompt_version })
```

4d. `doSave` (≈ line 172) — pass the provenance to `saveSnapshot`:

```javascript
      await saveSnapshot({ query: state.question, sources: state.sources, studyId: scope === 'study' ? study?.id ?? null : null, items, modelVersion: state.modelVersion ?? undefined, promptVersion: state.promptVersion ?? undefined })
```

(`?? undefined` ⇒ if `meta` did not provide a version — known-item, or no key — we fall back on the `MODEL_VERSION`/`PROMPT_VERSION` defaults of `literatureClient.js`.)

- [ ] **Step 5: Frontend lint + build**

Run (from `apps/web/`): `npm run lint && npm run build`
Expected: no ESLint error, build OK.

- [ ] **Step 6: Visual check (preview)**

Follow the preview workflow: start the server, open the Literature workbench, run a search, verify that the cards show "Why: …" and that the order reflects the curation; freeze a snapshot and reopen "Saved evidence" to confirm the rationale is persisted.

- [ ] **Step 7: Commit** *(if approved)*

```bash
git add apps/web/src/workspace/literature/literatureClient.js apps/web/src/workspace/literature/ResultCard.jsx apps/web/src/workspace/literature/AdHocQuery.jsx
git commit -m "feat(web): show the curation rationale + freeze it in snapshots"
```

---

### Task 9: Full CI gate

**Files:** none (verification)

- [ ] **Step 1: Full backend suite + lint + types + contracts**

Run (from `apps/api/`):

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q
```

Expected: all green. (The `@pytest.mark.integration` tests are skipped without `AUGURA_DATABASE_URL` — that is expected.)

- [ ] **Step 2: OpenAPI drift-check**

Run (from the root):

```bash
uv run python apps/api/scripts/dump_openapi.py && git diff --exit-code packages/api-client/openapi.json
```

Expected: exit code 0 (no uncommitted diff — Task 7 already regenerated).

- [ ] **Step 3: Frontend lint + build**

Run (from `apps/web/`): `npm run lint && npm run build`
Expected: green.

- [ ] **Step 4: Possible final commit** *(if approved and if formatting changes remain)*

```bash
git status   # verify nothing unexpected remains
```

---

## Scope notes

- **Not in A** (reserved for B / item C): keyword generation+validation workbench (MeSH-UID, openFDA, MAUDE, green/amber tags), agentic tool-use loop, result cache, live FDA/MAUDE sources.
- **Latency**: +1 LLM call per source before emitting the `group` ("group curated at once" decision). Mitigated by `agent_model_fast` + bounded pool (25). The frontend already shows a per-group loading state (`loading: true`).
