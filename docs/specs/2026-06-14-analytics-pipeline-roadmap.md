# Augura Analytics Pipeline — plan d'implémentation mappé au code

**Statut :** plan de travail — 2026-06-14. Traduit le draft « Augura Analytics
Pipeline/Roadmap (June 2026) » en chantiers concrets, séquencés, ancrés dans le code
existant (`augura-platform`). Décisions tranchées : **moteur Phase 6 en Python** (pas R),
**plan d'abord** (ce document) avant tout build.

Réfs : spec produit (draft fourni) ; architecture backend
[2026-06-11](2026-06-11-augura-backend-architecture-design.md) ;
livraison [2026-06-13](2026-06-13-delivery-design.md).

---

## 1. North star (les 3 propriétés) — et comment on les tient en Python

La spec impose trois propriétés à **chaque** phase :

- **Fonctionnel** — chaque phase produit un artefact consommable par la suivante + un
  critère d'acceptation concret.
- **Auditable** — chaque transformation / suggestion / décision humaine est loggée
  (user, timestamp, rationale). **C'est LE différenciateur réglementaire.** Construit dès
  le jour 1.
- **Reproductible** — la repro vient d'**artefacts versionnés + hashés**, jamais du
  re-run d'un process stochastique. **Le LLM n'est jamais sur le chemin critique d'une
  décision scientifique** : il rédige, récupère, explique ; ce sont des règles
  déterministes ou des décisions humaines loggées qui tranchent.

> **Pourquoi Python ne casse rien.** La reproductibilité de la spec ne dépend PAS de R :
> elle vient des **artefacts hashés + du run manifest + de l'environnement épinglé**. En
> Python on tient exactement la même garantie via `uv.lock` (dépendances figées) + digest
> de l'image conteneur + seed RNG + manifest. Le choix R/Python est un choix de
> *bibliothèques d'inférence causale*, pas un choix de rigueur. Voir §5 (décision moteur).

---

## 2. La colonne vertébrale : audit/provenance + lock de pré-spécification (transversal, construit EN PREMIER)

C'est le cœur de la spec et ce qui manque le plus aujourd'hui. Tout le reste s'y accroche.

### 2.1 Modèle d'artefact versionné & hashé (nouveau)

Nouvelle table `artifacts` (org-scopée, RLS) — source de vérité de tout objet
reproductible (snapshot dataset, rapport QC, dictionnaire mappé, DAG, SAP, run) :

```
artifacts(
  id uuid pk,
  org_id uuid not null,                      -- RLS tenant
  study_id uuid references studies(id),
  kind text not null,                        -- 'dataset_snapshot'|'qc_report'|'mapping'|'dag'|'sap'|'run_manifest'
  version int not null,                       -- v0 = machine-proposé, v1 = humain-approuvé…
  sha256 text not null,                       -- hash du contenu canonique (JSON trié / texte)
  content jsonb,                              -- corps inline (DAGitty, SAP YAML→json, edge list…)
  storage_ref text,                           -- ou pointeur Supabase Storage si volumineux (CSV brut)
  provenance jsonb not null,                  -- {source:'llm'|'human'|'rule', prompt_hash, model_id, ts, parent_version, diff}
  locked bool not null default false,         -- artefact figé (SAP/DAG approuvé)
  created_by uuid, created_at timestamptz,
  unique(study_id, kind, version)
)
```

- **Hash canonique** : `sha256(canonical_json(content))` — JSON à clés triées, ou texte
  DAGitty normalisé. Déterministe, indépendant du moteur LLM.
- **Lock** : `locked=true` + écriture du hash dans le SAP. Toute édition post-lock crée une
  **nouvelle version** et force un amendement SAP (la garantie de pré-spécification).

### 2.2 Log de provenance (réutilise l'existant)

- `outbox_events` (déjà en base : `aggregate_type/aggregate_id/event_type/payload/created_at`)
  → **event log d'audit**. Chaque transformation/décision émet un event
  (`artifact.created`, `dag.edge.accepted`, `sap.locked`, `qc.fix.rejected`…) avec
  user/ts/rationale dans `payload`. Aujourd'hui la table existe, le gate RLS « session
  backend » est posé ; **il faut juste commencer à écrire dedans**.
- `agent_runs` (déjà en base, inutilisé — cf. `log_agent_run`) → provenance LLM
  (model, tokens, coût, durée). À câbler dans `run_structured_agent`.
- `study_state` (déjà versionné) → reste l'état de workflow ; le **SAP lock** est un
  artefact `kind='sap', locked=true` distinct.

**Acceptation spine :** créer un dataset → un artefact `dataset_snapshot` hashé + un event
`outbox` ; rejouer ⇒ même hash ; tout edit de DAG/SAP loggé avec rationale.

