# Chantier A — Curation par abstract sur `/corpus/literature/retrieve`

**Date :** 2026-06-21
**Statut :** design validé (en attente de relecture spec)
**Périmètre :** backend (module `corpus`) + petite touche front (afficher le rationale, stamper la provenance au freeze)

## Contexte & objectif

`POST /corpus/literature/retrieve` fan-out PubMed + CT.gov en direct, groupé par
source, streamé en NDJSON (`meta` → `group`/source → `done`). Aujourd'hui la
récupération est « dumb » : PubMed `esearch` avec `sort=relevance` → `efetch` des
top-N verbatim ; CT.gov via l'ordre de pertinence natif de l'API v2. **Aucune
relecture d'abstract, aucune priorisation par niveau de preuve, aucun rationale.**

C'est la seule régression de *qualité de récupération* encore réelle vs l'ancienne
branche `augura/corpus-live` (dont l'agent lisait les abstracts et renvoyait « les N
plus pertinents / au plus haut niveau de preuve » avec un rationale).

**Objectif :** restaurer ce comportement de **curation** sur le chemin topique du
`retrieve`, de façon typée, bornée, reproductible et bon marché.

## Décisions (issues du brainstorming)

1. **Comportement = curation parité.** Sur-récupérer un pool large, le LLM lit les
   candidats, renvoie les N meilleurs classés par pertinence + force de preuve, avec
   un rationale par item. **La curation peut écarter les résultats faibles.**
2. **Deux sources.** PubMed curé par abstract ; CT.gov curé par ses champs
   structurés (titre / conditions / interventions / phase / statut).
3. **Streaming = groupe curé d'un coup.** Le `group` d'une source n'est émis qu'une
   fois la curation finie. Le contrat NDJSON `meta|group|done` est **conservé** ; le
   front affiche juste un état « curation… ». Changement front minimal.
4. **Toujours active, dégradation gracieuse.** Curation par défaut sur chaque
   `retrieve`. Pas de clé Anthropic / panne LLM → repli silencieux sur l'ordre
   relevance top-N actuel (comme `expand_pubmed_query` dégrade). Pas de flag opt-in.
5. **Approche = agent structuré, un appel par source.** Réutilise
   `run_structured_agent` (outil forcé + validation Pydantic + 1 retry réparation) et
   `settings.agent_model_fast`. Le LLM ne renvoie **que des ids ordonnés + rationale**.

## Non-objectifs (YAGNI)

- Pas de boucle agentique tool-use (approche 3) — c'est le terrain de la « grosse
  feature » B (workbench mots-clés), pas de A.
- Pas de scoring numérique par item (approche 2).
- Pas de `evidence_tier` produit par le LLM : on garde l'`evidence_type` déterministe
  déjà dérivé dans `pubmed.py`. Le LLM est *instruit* de pondérer la force de preuve
  dans son classement, mais ne fabrique aucun champ de preuve.
- Pas de cache de résultats (item C séparé).
- Pas de re-validation de mots-clés / MeSH-UID / openFDA (feature B).

## Architecture

Nouveau fichier `apps/api/src/augura_api/modules/corpus/curation.py`, frère de
`pubmed.py` / `ctgov.py`, qui isole toute la logique LLM :

- **`Curator` Protocol** — injectable (les tests fournissent un faux curator sans
  réseau) :
  ```
  async def curate(query, source, candidates: list[CurationCandidate]) -> list[CuratedRef]
  ```
- **`CurationCandidate`** (dataclass) : `id`, `title`, `text` — `text` = abstract
  (PubMed) ou résumé des champs structurés (CT.gov), tronqué (~1200 c) pour borner les
  tokens.
- **`CuratedRef`** (sortie) : `id`, `rationale`. L'**ordre de la liste** porte le
  classement.
- **`LLMCurator`** : implémentation réelle. Outil forcé renvoyant
  `{ "selected": [ { "id": str, "rationale": str }, ... ] }` (≤ `max_results`).
  Système : « documentaliste biomédical·e ; classe par pertinence à la question, en
  remontant les preuves plus fortes (méta-analyses / revues systématiques / RCT >
  observationnel > autre) ; rationale court par item ; n'invente aucun id ».
- **Constante** `CURATION_PROMPT_VERSION = "curate-v1"` exportée pour la provenance.

`retrieval.py` importe le **`Curator` Protocol** (pas le client Anthropic) →
couches propres. `curation.py` importe `core.llm.runtime` ; `corpus` peut importer
`core.llm` (contrat `lint-imports` respecté).

## Flux de données

Chemin **topique uniquement**. Le known-item (PMID/DOI/titre/NCT) reste un lookup
exact à 1 résultat — **jamais curé**.

```
_topical(query, srcs, max_results, day, filters)
  pour chaque source demandée (en parallèle, via le gather existant) :
    1. sur-récupérer un pool : POOL = min(50, max(25, max_results * 2))
       (borné par retmax ≤ 50 côté PubMed ; CT.gov pageSize équivalent)
    2. si curator présent :
         rendre les candidats (id + titre + texte tronqué)
         → curator.curate(query, source, candidates) → [CuratedRef] ordonné
         → mapper ids → enregistrements DÉJÀ récupérés (le LLM n'émet que des ids
           → zéro fabrication de contenu), réordonner, garder max_results,
           attacher rationale.
    3. si curator absent : trim relevance top-N (= comportement actuel).
  → SourceGroup(source, query_string, items[, note])
```

