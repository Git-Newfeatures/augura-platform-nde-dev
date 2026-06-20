# Design — Port B4 : enrichissement sémantique « à la volée »

**Date :** 2026-06-19
**Statut :** approuvé (design), à planifier
**Sous-système :** B4 (`enrich-propose/apply`) — dernière brique de la chaîne B (B1 ontologie → B2 `dag-llm` → B3 `picot-parse` → **B4 enrich** → B5 front).

## 1. Contexte & objectif

La DAG Generation (B2, `POST /causal/dag`) fonctionne : le LLM **propose** de nouveaux concepts/relations (`proposed_concepts` / `proposed_relations`, rendus en arêtes pointillées oranges), **mais rien ne les persiste**. La boucle d'enrichissement est ouverte : `modules/semantic/repo.py` est en lecture seule, il n'existe pas de route d'écriture, la RPC `upsert_semantic_release` est absente, et les surfaces front (`CausalEnrichPanel`/`EnrichmentSection`/`LearnFromQuestionPanel`) ont été volontairement omises (cf. `apps/web/src/workspace/SemanticLayerPage.jsx:12-13`).

Objectif : **fermer la boucle** — permettre d'enrichir la couche sémantique gouvernée (proposer + appliquer), en portant fidèlement la fonctionnalité de l'ancien repo, adaptée aux conventions de la plateforme.

## 2. Provenance (source du port)

- Repo : `Augura-Health/augura`, branche `data-intake-nde` (Nicolas Delporte). Working copy locale : `/Users/quentin/Desktop/Augure/lucis-dashboard`.
- Commit : **`98c1023`** « feat(data-intake): DAG generation refinements, semantic governed vocab, new docs » (2026-06-17) — le dernier commit de Nicolas, **non repris** lors du portage initial (preuve : `apps/api/.../causal/prompt.py:141` porte encore l'enum polarity drifté `["increases","decreases","mixed","unknown"]` que `governed-vocab.js` corrige en `["increases","decreases","neutral"]`).
- Fichiers source :
  - `api/enrich-propose.js` — coverage analysis + génération de propositions LLM (SSE).
  - `api/enrich-apply.js` — write-back versionné (4 chemins).
  - `src/semantic/governed-vocab.js` — enums gouvernés partagés.
  - `src/workspace/LearnFromQuestionPanel.jsx` (492 l.) — surface front de revue.
  - `supabase/migrations/20260610000000_create_semantic_schema.sql:258` — fonction `upsert_semantic_release`.

## 3. Décisions cadrantes (validées avec l'utilisateur)

1. **Gouvernance = globale, gated admin (port fidèle).** La couche sémantique est globale (tables en `public`, RLS `FOR SELECT` partagée par tous les tenants). L'enrichissement mute donc l'ontologie partagée ; l'**apply est réservé au rôle `owner`**. Garde-fous : workflow `pending_review`→`approved` + versioning `semantic_releases`. Écriture via fonction SQL `SECURITY DEFINER` (le rôle app n'a pas le write direct). **Pas** d'overlay par tenant.
2. **Exécution du *propose* = job background.** Le pipeline (long, multi-appels LLM) tourne via le moteur de jobs existant ; la progression passe par `set_progress()` (remplace les events SSE) ; le front poll le job. L'**apply reste synchrone**.
3. **Propositions stockées en artifact JSON** (via `core/storage.py`, comme `documents`) — **pas** de nouvelle table. L'apply reçoit le batch + la sélection dans le body (fidèle à l'original).

## 4. Architecture

Port fidèle découpé en 3 phases livrables indépendamment. Tout le code backend nouveau vit dans la tranche verticale `modules/semantic/` (le contrat import-linter `causal → semantic` est déjà autorisé).

### Phase 1 — Write-path (apply)