---

## 3. Gap analysis (spec ↔ code actuel)

| Spec | Aujourd'hui | État |
|---|---|---|
| **Audit/provenance** (transversal) | `usage_events`/`outbox_events`/`agent_runs` existent, ~inutilisés ; pas de hash d'artefact | ❌ à construire (§2) |
| **Lock pré-spec (SAP)** | `study_state` versionné, sans hash ni lock | ❌ |
| **P1 Ingestion** | module `datasets`, `ExcelUpload`, champ `storage_path` | 🟡 modèle oui ; upload réel + snapshot/hash + réconciliation lignes/cols non |
| **P2 Cleaning/QC** | `DatasetVerification` + agent `variable-check` (profiling) | 🟡 pas de rapport QC en artefact, pas d'audit accept/reject |
| **P3 Mapping/rôles** | `dataset_columns.proposed_role` + agent variable-check | 🟡 pas de CDM, pas de confiance/answer-key |
| **P4 DAG** | `/agents/dag` (LLM→JSON) + éditeur `CausalModel` | 🟡→❌ aucune rigueur spec (contraintes, dagitty, hash, provenance, adjustment sets) |
| **P5 Estimands/estimateurs** | configs estimateurs `SimulationEngine` | ❌ pas de tables de décision ICH E9(R1), pas de SAP stub |
| **P6 Moteur** | `simulation/run_bootstrap.py` (Python) + `power.py` | 🟡 base Python ; pas de manifest, pas de diagnostics gatés, pas de Quarto/rapport |
| **§3.4 DAG evidence-grounded (PubMed)** | **agent littérature PubMed** (commit 306fbdc) | 🟢 fondation posée ; manque requête par-edge + gel (query_string, retrieval_date) |

---

## 4. Décisions tranchées

1. **Moteur Phase 6 = Python** (cf. §5). Reproductibilité tenue par artefacts hashés +
   manifest + env épinglé, pas par R.
2. **DAG = code, pas dessin.** Canonique = **JSON edge list** (`{from,to,rationale,confidence,citation}`),
   avec export **DAGitty** (texte) pour `dagitty`/R-free validation côté Python.
3. **Artefacts hashés SHA-256**, versionnés, lockables (§2.1).
4. **LLM hors chemin critique** partout : il propose (temp 0, prompt versionné, sortie JSON
   structurée), des **règles déterministes** valident et **l'humain** approuve (loggé).
5. **Candidate edges** (confiance basse) = tâche d'acceptation explicite, jamais auto-acceptée.

---

## 5. Décision moteur : Python (avec garde-fous)

La spec nomme R (`tmle3`/`lmtp`/`WeightIt`/`survival`). On reste Python. Conséquences et
mitigations :

**Reproductibilité (préservée intégralement) :** image conteneur à digest figé,
`uv.lock` (dépendances épinglées), seed RNG, **run manifest** (hash dataset + SAP + DAG +
digest image + seed + version code + user + ts). Identique à la garantie R de la spec.

**Cartographie des estimateurs R → Python :**

| Spec (R) | Équivalent Python | Maturité |
|---|---|---|
| IPTW / IPW | propensity `scikit-learn` + pondération (`statsmodels`) | ✅ solide |
| g-computation | `statsmodels`/`sklearn` (outcome model + standardisation) | ✅ |
| Cox pondéré / MSM | `lifelines` (CoxPHFitter weights) / `statsmodels` PHReg | ✅ |
| Mixed models (clustering) | `statsmodels` MixedLM | ✅ |
| TMLE | `zepid` (TMLE) ou cross-fitting maison | 🟡 moins mature que `tmle3` |
| LMTP (treatment policies longitudinales) | **pas d'équivalent direct** | 🔴 gap réel |
| E-value (sensibilité) | trivial à implémenter | ✅ |
| Diagnostics (positivité/balance/poids) | implémentables | ✅ |

**Trade-off honnête :** on perd l'argument « packages publiés/validés `tmle3`/`lmtp` » face
au FDA, et **LMTP n'a pas d'équivalent Python** (les estimands longitudinaux time-varying
seront limités ou custom en v1). **Mitigation :** (a) tests de caractérisation sur données
simulées à réponse connue (= l'étape 5 « fake-data test » de la spec) ; (b) garder
l'architecture **agnostique au langage** (SAP→code compile, digest conteneur dans le
manifest) pour pouvoir ajouter **un sidecar R** dédié `tmle3`/`lmtp` plus tard si un sponsor
l'exige, sans rien réécrire. Décision : **Python pour v1 ; porte ouverte au sidecar R en
option premium.**

---

## 6. Roadmap séquencée (milestones)

Chaque milestone = artefact + critère d'acceptation (repris de la spec).

