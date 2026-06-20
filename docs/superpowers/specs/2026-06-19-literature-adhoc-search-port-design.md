# Spec — Port de la recherche ad-hoc littérature (+ retrait Browse)

> Date : 2026-06-19 · Branche : `Quentin` · Statut : **validé, en attente de relecture**
> Source de l'UI portée : `lucis-dashboard@corpus-live` → `src/literature/AdHocQuery/*`
> Cible : `augura-platform` (`apps/web` + `apps/api/modules/corpus`)

## 1. Contexte & objectif

La page Littérature actuelle ([apps/web/src/workspace/CorpusPage.jsx](../../../apps/web/src/workspace/CorpusPage.jsx)) a 3 sous-onglets — **Browse**, **Study matches** (recherche sémantique), **Ad-hoc query** (textarea PubMed simple). L'utilisateur veut :

1. **Retirer Browse.**
2. Remplacer l'**ad-hoc query** par la recherche riche multi-source de l'ancienne branche (capture de référence) : sources PubMed + ClinicalTrials.gov, filtres date & type d'étude, *Recent queries*, *Saved evidence*, résultats groupés par source, Keep/Dismiss, Save to study/standalone.
3. (Décidé en brainstorming) ajouter une action **« Add to corpus »** pour que la recherche sémantique « Study matches » ait de quoi se nourrir.