**SQL.** Port de `upsert_semantic_release(p_manifest jsonb, p_payload jsonb)` :
- Cible le schéma **`public`** (et non `semantic.*` comme l'original) et le **jeu de colonnes plateforme**.
- Upsert idempotent par table (`jsonb_populate_recordset` + `on conflict … do update`) pour : `taxonomy_concepts`, `taxonomy_synonyms`, `taxonomy_standard_codes`, `ontology_relations`, `ontology_relation_evidence`, `ontology_relation_qualifiers` (les seules tables écrites par l'enrichissement).
- Gère `semantic_releases` : insère la nouvelle ligne de release (depuis `p_manifest`) et bascule `is_current` (append-only, une seule courante) — la table plateforme a la forme `{semantic_release_version pk, taxonomy_version, causal_ontology_version, dq_ontology_version, omop_cdm_version, source, manifest jsonb, imported_at, is_current}`.
- `SECURITY DEFINER`, propriétaire privilégié, `set search_path` explicite ; `grant execute` au rôle applicatif.
- **Livraison** : ajout dans `apps/api/supabase/functions.sql` (source du bundle) **+** migration alembic `0002+` **idempotente** (`CREATE OR REPLACE FUNCTION`) **+** application à la DB live via MCP Supabase (invariant : le déploiement Modal n'applique ni migrations ni seed).

**Route.** `POST /semantic/enrich/apply`, **`require_role("owner")`**. 4 chemins (port de `enrich-apply.js`) :
- `proposals` + `selected_concept_ids` + `selected_relation_ids` → filtre les rows approuvés (cascade vers synonyms/codes/evidence/qualifiers), stampe `approved`/`active`, bump **minor** si concepts ajoutés sinon **patch**.
- `direct_relations` → relations légères (sans IDs) depuis les proposals du DAG : valide que les concepts existent, assigne `ENRR_{date}_{NNN}`, evidence auto-stub si absente, bump **patch**. Renvoie un `relation_id_map` (réconciliation des IDs provisoires du DAG).
- `deactivate_relation` → désactive une relation jugée fausse (bump patch, `review_status='deprecated'`).
- `add_qualifier` → ajoute un qualifier restreignant l'applicabilité d'une relation (bump patch).

**Repo.** Une **seule** méthode d'écriture `apply_release(manifest, payload)` qui appelle la RPC ; le reste de `repo.py` reste en lecture.

### Phase 2 — Propose pipeline (+ governed-vocab, + fix polarity)

**Enums gouvernés.** Nouveau module `modules/semantic/vocab.py` : `POLARITY=["increases","decreases","neutral"]`, `AUGURA_DOMAINS`, `QUALIFIER_TYPES`, `QUALIFIER_EFFECTS`, `STANDARD_CODE_VOCABULARIES`, `RELATION_STRENGTH`, `CAUSAL_PREDICATES` (miroir de la table). Importé par l'enrichissement **et** le causal → source unique, fin du drift.

**Fix polarity.** `modules/causal/prompt.py` (et `schemas.py`/`builder.py` si l'enum y est dupliqué) consomment `vocab.POLARITY`. Contrat modifié → **régénération du client api** (drift-check CI).

**Logique pure.** `modules/semantic/enrichment.py`, sans I/O (testable à LLM mocké) :
- `match_tokens`, `directed_bfs`, `analyze_coverage` (port de la coverage analysis : concepts manquants + path gaps).
- helpers de proposition : `group_missing_concepts`, `apply_prechecks` (reject self-loop/dup/orphan/predicate inconnu/L1-sans-code ; auto-stub evidence), `reassign_ids`, `stamp_rows`, `merge_into`.
- Le schéma d'outil LLM `PROPOSAL_SCHEMA` (Pydantic) dérive de `vocab.py`.

**Job.** Nouveau kind `"enrich_propose"` + `handle_enrich_propose(ctx)` dans `jobs/handlers.py` :
- lit le bundle sémantique (concepts, synonyms, relations, predicates),
- exécute les batchs (Batch 1 concepts manquants, Batch 2 path gaps, Batch 3 bootstrap des nouveaux concepts ; + raccourci `selected_concepts`) via `core/llm/runtime.run_structured_agent`,
- `set_progress()` à chaque étape (setup/coverage/propose/precheck) — c'est le « log live » porté,
- persiste le batch de propositions (concepts/relations/evidence/qualifiers + `coverage_summary` + `precheck_log`) en **artifact JSON** (`core/storage.py`) ; renvoie le `result_ref`.

**Route.** `POST /semantic/enrich/propose` (body : `{questions[]}` ou `{selected_concepts[]}`) → `create_job("enrich_propose", params)` + `enqueue_job` → renvoie `job_id`. Le front poll `GET /jobs/{id}` ; au succès, récupère l'artifact de propositions.

### Phase 3 — Frontend

- Port de `LearnFromQuestionPanel.jsx` → composant de revue monté dans `SemanticLayerPage` : déclenche le job propose, affiche la progression (polling du job), liste concepts/relations proposés avec sélection (cases à cocher + cascade), POST `apply`. **Aucun mock/fallback** (tout vient du backend réel).
- `CausalModelingPage` : bouton « accepter » sur les arêtes `proposed_*` → `apply` via `direct_relations`, puis `resetSemanticStore()` (déjà défini, jamais câblé) + re-fetch du bundle.

## 5. Tests

- **Unitaires** (pytest, LLM mocké) — `enrichment.py` : coverage, `directed_bfs`, pre-checks (chaque rejet), dedup, reassign IDs, auto-stub evidence. Cœur logique, fort ROI.
- **Intégration** (`@pytest.mark.integration`, exige `AUGURA_DATABASE_URL`) — `upsert_semantic_release` : insert + conflict update + bascule `is_current` ; isolation RLS (le rôle app écrit *via* la fonction, pas en direct).
- **Apply** — gating `owner` (403 sinon) ; chemins `direct_relations` / `deactivate_relation` / `add_qualifier`.
- **Job** — `handle_enrich_propose` à LLM mocké : produit un batch cohérent, `set_progress` appelé, artifact écrit.

## 6. Contrats & CI

`ruff format --check` + `ruff check` + `pyright` (strict) + `lint-imports` (causal→semantic OK) + `pytest`. **Régénération** `apps/api/scripts/dump_openapi.py` → `openapi.json` puis `npm --prefix packages/api-client run generate` (nouvelles routes + enum polarity). Migration **idempotente** + application DB live via MCP Supabase. Front : `npm run lint` + `npm run build`.

## 7. Hors périmètre (YAGNI)

- Overlay/enrichissement par tenant (décision : ontologie globale).
- Streaming SSE (décision : job + polling).
- Table dédiée de propositions (décision : artifact JSON).
- UI de gestion des releases/rollback (la table existe, le `GET /semantic/release` aussi ; pas de nouvelle UI de versioning ici).
- Réécriture des raffinements DAG non liés à l'enrichissement présents dans `98c1023` (on ne porte que ce qui sert l'enrichissement + le fix polarity).

## 8. Risques / points d'attention

- **`upsert_semantic_release` doit cibler `public`** (l'original vise `semantic.*`) et matcher exactement les colonnes plateforme — divergence de schéma = bug silencieux. Vérifier colonne par colonne contre `schema.sql`.
- **Écriture sous RLS** : valider que `SECURITY DEFINER` + `grant execute` au rôle `augura_api` suffit (le rôle est non-BYPASSRLS, RLS `FOR SELECT` seulement).
- **Changement d'enum polarity** : casse potentielle de données DAG existantes typées `mixed`/`unknown` — vérifier qu'aucune donnée live ne dépend de ces valeurs avant bascule.
- **Apply après deploy** : la fonction SQL doit être appliquée à la DB live séparément (Modal ne migre pas).