**M0 — Spine audit/repro (transversal, prérequis).** Table `artifacts` + helper de
hash canonique + écriture `outbox_events` + câblage `log_agent_run` dans
`run_structured_agent`. *Accept :* créer un dataset/DAG ⇒ artefact hashé + event loggé ;
re-hash identique.

**M1 — Phase 1 ingestion réelle.** Upload → Supabase Storage, snapshot brut **verrouillé**,
détection schéma (noms/types/missingness), **fingerprint du fichier** + réconciliation
lignes/cols vs déclaré, dédup par hash. *Accept :* upload → inventaire de variables < 30 s ;
échec si counts ≠ déclaré ou fichier déjà chargé.

**M2 — Phase 2 cleaning/QC.** Rapport QC déterministe (missingness, outliers, valeurs
impossibles, doublons, unités) en **artefact** ; fixes suggérés accept/reject **one-click,
loggés** ; recette de cleaning idempotente. *Accept :* dataset nettoyé + rapport QC
exportable ; échec si une valeur change sans rationale loggée.

**M3 — Phase 4 DAG à la spec** (priorité haute, le plus différenciant ; détail §7). *Accept :*
DAG validé `dagitty` → adjustment set minimal exporté ; artefact DAGitty hashé/versionné.

**M4 — Phase 3 mapping durci.** Mapping vers CDM slim + rôles, confiance LLM, **answer-key**
hand-checked + métrique d'accord. *Accept :* dataset analysis-ready labellisé ; échec si
colonnes non labellisées ou désaccord answer-key.

**M5 — Phase 5 estimands/estimateurs** (détail §8). Tables de décision versionnées
(ICH E9(R1)) → estimand → estimateur + checklist d'hypothèses → **SAP stub** YAML signable
et lockable. *Accept :* user choisit l'estimand → SAP stub auto-généré.

**M6 — Phase 6 moteur Python + manifest** (détail §9). SAP→script via templates ;
diagnostics **gatés** (positivité/balance/missingness) ; **run manifest** ; rapport
(Quarto-like ; en Python : `quarto` avec noyau jupyter, ou un rapport HTML/PDF maison).
*Accept :* run de bout en bout (upload→estimate) avec audit trail complet ; re-run du
manifest ⇒ nombres identiques.

> Ordre conseillé : **M0 → M3 (DAG) → M5 (estimands) → M6 (moteur)**, en intercalant
> M1/M2/M4 (ingestion/QC/mapping) au fil de l'eau. Rationale : M3+M5+M6 forment la chaîne
> différenciante (DAG hashé → SAP locké → run reproductible) ; M1/M2/M4 durcissent l'amont
> déjà à moitié présent.

---

## 7. Phase 4 — DAG reproductible (design détaillé)

Adapte le §3 de la spec au code (`modules/agents` + `CausalModel.jsx`).

1. **Entrées déterministes** : uniquement le dictionnaire mappé Phase 3 (noms, labels,
   rôles exposure/outcome/covariate/mediator-candidate, timing). Fichier structuré
   versionné — pas de prompt libre.
2. **Couche de contraintes (rule-based, AVANT le LLM)** : pas d'arête temps-postérieur →
   temps-antérieur ; si randomisé, pas d'arête entrante sur l'exposition sauf
   randomisation ; l'outcome n'a pas d'arête sortante. Déterministe + **tests unitaires**.
   → nouveau `modules/agents/dag_constraints.py`.
3. **Proposition LLM sous contrôle repro** : prompt template versionné, modèle épinglé,
   **temp 0**, sortie JSON (1 arête = `{from,to,rationale,confidence,citation}`).
   `prompt_hash`+`model_id`+`ts` dans la provenance de l'artefact. (Le `/agents/dag`
   existant est le point de départ ; on durcit la sortie et on pin.)
4. **Validation formelle** : pipe l'edge list dans une validation type `dagitty` —
   acyclicité, nœuds orphelins, **dérivation de l'adjustment set minimal (backdoor)**,
   colliders/médiateurs à NE PAS ajuster. En Python (pas de R) : implémenter le critère
   backdoor sur le graphe (networkx) ou porter la logique `dagitty`. Échec ⇒ retour étape 3
   avec la violation injectée.
5. **Artefact = source de vérité** : DAGitty (texte) + edge-list JSON, **SHA-256**, v0 =
   machine. Quiconque a le fichier reproduit le DAG et ses adjustment sets, à jamais.
6. **Édition investigateur avec provenance** : éditeur visuel (`CausalModel.jsx`) ;
   add/delete/reverse ⇒ rationale obligatoire + log (user, ts, before/after) ; chaque save =
   nouvelle version ; à l'approbation **lock** + hash écrit dans le SAP.
