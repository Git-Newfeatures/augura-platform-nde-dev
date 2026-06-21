# Curation par abstract sur `/corpus/literature/retrieve` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une curation LLM (lecture des abstracts → top-N classé + rationale) sur le chemin topique du `retrieve`, deux sources, toujours active avec dégradation gracieuse.

**Architecture:** Nouveau module `corpus/curation.py` (Protocol `Curator` injectable + `LLMCurator` réutilisant `run_structured_agent`). Le `LiteratureRetriever` sur-récupère un pool, appelle le curator par source en parallèle, réordonne/filtre les enregistrements déjà récupérés (le LLM n'émet que des ids → zéro fabrication), et attache un `rationale`. Pas de curator (clé absente) ou panne LLM → repli sur l'ordre relevance top-N actuel. Le `rationale` transite jusqu'au snapshot gelé.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic · Anthropic SDK · pytest (asyncio) · React 19 · Vite. CI : `ruff format --check` · `ruff check` · `pyright` (strict) · `lint-imports` · `pytest` · drift-check OpenAPI.

**Référence spec :** `docs/superpowers/specs/2026-06-21-literature-rerank-design.md`

**Convention projet :** commentaires/docstrings en français. Ne PAS committer/pousser sans demande explicite (`CLAUDE.md`) — les steps « Commit » ci-dessous sont à exécuter **uniquement si l'utilisateur a validé les commits** ; sinon, sauter le step Commit et empiler les changements.

**Toutes les commandes backend partent de `apps/api/`.** Les `@pytest.mark.integration` exigent une DB ; les tests ci-dessous sont unitaires (aucun réseau, aucune DB).

---

### Task 1: `curation.py` — types + helper pur `apply_curation`

**Files:**
- Create: `apps/api/src/augura_api/modules/corpus/curation.py`
- Test: `apps/api/tests/test_corpus_curation.py`

- [ ] **Step 1: Écrire le test qui échoue (mapping pur)**

Créer `apps/api/tests/test_corpus_curation.py` :

```python
"""Curation LLM (re-ranking par abstract) — helper de mapping pur + LLMCurator mocké.

Aucun réseau : le mapping est pur ; le LLMCurator est testé avec un client LLM factice
(même pattern que test_agents_dag.py)."""

from augura_api.modules.corpus.curation import CuratedRef, apply_curation


def test_apply_curation_reorders_and_drops() -> None:
    by_id = {"a": "RecA", "b": "RecB", "c": "RecC"}
    refs = [CuratedRef(id="c", rationale="plus pertinent"), CuratedRef(id="a", rationale="ok")]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecC", "plus pertinent"), ("RecA", "ok")]  # 'b' écarté, ordre LLM


def test_apply_curation_ignores_hallucinated_and_dupes() -> None:
    by_id = {"a": "RecA"}
    refs = [CuratedRef(id="zzz", rationale="inventé"), CuratedRef(id="a", rationale="1"),
            CuratedRef(id="a", rationale="2")]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecA", "1")]  # id hors pool ignoré, doublon ignoré


def test_apply_curation_caps_at_max_results() -> None:
    by_id = {"a": "A", "b": "B", "c": "C"}
    refs = [CuratedRef("a", ""), CuratedRef("b", ""), CuratedRef("c", "")]
    out = apply_curation(refs, by_id, max_results=2)
    assert [rec for rec, _ in out] == ["A", "B"]


def test_apply_curation_empty_when_nothing_matches() -> None:
    out = apply_curation([CuratedRef("zzz", "x")], {"a": "A"}, max_results=10)
    assert out == []
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: FAIL — `ModuleNotFoundError: ... corpus.curation` (le module n'existe pas).

- [ ] **Step 3: Créer `curation.py` avec les types + `apply_curation`**

Créer `apps/api/src/augura_api/modules/corpus/curation.py` :

```python
"""Curation LLM des résultats live (re-ranking par abstract + rationale).

Frère de `pubmed.py` / `ctgov.py`. `Curator` est un Protocol injectable (tests sans
réseau) ; `LLMCurator` réutilise `run_structured_agent` (outil forcé + validation
Pydantic + 1 retry réparation). Le LLM ne renvoie QUE des ids ordonnés + rationale ;
le mapping vers les enregistrements déjà récupérés est déterministe (`apply_curation`),
donc aucune fabrication de contenu n'est possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel
from anthropic.types import ToolParam

from augura_api.core.llm.runtime import LLMClient, run_structured_agent

# Version du prompt de curation — épinglée dans la provenance des snapshots.
CURATION_PROMPT_VERSION = "curate-v1"

# Borne de tokens : on tronque le texte de chaque candidat (abstract / résumé CT.gov).
_MAX_TEXT = 1200


@dataclass(frozen=True)
class CurationCandidate:
    """Candidat soumis au LLM : id stable + titre + texte jugeable (abstract ou résumé)."""

    id: str
    title: str
    text: str


@dataclass(frozen=True)
class CuratedRef:
    """Sortie de curation par item : l'ordre de la liste porte le classement."""

    id: str
    rationale: str


def apply_curation[T](
    refs: list[CuratedRef], by_id: dict[str, T], *, max_results: int
) -> list[tuple[T, str]]:
    """Mappe les refs ordonnées du LLM → (enregistrement, rationale), de façon
    déterministe : ignore les ids hors `by_id` (hallucinés) et les doublons, cape à
    `max_results`. Renvoie [] si rien ne matche (l'appelant décide du repli)."""
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

(Les imports `BaseModel`/`ToolParam`/`run_structured_agent`/`LLMClient` servent au Task 2 ; ils sont posés ici pour éviter un second remaniement d'en-tête. `ruff` peut signaler des imports inutilisés tant que le Task 2 n'est pas fait — exécuter les deux tasks avant le lint final, ou ajouter le code du Task 2 dans la foulée.)

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** *(uniquement si commits validés par l'utilisateur)*

```bash
git add apps/api/src/augura_api/modules/corpus/curation.py apps/api/tests/test_corpus_curation.py
git commit -m "feat(corpus): curation types + apply_curation pur (re-ranking)"
```

---

### Task 2: `curation.py` — `Curator` Protocol + `LLMCurator`

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/curation.py`
- Test: `apps/api/tests/test_corpus_curation.py`

- [ ] **Step 1: Ajouter les tests qui échouent (LLMCurator mocké)**

Ajouter en tête de `tests/test_corpus_curation.py` (imports) :

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

> ⚠️ Le Task 1 a déjà créé ce fichier avec
> `from augura_api.modules.corpus.curation import CuratedRef, apply_curation`.
> **Fusionner** dans le bloc ci-dessus (ne pas dupliquer `CuratedRef`/`apply_curation`,
> sinon ruff F811/F401).

Les helpers de client LLM factice (même pattern que `test_agents_dag.py`), dans le même fichier :

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

Puis les tests :

```python
async def test_llm_curator_returns_ordered_refs() -> None:
    client = _FakeClient(_msg({"selected": [
        {"id": "2", "rationale": "RCT directement sur la question"},
        {"id": "1", "rationale": "pertinent mais observationnel"},
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
    client = _FakeClient()  # aucune réponse → si appelé, lèverait IndexError
    curator = LLMCurator(client, "m")  # type: ignore[arg-type]
    assert await curator.curate("q", "pubmed", [], max_results=5) == []
    assert client.messages.calls == 0
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: FAIL — `ImportError: cannot import name 'LLMCurator'`.

- [ ] **Step 3: Implémenter `Curator` + `LLMCurator` dans `curation.py`**

Ajouter à la fin de `curation.py` :

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
    "description": "Renvoie les résultats les plus pertinents, classés du plus au moins "
    "pertinent, chacun avec un rationale court.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "id exact d'un candidat fourni"},
                        "rationale": {"type": "string", "description": "1 phrase de justification"},
                    },
                    "required": ["id"],
                },
            }
        },
        "required": ["selected"],
    },
}