**Constat clé :** le backend `corpus` actuel est déjà largement capable. Existent déjà :
- `POST /corpus/literature/retrieve` — fan-out PubMed + CT.gov, streamé en NDJSON (`meta → group(s) → done`), routage known-item (PMID/DOI/titre→PubMed, NCT→CT.gov). ([router.py:147](../../../apps/api/src/augura_api/modules/corpus/router.py#L147))
- `POST/GET /corpus/literature/snapshots/{id}` — gel reproductible (content-hash). ([router.py:182](../../../apps/api/src/augura_api/modules/corpus/router.py#L182))
- `POST/GET /corpus/literature/sessions(+events)` — sessions + journal d'événements. ([router.py:200](../../../apps/api/src/augura_api/modules/corpus/router.py#L200))

## 2. Périmètre

**Inclus**
- Retrait du sous-onglet Browse.
- Port de l'UI riche, branchée à 100 % sur les endpoints réels (règle no-mock).
- **Backend : filtres date + type d'étude** sur `retrieve`.
- **Backend : `GET /corpus/literature/snapshots`** (liste) — pour *Saved evidence*.
- **Backend : `POST /corpus/literature/ingest`** (par PMIDs) — pour « Add to corpus ».

**Différé** (caché côté UI tant que non backé — sinon ce serait du mock)
- **Cache** → la distinction *Search sources* (cache-first) vs *Refresh from source* (bypass) ; pour l'instant **un seul bouton** « Search sources » (toujours live).
- **Panneau d'activité agent** → le stream n'émet pas d'events `intent`/`agent_activity`.

**Hors périmètre / non porté**
- Mode démo et `demoFixture.js` (interdit par la règle no-mock).
- L'API Vercel serverless de l'ancien repo (`api/literature.js`) — on a déjà FastAPI.
- Restauration des filtres à la ré-ouverture d'une *recent query* (pas de cache → on relance live).
- Ingestion CT.gov (l'ingestion corpus est PubMed-only aujourd'hui) → « Add to corpus » désactivé sur un résultat CT.gov, avec note honnête.

## 3. Architecture backend (`apps/api/src/augura_api/modules/corpus`)

### 3.1 Filtres sur `retrieve`
- **Schéma** ([schemas.py:129](../../../apps/api/src/augura_api/modules/corpus/schemas.py#L129)) — étendre `LiteratureRetrieveRequest` :
  - `date_range: Literal["any","1y","5y","10y"] = "any"`
  - `study_types: list[Literal["rct","observational","systematic_review","meta_analysis"]] = []`
- **Plomberie** — threader les filtres dans `LiteratureRetriever.retrieve() → _topical() → _pubmed_topical()/_ctgov_topical()` ([retrieval.py:114](../../../apps/api/src/augura_api/modules/corpus/retrieval.py#L114)). Étendre les `Protocol` `PubMedClient.search` / `CTGovClient.search` (+ implémentations réelles + fakes de test).
  - **PubMed** ([pubmed.py:173](../../../apps/api/src/augura_api/modules/corpus/pubmed.py#L173)) : ajouter à `_esearch` les params `mindate`/`maxdate` (calculés depuis `date_range`, année courante − N) + `datetype=pdat`. Types → termes `[pt]` combinés `(query) AND (a[pt] OR b[pt])` :
    | study_type | terme PubMed |
    |---|---|
    | rct | `Randomized Controlled Trial[pt]` |
    | meta_analysis | `Meta-Analysis[pt]` |
    | systematic_review | `Systematic Review[pt]` |
    | observational | `Observational Study[pt]` |
  - **CT.gov** ([ctgov.py:88](../../../apps/api/src/augura_api/modules/corpus/ctgov.py#L88)) : date via `filter.advanced=AREA[StudyFirstPostDate]RANGE[<min>,MAX]` ; type via `aggFilters=studyType:int|obs`. **Mapping partiel assumé** : `observational`→`obs`, `rct`→`int` ; `systematic_review`/`meta_analysis` n'ont pas d'équivalent CT.gov → ignorés côté CT.gov (si **seuls** ces deux types sont cochés, CT.gov ne renvoie rien de filtré — comportement documenté, pas une erreur).
  - **Known-item** : le chemin `_known_item` ignore les filtres (un identifiant exact n'est pas filtré) — documenté en docstring.

### 3.2 Liste des snapshots — `GET /corpus/literature/snapshots`
- `LiveRepo.list_snapshots(tenant_id, *, study_id: UUID | None = None)` ([live_repo.py](../../../apps/api/src/augura_api/modules/corpus/live_repo.py)) — `select` scopé `org_id == tenant`, filtre optionnel `study_id`, tri `created_at desc`.
- Nouveau schéma léger `SnapshotSummary` : `id, study_id, query, sources, created_at, result_count` (on ne renvoie PAS `results` ni ne re-vérifie le hash pour une liste).
- Route `GET /corpus/literature/snapshots?study_id=` → `list[SnapshotSummary]`. La ré-ouverture d'un snapshot reste `GET …/snapshots/{id}` (résultats complets + vérif hash, déjà en place).

### 3.3 Ingestion par enregistrements — `POST /corpus/literature/ingest`
- Requête : `{ pmids: list[str] }` (1–50).
- Service : `fetch_by_ids(pmids)` (déjà dans `NCBIPubMedClient`) → réutilise la machinerie d'ingestion de `LiteratureService` (Document + Chunk + embedding optionnel, dédup par URL/tenant déjà existante).
- Réponse : `LiteratureSearchResult` (réutilisé : `found`, `ingested`, `embedded`, `documents`).
- **PubMed uniquement** — CT.gov non supporté à l'ingestion (gap connu).

### 3.4 Provenance des snapshots
Le `retrieve` n'utilise pas de LLM. Pour `SnapshotWriteRequest` (qui exige `model_version`/`prompt_version`), le front envoie des constantes de provenance du pipeline retrieve : `model_version="retrieve"`, `prompt_version="v1"` (pas d'expansion LLM dans ce chemin).

### 3.5 Contrat & CI
`uv run python scripts/dump_openapi.py` → `packages/api-client/openapi.json`, puis `npm --prefix packages/api-client run generate`. Gate CI complet : `ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest`.

## 4. Architecture frontend (`apps/web/src/workspace`)

### 4.1 `CorpusPage.jsx`
- Supprimer l'entrée `{ id:'browse', … }` du `SubTabs` ([CorpusPage.jsx:236](../../../apps/web/src/workspace/CorpusPage.jsx#L236)) et le bloc `{sub === 'browse' && (…)}` (lignes 244-291).
- `useState('browse')` → défaut sur l'onglet workbench (ex. `'query'`).
- Retirer le fetch devenu mort `useCollection('corpus_coverage')` (ligne 206) et les imports/`CORPUS_ICON` qui ne servaient qu'aux cartes Browse (garder `Library`, encore utilisé par l'`EmptyState`).
- **Conserver** `useCollection('corpus_sources')` (sert au sous-titre `total` + au gating empty-state).
- Onglets finaux : **Ad-hoc query** (workbench, par défaut) + **Study matches** (sémantique, inchangé).

### 4.2 Nouveau dossier `workspace/literature/`
Composants portés et adaptés aux primitives du repo (l'ancien repo utilise déjà Card/Button/Badge shadcn → restyle minimal) :
- `LiteratureWorkbench.jsx` — conteneur (état via `useReducer`), orchestre recherche/save/recent/saved.
- `QueryInput.jsx` — textarea + toggles sources (PubMed/CT.gov) + boutons date (Any/1y/5y/10y) + toggles type (RCT/Observational/Systematic review/Meta-analysis) + **un seul** bouton « Search sources ».
- `ResultsList.jsx` / `ResultCard.jsx` — résultats groupés par source, badges de comptage, abstract repliable, boutons **Keep/Dismiss**, bouton **Add to corpus** (désactivé si source = CT.gov).
- `RecentQueries.jsx` — liste repliable depuis `GET …/sessions`.
- `SavedEvidence.jsx` — liste repliable depuis `GET …/snapshots`, ré-ouverture lecture seule via `GET …/snapshots/{id}`.
- `SessionActions.jsx` — Save to study / Save standalone / New query / Discard.
- `StudyPicker.jsx` — modale, liste des études via la collection `studies` existante (dataClient).
- `literatureClient.js` — wrappers sur `apiFetch`/`apiJson` + **lecteur NDJSON** (`res.body.getReader()` + `TextDecoder`, buffer de lignes, `JSON.parse`, dispatch `type` ∈ `meta|group|done`). Aucun helper streaming n'existe aujourd'hui dans [api.js](../../../apps/web/src/api.js).

### 4.3 Flux de données (tout sur endpoints réels)
| UI | Endpoint |
|---|---|
| Recherche (résultats groupés) | `POST /corpus/literature/retrieve` (stream NDJSON) |
| Recent queries | `POST …/sessions` (1 par recherche) + `GET …/sessions` |
| Keep / Dismiss (audit) | `POST …/sessions/{id}/events` |
| Save to study / standalone | `POST …/snapshots` |
| Saved evidence (liste + ré-ouverture) | `GET …/snapshots` *(nouveau)* + `GET …/snapshots/{id}` |
| Add to corpus | `POST …/ingest` *(nouveau, PubMed only)* |
| StudyPicker | collection `studies` existante |

## 5. Gestion d'erreurs
- Stream : erreur réseau / `raise_for_status` côté serveur → carte d'erreur dans le groupe concerné ; `note` de groupe (ex. miss known-item) affichée telle quelle.
- `AbortController` pour annuler un stream en cours (changement de requête / New query).
- Save snapshot en échec → message inline (pas de toast global si le repo n'en a pas).
- `GET snapshot/{id}` avec divergence de hash → erreur dure remontée (déjà géré backend) → carte « preuve non vérifiable ».
- « Add to corpus » : succès = badge « ingéré » sur le résultat ; échec = message inline ; CT.gov = bouton désactivé + tooltip.

## 6. Tests
**Backend (pytest, clients injectés en fake — pattern existant)**
- `_esearch` construit bien `mindate/maxdate/datetype=pdat` selon `date_range`, et le `term` inclut les `[pt]` selon `study_types`.
- CT.gov : params `filter.advanced` / `aggFilters` selon filtres ; cas « seulement systematic_review/meta_analysis » → pas de filtre studyType CT.gov.
- `list_snapshots` : tenant-scoping (un tenant ne voit pas les snapshots d'un autre), filtre `study_id`.
- `POST /ingest` : `fetch_by_ids` appelé avec les PMIDs, dédup réutilisée.
**Frontend** : vérification via preview (le gate web CI = eslint). Lint `npm run lint`.

## 7. Découpage d'implémentation (pressenti — détaillé dans le plan)
1. **Backend filtres** : schémas + retrieval + pubmed/ctgov + tests.
2. **Backend `GET snapshots` + `POST ingest`** : repo + service + router + schémas + tests.
3. **OpenAPI** : dump + regen api-client.
4. **Front — retrait Browse** (CorpusPage).
5. **Front — workbench** : `literature/` + lecteur NDJSON + branchements.
6. **Vérif preview** + lint + gate CI complet.

## 8. Risques / points de vigilance
- **Mapping CT.gov imparfait** des types d'étude (assumé & documenté).
- **PubMed `[pt]` agressif** : trop de types cochés peut sur-filtrer → vérifier qu'au moins un résultat revient sur des requêtes types.
- **Corpus potentiellement vide** : Browse retiré + retrieve éphémère → « Study matches » dépend désormais de « Add to corpus » et de l'ingestion existante.
- **NDJSON sur Modal/Vercel** : confirmer que le streaming `application/x-ndjson` passe bout-en-bout en prod (sinon repli : lire la réponse complète puis splitter — le format ligne-à-ligne le permet).
- **Commit** : selon CLAUDE.md, **aucun commit/push sans demande explicite** — ce doc n'est pas committé tant que tu ne le demandes pas.