POOL par défaut = 25 (`max_results` défaut 10 → pool 25, borné à 50).

**Garde-fous déterministes** (dans `retrieval.py`, hors LLM) :
- ids hors pool (hallucinés) → ignorés ;
- doublons d'id → dédupliqués (premier gardé) ;
- **sortie vide / tout filtré alors qu'il y avait des candidats → repli relevance
  top-N** (jamais de groupe vide par faute de curation).

## Changements de contrat (⇒ regen OpenAPI + client, drift-check CI)

- `RetrievedItem` (dataclass `retrieval.py`) : nouveau champ `rationale: str | None = None`.
- `schemas.RetrievedItemOut` : `rationale: str | None = None`.
- `schemas.FrozenResult` : `rationale: str | None = None` (persistance snapshot).
- Event **`meta`** du stream enrichi : `curated: bool`, `model_version: str | None`,
  `prompt_version: str | None` (= `CURATION_PROMPT_VERSION`). Fournit au front la
  provenance pour *geler* un snapshot reproductible (les champs `model_version` /
  `prompt_version` du snapshot existent déjà, en attente de ça).
- `snapshot_service.to_retrieve_response` : passe `rationale=i.rationale`.
- `snapshot_service._build_payload` : ajoute `"rationale": r.rationale` aux results.

**Compat snapshots** : `rationale` optionnel. Les anciens snapshots (payload sans la
clé) se relisent sans casse — `FrozenResult(**r)` tolère l'absence (défaut `None`), et
`verify_content_hash` recalcule sur le payload **stocké tel quel** → hash inchangé.
Les nouveaux snapshots incluent `rationale` dans le hash.

Après contrat : `uv run python apps/api/scripts/dump_openapi.py` puis
`npm --prefix packages/api-client run generate`.

## Gestion d'erreur / dégradation

- L'appel curation est enveloppé : `AgentUpstreamError` / `AgentInvalidOutput` → log
  `warning` + repli relevance top-N **sans rationale** ; jamais d'exception remontée.
- Combiné au `_safe_group` existant : une source qui tombe (403 CT.gov, panne LLM) ne
  casse ni le fan-out ni le stream — l'autre source remonte normalement.
- Pas de clé Anthropic → `curator=None` (le routeur l'attrape comme pour l'embedder) →
  `retrieve` se comporte exactement comme aujourd'hui. **Zéro régression possible.**

## Câblage routeur

Dans `literature_retrieve` :
- construire le curator depuis `get_anthropic_client(settings)` ; sur
  `AgentUpstreamError` → `curator=None` (même pattern que l'embedder dans `/literature`).
- passer `curator` + `settings.agent_model_fast` à `LiteratureRetriever`.
- l'`AsyncClient` LLM n'est pas un HTTP request-scoped : `LLMCurator` détient le
  client Anthropic injecté ; le `gen()` NDJSON reste inchangé (le `group` arrive déjà
  curé). Le `meta` event porte désormais `curated` / `model_version` / `prompt_version`.

## Tests (CI : ruff · pyright strict · lint-imports · pytest · drift-check OpenAPI)

- **`curation.py`** (LLM mocké via le `LLMClient` Protocol) : réordonne selon la
  sortie ; écarte les non-sélectionnés ; ignore les ids hallucinés ; déduplique ;
  tronque le texte ; sortie outil invalide → `AgentInvalidOutput` (testé au niveau
  `run_structured_agent` déjà couvert, ici on teste le mapping).
- **`retrieval.py`** (curator stub) : sur-récup → cure → trim à `max_results` ;
  known-item **non curé** ; `curator=None` → top-N relevance inchangé ; curator qui
  lève → repli gracieux + stream intact ; sortie vide → repli relevance top-N.
- **régression** : les tests existants du `retrieve` passent (ajouter `curator=None`
  ou un stub selon le cas).

## Fichiers touchés

| Fichier | Changement |
|---|---|
| `corpus/curation.py` | **NEW** — `Curator` Protocol, `LLMCurator`, candidats, outil + sortie, `CURATION_PROMPT_VERSION` |
| `corpus/retrieval.py` | sur-récup + curation dans `_topical` ; champ `rationale` ; garde-fous |
| `corpus/router.py` | build curator ; passe au retriever ; `meta` enrichi |
| `corpus/schemas.py` | `rationale` sur `RetrievedItemOut` + `FrozenResult` |
| `corpus/snapshot_service.py` | passe `rationale` (response + payload) |
| `apps/web/src/workspace/literature/literatureClient.js` + UI | afficher rationale ; stamper model/prompt au freeze |
| tests backend | `curation.py` + `retrieval.py` |
| `packages/api-client` | regen OpenAPI + client |

## Risques / points ouverts

- **Latence** : +1 appel LLM par source (≈2–5 s) avant l'émission du groupe. Atténué
  par le modèle `agent_model_fast` et le pool borné (25). Accepté (décision streaming).
- **Troncature d'abstract** : 1200 c peut couper un abstract long ; suffisant pour
  juger la pertinence. Paramétrable si besoin.
- **Coût tokens** : ~25 candidats × ~1200 c ≈ ~10–15k tokens d'entrée par source.
  Borné, sur modèle fast.

## Politique de commit

`CLAUDE.md` : « ne commit/push/déploie que sur demande explicite ». La spec est
**écrite mais non committée** ; commit sur demande.