_SYSTEM = (
    "Tu es un·e documentaliste biomédical·e. À partir d'une question de recherche et "
    "d'une liste de résultats (id, titre, texte), sélectionne et CLASSE les plus "
    "pertinents, du plus au moins pertinent. À pertinence égale, remonte les preuves "
    "les plus fortes (méta-analyses / revues systématiques / RCT > observationnel > "
    "autre). N'invente JAMAIS d'id : n'utilise que les id fournis. Donne un rationale "
    "d'une phrase par résultat retenu. Écarte les résultats hors sujet."
)


def _render(candidates: list[CurationCandidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        text = c.text[:_MAX_TEXT]
        lines.append(f"[{c.id}] {c.title}\n{text}")
    return "\n\n".join(lines)


class LLMCurator:
    """Implémentation réelle : un appel `run_structured_agent` par source."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        if not candidates:
            return []
        user = (
            f"Question : {query}\nSource : {source}\n"
            f"Sélectionne au plus {max_results} résultats parmi :\n\n{_render(candidates)}"
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

- [ ] **Step 4: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_corpus_curation.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint + types du module**

Run: `uv run ruff check src/augura_api/modules/corpus/curation.py && uv run pyright src/augura_api/modules/corpus/curation.py`
Expected: aucune erreur (plus d'imports inutilisés).

- [ ] **Step 6: Commit** *(si validé)*

```bash
git add apps/api/src/augura_api/modules/corpus/curation.py apps/api/tests/test_corpus_curation.py
git commit -m "feat(corpus): LLMCurator (re-ranking par abstract via run_structured_agent)"
```

---

### Task 3: Contrat — `rationale` sur `RetrievedItemOut` + `FrozenResult`

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py:143-150` (`RetrievedItemOut`)
- Modify: `apps/api/src/augura_api/modules/corpus/schemas.py:171-181` (`FrozenResult`)

- [ ] **Step 1: Ajouter le champ `rationale` à `RetrievedItemOut`**

Dans `RetrievedItemOut`, après `annotation: str | None = None`, ajouter :

```python
    rationale: str | None = None  # justification de curation (None si non curé)
```

- [ ] **Step 2: Ajouter le champ `rationale` à `FrozenResult`**

Dans `FrozenResult`, après `annotation: str | None = None`, ajouter :

```python
    rationale: str | None = None  # justification de curation gelée (provenance)
```

- [ ] **Step 3: Vérifier les types**

Run: `uv run pyright src/augura_api/modules/corpus/schemas.py`
Expected: aucune erreur.

- [ ] **Step 4: Commit** *(si validé)*

```bash
git add apps/api/src/augura_api/modules/corpus/schemas.py
git commit -m "feat(corpus): champ rationale sur RetrievedItemOut + FrozenResult"
```

---

### Task 4: `retrieval.py` — `RetrievedItem.rationale` + sur-récupération + curation

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/retrieval.py`
- Test: `apps/api/tests/test_corpus_retrieval.py`

- [ ] **Step 1: Ajouter les tests qui échouent (curator stub)**

Ajouter à `tests/test_corpus_retrieval.py` — d'abord un stub curator en bas de la zone des fakes (après `FakeCTGov`) :

```python
from augura_api.modules.corpus.curation import CurationCandidate, CuratedRef


class FakeCurator:
    """Renvoie les ids dans l'ordre inverse de réception, avec un rationale, et peut
    simuler une panne (raise) ou une sélection partielle."""

    def __init__(self, *, error: Exception | None = None, only: list[str] | None = None) -> None:
        self.error = error
        self.only = only
        self.calls: list[tuple[str, str, int]] = []  # (source, premier id, nb candidats)

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

Puis un helper `_retriever_c` et les tests (les `ART`/`STUDY` existants ont des ids `35319473` / `NCT01691846` ; ajouter un 2e de chaque pour tester le réordonnancement) :

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
    cur = FakeCurator()  # inverse l'ordre
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["40000000", "35319473"]  # ordre inversé par le curator
    assert pmg.items[0].rationale == "rat-40000000"
    ctg = next(g for g in r.groups if g.source == SOURCE_CTGOV)
    assert [i.id for i in ctg.items] == ["NCT02000000", "NCT01691846"]
    assert ctg.items[0].rationale == "rat-NCT02000000"
    # sur-récupération : pool = min(50, max(25, 5*2)) = 25
    assert pm.calls == [("search", "hba1c", 25)]
    assert ct.calls == [("search", "hba1c", 25)]


async def test_curation_failure_falls_back_to_relevance_order() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator(error=RuntimeError("LLM down"))
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]  # ordre source conservé
    assert all(i.rationale is None for i in pmg.items)  # pas de rationale en repli


async def test_curation_empty_selection_falls_back() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[])
    cur = FakeCurator(only=["zzz"])  # rien ne matche
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)
    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]  # repli relevance
    assert all(i.rationale is None for i in pmg.items)


async def test_known_item_is_not_curated() -> None:
    pm = FakePubMed(fetch_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator()
    r = await _retriever_c(pm, ct, cur).retrieve("35319473", today=DAY)
    assert cur.calls == []  # known-item jamais curé
    assert r.groups[0].items[0].rationale is None
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_corpus_retrieval.py -q`
Expected: FAIL — `TypeError: LiteratureRetriever.__init__() got an unexpected keyword argument 'curator'` (et `RetrievedItem` n'a pas `rationale`).

- [ ] **Step 3: Modifier `retrieval.py`**

3a. En-tête — ajouter l'import (après l'import `pubmed`) :

```python
from augura_api.core.llm.runtime import AgentInvalidOutput, AgentUpstreamError
from augura_api.modules.corpus.curation import (
    CurationCandidate,
    Curator,
    apply_curation,
)
```

3b. `RetrievedItem` (≈ ligne 53) — ajouter le champ après `annotation` :

```python
    rationale: str | None = None  # justification de curation (None si non curé)
```

3c. `LiteratureRetriever.__init__` (≈ ligne 121) — accepter le curator :

```python
    def __init__(
        self, pubmed: PubMedClient, ctgov: CTGovClient, *, curator: Curator | None = None
    ) -> None:
        self._pubmed = pubmed
        self._ctgov = ctgov
        self._curator = curator
```

3d. Ajouter le calcul de pool + deux helpers de curation (méthodes de la classe) :

```python
    def _pool(self, max_results: int) -> int:
        """Taille du pool sur-récupéré : pas de curation ⇒ exactement max_results
        (comportement historique inchangé) ; sinon min(50, max(25, max_results*2))."""
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
                f"{', '.join(s.interventions)}. Phase {s.phase}. Statut {s.status}.",
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

3e. Réécrire `_pubmed_topical` (≈ ligne 211) pour sur-récupérer puis curer :

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

3f. Réécrire `_ctgov_topical` (≈ ligne 223) de même :

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

Note : `RetrievedItem(...)` est ici appelé positionnellement (source, id, title, query_string, retrieval_date, record) + `rationale=` en kwarg — aligné sur la dataclass.

- [ ] **Step 4: Lancer les tests retrieval (anciens + nouveaux)**

Run: `uv run pytest tests/test_corpus_retrieval.py -q`
Expected: PASS. Les anciens tests (`curator` absent → `_pool` = max_results) gardent `pm.calls == [("search", query, 5)]` ; les 4 nouveaux passent.

- [ ] **Step 5: Vérifier types + contrats d'import**

Run: `uv run pyright src/augura_api/modules/corpus/retrieval.py && uv run lint-imports`
Expected: aucune erreur (`corpus` peut importer `core.llm`).

- [ ] **Step 6: Commit** *(si validé)*

```bash
git add apps/api/src/augura_api/modules/corpus/retrieval.py apps/api/tests/test_corpus_retrieval.py
git commit -m "feat(corpus): sur-récupération + curation par source dans le retrieve"
```

---

### Task 5: `snapshot_service.py` — propager `rationale` (réponse + payload gelé)

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/snapshot_service.py:41-49` (`to_retrieve_response`)
- Modify: `apps/api/src/augura_api/modules/corpus/snapshot_service.py:70-81` (`_build_payload`)
- Test: `apps/api/tests/test_corpus_freeze.py`

- [ ] **Step 1: Écrire le test qui échoue**

Vérifier d'abord le style de `tests/test_corpus_freeze.py` (`uv run pytest tests/test_corpus_freeze.py -q` doit déjà passer). Ajouter un test ciblé `to_retrieve_response` :

```python
from datetime import date

from augura_api.modules.corpus.retrieval import (
    RetrievalResult, RetrievedItem, SourceGroup,
)
from augura_api.modules.corpus.snapshot_service import to_retrieve_response


def test_to_retrieve_response_carries_rationale() -> None:
    item = RetrievedItem(
        "pubmed", "1", "T", "term", date(2026, 6, 21), {"pmid": "1"}, rationale="le plus pertinent",
    )
    res = RetrievalResult("q", ["pubmed"], False, None, [SourceGroup("pubmed", "term", [item])])
    out = to_retrieve_response(res)
    assert out.groups[0].items[0].rationale == "le plus pertinent"
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `uv run pytest tests/test_corpus_freeze.py::test_to_retrieve_response_carries_rationale -q`
Expected: FAIL — `AssertionError` (rationale vaut None car non propagé) ou `TypeError` si le champ kwarg n'est pas reconnu (selon l'état des autres tasks ; Task 3 doit être faite avant).

- [ ] **Step 3: Propager `rationale` dans `to_retrieve_response`**

Dans la construction `schemas.RetrievedItemOut(...)`, après `annotation=i.annotation,` ajouter :

```python
                        rationale=i.rationale,
```

- [ ] **Step 4: Propager `rationale` dans `_build_payload`**

Dans le dict de chaque résultat (`results: [...]`), après `"annotation": r.annotation,` ajouter :

```python
                "rationale": r.rationale,
```

- [ ] **Step 5: Lancer, vérifier le succès**

Run: `uv run pytest tests/test_corpus_freeze.py -q`
Expected: PASS (anciens + nouveau). Note compat : les anciens snapshots stockés sans clé `rationale` se relisent via `FrozenResult(**r)` (champ optionnel `None`) et `verify_content_hash` recalcule sur le payload stocké tel quel → hash inchangé.

- [ ] **Step 6: Commit** *(si validé)*

```bash
git add apps/api/src/augura_api/modules/corpus/snapshot_service.py apps/api/tests/test_corpus_freeze.py
git commit -m "feat(corpus): rationale propagé en réponse retrieve + payload snapshot"
```

---

### Task 6: `router.py` — construire le curator + enrichir l'event `meta`

**Files:**
- Modify: `apps/api/src/augura_api/modules/corpus/router.py:18-36` (imports)
- Modify: `apps/api/src/augura_api/modules/corpus/router.py:192-242` (`literature_retrieve`)

- [ ] **Step 1: Ajouter les imports**

Après `from augura_api.modules.corpus.ctgov import CTGovApiClient`, ajouter :

```python
from augura_api.modules.corpus.curation import CURATION_PROMPT_VERSION, Curator, LLMCurator
```

- [ ] **Step 2: Construire le curator dans `literature_retrieve`**

Au début de `literature_retrieve`, après `sources = set(req.sources) if req.sources else None`, ajouter :

```python
    # Curator construit une fois par requête (réutilise le client Anthropic). Pas de clé
    # ⇒ curator=None ⇒ retrieve se comporte comme avant (zéro régression).
    curator: Curator | None = None
    try:
        curator = LLMCurator(get_anthropic_client(settings), settings.agent_model_fast)
    except AgentUpstreamError:
        curator = None
```

- [ ] **Step 3: Passer le curator au retriever + enrichir `meta`**

Dans `gen()`, passer `curator=curator` au `LiteratureRetriever(...)` :

```python
                retriever = LiteratureRetriever(
                    NCBIPubMedClient(http, api_key=settings.ncbi_api_key),
                    CTGovApiClient(ctgov_http, base_url=settings.ctgov_relay_url),
                    curator=curator,
                )
```

Et enrichir l'event `meta` (la curation ne s'applique qu'au topique) :

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

- [ ] **Step 4: Vérifier types + que la route est toujours montée**

Run: `uv run pyright src/augura_api/modules/corpus/router.py && uv run pytest tests/test_app_routes.py -q`
Expected: aucune erreur de types ; les tests de routes passent (route `/corpus/literature/retrieve` toujours enregistrée). La logique de curation est couverte au niveau `retrieval.py` (Task 4) ; ce câblage est trivial.

- [ ] **Step 5: Commit** *(si validé)*

```bash
git add apps/api/src/augura_api/modules/corpus/router.py
git commit -m "feat(corpus): câble le curator dans /literature/retrieve + meta enrichi"
```

---

### Task 7: Régénérer l'OpenAPI + le client TS (drift-check CI)

**Files:**
- Modify: `packages/api-client/openapi.json`
- Modify: `packages/api-client/src/schema.d.ts`

- [ ] **Step 1: Régénérer l'OpenAPI**

Run (depuis la racine du repo) : `uv run python apps/api/scripts/dump_openapi.py`
Expected: `packages/api-client/openapi.json` régénéré. `git diff --stat packages/api-client/openapi.json` doit montrer l'ajout de `rationale` sur les schémas `FrozenResult` (et `RetrievedItemOut` s'il est atteignable depuis le graphe). Si aucun diff : les modèles ne sont pas atteignables ⇒ rien à faire, continuer.

- [ ] **Step 2: Régénérer le client TS**

Run: `npm --prefix packages/api-client run generate`
Expected: `packages/api-client/src/schema.d.ts` régénéré (NE JAMAIS l'éditer à la main).

- [ ] **Step 3: Commit** *(si validé)*

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regen OpenAPI/client pour rationale de curation"
```

---

### Task 8: Frontend — afficher le rationale + le geler + provenance

**Files:**
- Modify: `apps/web/src/workspace/literature/literatureClient.js:17-30` (`flattenItem`)
- Modify: `apps/web/src/workspace/literature/literatureClient.js:93-114` (`saveSnapshot`)
- Modify: `apps/web/src/workspace/literature/ResultCard.jsx`
- Modify: `apps/web/src/workspace/literature/AdHocQuery.jsx` (reducer + `doSave`)

- [ ] **Step 1: `flattenItem` porte le rationale**

Dans `literatureClient.js`, dans l'objet retourné par `flattenItem`, après `annotation: item.annotation ?? null,` ajouter :

```javascript
    rationale: item.rationale ?? null,
```

(Placer cette ligne AVANT le spread `...rec` n'a pas d'importance : `record` n'a pas de clé `rationale`. Le laisser juste après `annotation` est le plus lisible.)

- [ ] **Step 2: `saveSnapshot` gèle le rationale + accepte la provenance**

Modifier la signature et le mapping de `saveSnapshot` :

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

- [ ] **Step 3: `ResultCard` affiche le rationale**

Dans `ResultCard.jsx`, juste avant le bloc `{showAbstract && result.abstract && (...)}` (≈ ligne 113), insérer un encart rationale (visible hors readOnly comme en frozen) :

```jsx
      {result.rationale && (
        <p className="mt-2 rounded-md bg-secondary/30 px-2.5 py-1.5 text-[11.5px] italic leading-relaxed text-muted-foreground">
          <span className="font-medium not-italic text-foreground/70">Why: </span>{result.rationale}
        </p>
      )}
```

- [ ] **Step 4: `AdHocQuery` capture la provenance du `meta` et la passe au Save**

4a. `initialState` (≈ ligne 34) — ajouter après `frozenAt: null,` :

```javascript
  modelVersion: null,
  promptVersion: null,
```

4b. Reducer `ev_meta` (≈ ligne 60) — capturer les versions :

```javascript
    case 'ev_meta':
      return { ...state, sources: action.sources || state.sources, knownItem: !!action.known_item, modelVersion: action.model_version ?? null, promptVersion: action.prompt_version ?? null, groups: blankGroups(action.sources || state.sources) }
```

4c. `onEvent` du `meta` (≈ ligne 132) — transmettre les champs :

```javascript
        if (ev.type === 'meta') dispatch({ type: 'ev_meta', sources: ev.sources, known_item: ev.known_item, model_version: ev.model_version, prompt_version: ev.prompt_version })
```

4d. `doSave` (≈ ligne 172) — passer la provenance à `saveSnapshot` :

```javascript
      await saveSnapshot({ query: state.question, sources: state.sources, studyId: scope === 'study' ? study?.id ?? null : null, items, modelVersion: state.modelVersion ?? undefined, promptVersion: state.promptVersion ?? undefined })
```

(`?? undefined` ⇒ si le `meta` n'a pas fourni de version — known-item, ou pas de clé — on retombe sur les défauts `MODEL_VERSION`/`PROMPT_VERSION` de `literatureClient.js`.)

- [ ] **Step 5: Lint + build front**

Run (depuis `apps/web/`) : `npm run lint && npm run build`
Expected: aucune erreur ESLint, build OK.

- [ ] **Step 6: Vérification visuelle (preview)**

Suivre le workflow preview : lancer le serveur, ouvrir le workbench Littérature, lancer une recherche, vérifier que les cartes affichent « Why: … » et que l'ordre reflète la curation ; geler un snapshot et rouvrir « Saved evidence » pour confirmer la persistance du rationale.

- [ ] **Step 7: Commit** *(si validé)*

```bash
git add apps/web/src/workspace/literature/literatureClient.js apps/web/src/workspace/literature/ResultCard.jsx apps/web/src/workspace/literature/AdHocQuery.jsx
git commit -m "feat(web): affiche le rationale de curation + le gèle dans les snapshots"
```

---

### Task 9: Gate CI complète

**Files:** aucun (vérification)

- [ ] **Step 1: Suite backend complète + lint + types + contrats**

Run (depuis `apps/api/`) :

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q
```

Expected: tout vert. (Les `@pytest.mark.integration` sont sautés sans `AUGURA_DATABASE_URL` — c'est attendu.)

- [ ] **Step 2: Drift-check OpenAPI**

Run (depuis la racine) :

```bash
uv run python apps/api/scripts/dump_openapi.py && git diff --exit-code packages/api-client/openapi.json
```

Expected: code de sortie 0 (aucun diff non committé — Task 7 a déjà régénéré).

- [ ] **Step 3: Front lint + build**

Run (depuis `apps/web/`) : `npm run lint && npm run build`
Expected: vert.

- [ ] **Step 4: Commit final éventuel** *(si validé et s'il reste des changements de formatage)*

```bash
git status   # vérifier qu'il ne reste rien d'inattendu
```

---

## Notes de portée

- **Pas dans A** (réservé à B / item C) : workbench de génération+validation de mots-clés (MeSH-UID, openFDA, MAUDE, tags vert/ambre), boucle agentique tool-use, cache de résultats, sources FDA/MAUDE live.
- **Latence** : +1 appel LLM par source avant émission du `group` (décision « groupe curé d'un coup »). Atténuée par `agent_model_fast` + pool borné (25). Le front montre déjà un état de chargement par groupe (`loading: true`).