7. **Candidate edges** (confiance basse) = arêtes pointillées à accepter/rejeter
   explicitement.
8. **§3.4 evidence-grounding (optionnel, premium)** : pour chaque arête, requête PubMed
   templatée via **l'agent littérature déjà construit** (E-utilities) → PMIDs supportant/
   contredisant ; **gel** dans l'artefact (PMID, titre, `query_string`, `retrieval_date`).
   Ship v1 sans ; ajout en « evidence-grounded DAG ».

---

## 8. Phase 5 — Estimands & estimateurs (design détaillé)

Sélection **rule-based**, pas LLM (le LLM ne rédige que la justification en clair).

- **Entrées** : DAG locké v1 (par hash), métadonnées de design (randomisé/observationnel,
  cluster, crossover), dictionnaire (type d'outcome, censure, traitement time-varying).
- **Dérivation d'estimand** : table de décision déterministe design+DAG → estimands cadrés
  ICH E9(R1) (population, contraste, endpoint, stratégie d'intercurrent-event, summary).
  Confounding time-varying détecté dans le DAG ⇒ flag estimands longitudinaux (⚠ LMTP =
  gap Python, cf. §5).
- **Matching estimateur** : 2ᵉ table estimand+data → estimateur (parmi la cartographie
  Python §5) + **checklist d'hypothèses** (positivité, échangeabilité vu l'adjustment set,
  censure) + failure modes connus.
- **Artefact SAP stub** (YAML/JSON) : estimand, adjustment set **hérité du DAG locké**,
  estimateur primaire, analyses de sensibilité pré-spécifiées (E-value, estimateur alt, DAG
  alt sur arêtes incertaines). Revue → édition loggée → signature → **lock + hash**.
- Les **tables de décision sont versionnées** (on sait quelle règle a produit quelle
  suggestion). → nouveau `modules/<estimands>/decision_tables/` (YAML versionnés).

---

## 9. Phase 6 — Moteur d'analyse Python (design détaillé)

- **Env épinglé** : image conteneur (Modal) à digest figé + `uv.lock` (numpy/scipy/
  statsmodels/lifelines/scikit-learn/zepid + report). Le digest fait partie de chaque run.
- **SAP → code** : le SAP YAML compile **déterministement** en script Python via templates ;
  les rôles de variables du mapping remplissent les arguments. **Aucun code d'analyse écrit à
  la main** ⇒ rien à dévier du SAP.
- **Exécution gatée** : avant estimation, diagnostics qui **bloquent** — positivité
  (overlap des propensities), balance des covariables, missingness réconciliée vs rapport
  QC Phase 2. Violation ⇒ override investigateur loggé.
- **Run manifest** (artefact `kind='run_manifest'`) : hash dataset + SAP + DAG + digest
  conteneur + seed RNG + version code + user + ts. *La phrase repro au régulateur.*
- **Sorties** : estimations + IC, plots de diagnostic (balance, positivité, poids), rapport
  auto-généré (Quarto via noyau Python, ou rapport maison) dont la 1ʳᵉ page imprime le
  manifest. Étend `simulation/run_bootstrap.py` (worker Modal, déjà prévu comme follow-up).

---

## 10. Risques & questions ouvertes

- **LMTP / estimands longitudinaux** : pas d'équivalent Python mûr → soit custom, soit hors
  v1, soit sidecar R plus tard. À arbitrer quand un cas client le réclame.
- **TMLE Python** (`zepid`) moins éprouvé que `tmle3` → valider par fake-data tests.
- **Quarto** est R/Python-agnostique mais ajoute une dépendance ; alternative : rapport
  HTML/PDF maison (WeasyPrint, déjà envisagé pour les documents générés).
- **Storage Supabase** (uploads bruts, rapports) pas encore câblé — prérequis M1.
- **Clés LLM** (`ANTHROPIC`/`OPENAI`) requises pour les couches LLM (DAG proposal,
  justifications, embeddings) ; tout le rule-based + repro marche sans.
- **CDM/OMOP** : la spec dit « OMOP plus tard » → v1 = CDM slim maison.

---

## 11. Prochaines étapes immédiates

1. **M0 — spine** : table `artifacts` + migration + helper hash canonique + premiers events
   `outbox` + câblage `log_agent_run`. (Petit, transversal, débloque tout.)
2. **M3 — Phase 4 DAG à la spec** : `dag_constraints.py` (rule-based + tests) → durcir
   `/agents/dag` (temp 0, prompt versionné, JSON+provenance) → validation backdoor
   (networkx) → artefact DAGitty hashé → provenance d'édition dans `CausalModel.jsx`.
3. Réutiliser l'**agent PubMed** pour le §3.4 (evidence-grounded) quand M3 est posé.

> À valider avec Quentin avant de coder M0/M3.
