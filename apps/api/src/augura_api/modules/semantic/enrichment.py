"""
Logique pure d'enrichissement sémantique (sans I/O, sans LLM, sans DB).

Port fidèle de :
  - lucis-dashboard/api/enrich-propose.js  (buildSemanticData, matchTokens,
    directedBFS, analyzeCoverage, groupMissingConcepts, applyPreChecks,
    reassignIds, stampRows, mergeInto)
  - lucis-dashboard/src/semantic/lexical-normalizer.js  (normalize)

Les seuils numériques et les conditions de branchement sont reproduits à
l'identique depuis la source JS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# ── Constante globale ──────────────────────────────────────────────────────────

HOP_LIMIT = 3

# ── Normalisation lexicale ─────────────────────────────────────────────────────
# Port de lexical-normalizer.js → fonction `normalize`.
#
# Étapes (identiques au JS) :
#   1. Minuscules
#   2. Suppression des artefacts d'encodage ".."
#   3. Suppression des suffixes de timepoint (.BL, .3M, .6M, …)
#   4. Remplacement des séparateurs (_, . : - / \ |) par des espaces
#   5. Suppression des caractères non-alphanumériques (hors espace)
#   6. Tokenisation
#   7. Expansion des abréviations médicales connues
#   8. Suppression des tokens purement numériques et des tokens bruit
#   9. Jointure + trim

# Carte d'expansion des abréviations (port exact du JS)
_ABBREV_MAP: dict[str, str] = {
    # Mesures cliniques
    "hba1c": "hemoglobin a1c",
    "a1c": "hemoglobin a1c",
    "hgba1c": "hemoglobin a1c",
    "sbp": "systolic blood pressure",
    "dbp": "diastolic blood pressure",
    "tir": "time in range",
    "tbr": "time below range",
    "tar": "time above range",
    "bmi": "body mass index",
    "spo2": "oxygen saturation",
    "ahi": "apnea hypopnea index",
    "fev1": "forced expiratory volume",
    "fvc": "forced vital capacity",
    "ktv": "dialysis adequacy",
    "lvef": "ejection fraction",
    "egfr": "estimated glomerular filtration rate",
    "scr": "serum creatinine",
    "pth": "parathyroid hormone",
    "ldl": "low density lipoprotein",
    "hdl": "high density lipoprotein",
    "tg": "triglycerides",
    "vo2max": "maximal oxygen uptake",
    "mets": "metabolic equivalents",
    "ewl": "excess weight loss",
    "twl": "total weight loss",
    "koos": "knee outcome score",
    "acq": "asthma control questionnaire",
    "qlq": "quality of life questionnaire",
    "ctcae": "toxicity grade",
    "vas": "pain analog scale",
    "nrs": "pain rating scale",
    # Dispositifs / procédures
    "tka": "total knee arthroplasty",
    "tkr": "total knee replacement",
    "rygb": "gastric bypass",
    "vsg": "sleeve gastrectomy",
    # Conditions
    "af": "atrial fibrillation",
    "afib": "atrial fibrillation",
    "hf": "heart failure",
    "chf": "heart failure",
    "osa": "sleep apnea",
    "cpap": "positive airway pressure",
    "esrd": "end stage renal disease",
    "copd": "chronic obstructive pulmonary disease",
    "t1d": "type 1 diabetes",
    "t2d": "type 2 diabetes",
    "t1dm": "type 1 diabetes",
    "t2dm": "type 2 diabetes",
    "dm": "diabetes",
    "icm": "cardiac monitor",
    # NOTE: "cgm" intentionnellement NON expansé (idem JS)
    "hcl": "closed loop",
    "mdi": "daily injection",
    "ics": "inhaled corticosteroid",
    "acei": "ace inhibitor",
    "arb": "angiotensin blocker",
    "scs": "spinal cord stimulator",
    "npwt": "negative pressure wound",
    "dr": "diabetic retinopathy",
    "qol": "quality of life",
    "pro": "patient reported outcome",
    "rpm": "remote monitoring",
    # Formes courtes communes
    "bl": "baseline",
    "pt": "patient",
    "wt": "weight",
    "ht": "height",
    "dx": "diagnosis",
    "rx": "medication",
    "pct": "percent",
    "mgdl": "mg dl",
    "mmol": "millimol",
    "gdl": "g dl",
    "pgml": "pg ml",
    "kgm2": "kg m2",
}

# Tokens bruit à supprimer (port exact du JS)
_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "value",
        "values",
        "score",
        "scores",
        "result",
        "results",
        "data",
        "var",
        "variable",
        "col",
        "column",
        "field",
        "entry",
        "item",
        "measure",
        "measurement",
        "level",
        "reading",
        "status",
        "flag",
        "indicator",
        "code",
        "cd",
        "id",
        "num",
        "no",
        "n",
        "the",
        "a",
        "an",
        "of",
        "in",
        "at",
        "on",
        "for",
        "and",
        "or",
        "with",
        "per",
    }
)

# Pattern des suffixes de timepoint (port du regex JS)
_TIMEPOINT_RE = re.compile(
    r"\.(bl|baseline|3m|6m|12m|24m|36m|w0|w2|w4|w8|w12|pre|post|fu)\b",
    re.IGNORECASE,
)
# Séparateurs → espace
_SEPARATOR_RE = re.compile(r"[_.:\-\/\\|]")
# Caractères non-alphanumériques hors espace
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")
# Token purement numérique
_DIGITS_RE = re.compile(r"^\d+$")


def normalize(text: str | None) -> str:
    """Normalise un texte brut pour la correspondance lexicale.

    Port exact de ``lexical-normalizer.js → normalize()``.
    Retourne une chaîne vide si l'entrée est None ou chaîne vide.
    """
    if not text:
        return ""

    s = text.lower()

    # Suppression des artefacts d'encodage (..)
    s = s.replace("..", " ")

    # Suppression des suffixes de timepoint
    s = _TIMEPOINT_RE.sub("", s)

    # Remplacement des séparateurs par des espaces
    s = _SEPARATOR_RE.sub(" ", s)

    # Suppression des caractères non-sémantiques
    s = _NON_ALNUM_RE.sub("", s)

    # Tokenisation
    tokens: list[str] = [t for t in s.split() if t]

    # Expansion des abréviations
    expanded: list[str] = []
    for tok in tokens:
        if tok in _ABBREV_MAP:
            expanded.extend(_ABBREV_MAP[tok].split())
        else:
            expanded.append(tok)

    # Suppression des tokens numériques et des tokens bruit
    filtered = [
        tok for tok in expanded if tok and tok not in _NOISE_TOKENS and not _DIGITS_RE.match(tok)
    ]

    return " ".join(filtered).strip()


# ── Structures de données ──────────────────────────────────────────────────────


@dataclass
class _Ontology:
    """Index en mémoire de l'ontologie causale."""

    relations: list[dict[str, Any]]
    by_subject: dict[str, list[dict[str, Any]]]
    by_object: dict[str, list[dict[str, Any]]]
    predicates: dict[str, dict[str, Any]]


@dataclass
class SemanticIndex:
    """Résultat de ``build_semantic_data`` : index complet pour l'analyse."""

    concept_index: list[dict[str, Any]]
    syn_lookup: dict[str, list[str]]
    ontology: _Ontology


@dataclass
class BfsResult:
    """Résultat d'un parcours BFS directionnel."""

    found: bool
    nearest_forward_hop: dict[str, Any] | None = None


# ── Construction des index ─────────────────────────────────────────────────────


def _parse_boolean(v: Any) -> bool:
    """Convertit une valeur potentiellement sérialisée en booléen.

    Reproduit le comportement JS : ``v === true || v === 'true' || v === 1``.
    """
    return v is True or v == "true" or v == 1


def build_semantic_data(raw_data: dict[str, Any]) -> SemanticIndex:
    """Construit les index sémantiques en mémoire depuis les données brutes.

    Port de ``buildSemanticData()`` dans enrich-propose.js.

    Args:
        raw_data: dict avec clés ``taxonomy_concepts``, ``taxonomy_synonyms``,
            ``ontology_relations``, ``causal_predicates`` (chacune liste ou
            liste vide par défaut).

    Returns:
        :class:`SemanticIndex` avec concept_index, syn_lookup, ontology.
    """
    taxonomy_concepts: list[dict[str, Any]] = raw_data.get("taxonomy_concepts", [])
    taxonomy_synonyms: list[dict[str, Any]] = raw_data.get("taxonomy_synonyms", [])
    ontology_relations: list[dict[str, Any]] = raw_data.get("ontology_relations", [])
    causal_predicates: list[dict[str, Any]] = raw_data.get("causal_predicates", [])

    # Regroupement des synonymes par concept
    synonyms_by_concept_id: dict[str, list[str]] = {}
    for s in taxonomy_synonyms:
        if not s.get("synonym"):
            continue
        cid: str = s["local_concept_id"]
        synonyms_by_concept_id.setdefault(cid, []).append(s["synonym"])

    # Construction du concept index (uniquement les concepts actifs)
    concept_index: list[dict[str, Any]] = []
    for row in taxonomy_concepts:
        if not _parse_boolean(row.get("active")):
            continue
        cid = row["local_concept_id"]
        syns: list[str] = synonyms_by_concept_id.get(cid, [])
        concept_index.append(
            {
                "id": cid,
                "label": row["concept_name"],
                "domain": row.get("augura_domain"),
                "layer": int(row.get("layer", 2)),
                "_norm_label": normalize(row["concept_name"]),
                "_norm_synonyms": [normalize(s) for s in syns],
                "synonyms": syns,
            }
        )

    # Construction du syn_lookup : texte normalisé → liste de concept IDs
    syn_lookup: dict[str, list[str]] = {}

    def _add_to_lookup(norm_text: str, concept_id: str) -> None:
        if not norm_text:
            return
        ids = syn_lookup.setdefault(norm_text, [])
        if concept_id not in ids:
            ids.append(concept_id)

    for concept in concept_index:
        _add_to_lookup(concept["_norm_label"], concept["id"])
        for norm_syn in concept["_norm_synonyms"]:
            _add_to_lookup(norm_syn, concept["id"])

    # Construction de l'ontologie avec maps directionnelles
    active_relations = [r for r in ontology_relations if _parse_boolean(r.get("active"))]
    by_subject: dict[str, list[dict[str, Any]]] = {}
    by_object: dict[str, list[dict[str, Any]]] = {}
    for rel in active_relations:
        sid: str = rel["subject_concept_id"]
        oid: str = rel["object_concept_id"]
        by_subject.setdefault(sid, []).append(rel)
        by_object.setdefault(oid, []).append(rel)

    predicates: dict[str, dict[str, Any]] = {p["predicate_id"]: p for p in causal_predicates}

    return SemanticIndex(
        concept_index=concept_index,
        syn_lookup=syn_lookup,
        ontology=_Ontology(
            relations=active_relations,
            by_subject=by_subject,
            by_object=by_object,
            predicates=predicates,
        ),
    )


# ── Analyse de couverture (Phase 2) ───────────────────────────────────────────


def match_tokens(
    phrases: list[str],
    syn_lookup: dict[str, list[str]],
    concept_index: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], set[str]]:
    """Associe des phrases PICOT à des concepts du taxonomy.

    Port de ``matchTokens()`` dans enrich-propose.js.

    Règles (fidèles au JS) :
    - Correspondance exacte via syn_lookup → priorité absolue.
    - Sinon, parcours du concept_index :
      - Le label normalisé du concept doit être contenu dans la phrase normalisée
        ET faire au moins 4 caractères.
      - Si le label ne passe pas, on teste les synonymes normalisés (même
        contrainte de longueur ≥ 4).
      - La règle de couverture de mots : on accepte si la phrase est courte
        (≤ 3 mots) OU si le ratio mots_label / mots_phrase ≥ 0.5.

    Returns:
        Tuple (matched, unmatched) où matched est un dict phrase→liste_concept_ids
        et unmatched est un set des phrases sans correspondance.
    """
    matched: dict[str, list[str]] = {}
    unmatched: set[str] = set()

    for phrase in phrases:
        if not phrase:
            continue
        norm_phrase = normalize(phrase)
        if not norm_phrase:
            continue

        # Correspondance exacte via le syn_lookup — confiance maximale
        if norm_phrase in syn_lookup:
            matched[phrase] = list(syn_lookup[norm_phrase])
            continue

        phrase_words = len([w for w in norm_phrase.split() if w])

        found: list[str] = []
        for c in concept_index:
            norm_label: str = c["_norm_label"]

            # Vérification via le label normalisé (port exact du JS) :
            # le label doit être contenu dans la phrase ET faire ≥ 4 chars.
            if norm_label and len(norm_label) >= 4 and norm_label in norm_phrase:
                label_words = len([w for w in norm_label.split() if w])
                if phrase_words <= 3 or label_words / phrase_words >= 0.5:
                    found.append(c["id"])
                    continue  # label match → on passe au concept suivant

            # Sinon, vérification via les synonymes normalisés
            for syn in c["_norm_synonyms"]:
                if not syn or len(syn) < 4 or syn not in norm_phrase:
                    continue
                syn_words = len([w for w in syn.split() if w])
                # Accepté si phrase courte (≤3 mots) ou synonyme couvre ≥50% des mots
                if phrase_words <= 3 or syn_words / phrase_words >= 0.5:
                    found.append(c["id"])
                    break

        if found:
            # Déduplication (comme JS : [...new Set(found)])
            seen: set[str] = set()
            deduped = [x for x in found if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]
            matched[phrase] = deduped
        else:
            unmatched.add(phrase)

    return matched, unmatched


def directed_bfs(
    ontology: _Ontology,
    from_ids: list[str],
    to_ids: list[str],
    max_hops: int = HOP_LIMIT,
) -> BfsResult:
    """Parcours en largeur directionnel dans l'ontologie causale.

    Port de ``directedBFS()`` dans enrich-propose.js.

    Retourne :class:`BfsResult` avec ``found=True`` si un chemin direct existe,
    sinon ``found=False`` avec éventuellement ``nearest_forward_hop`` indiquant
    le concept le plus proche des cibles vu depuis la frontière visitée.
    """
    to_set: set[str] = set(to_ids)
    visited: set[str] = set(from_ids)
    frontier: set[str] = set(from_ids)

    for _hop in range(1, max_hops + 1):
        next_frontier: set[str] = set()
        for node_id in frontier:
            for rel in ontology.by_subject.get(node_id, []):
                target: str = rel["object_concept_id"]
                if target in to_set:
                    return BfsResult(found=True, nearest_forward_hop=None)
                if target not in visited:
                    next_frontier.add(target)
                    visited.add(target)
        if not next_frontier:
            break
        frontier = next_frontier

    # Recherche du voisin le plus proche des cibles parmi les nœuds visités
    target_neighbors: set[str] = set()
    for tid in to_ids:
        for rel in ontology.by_object.get(tid, []):
            target_neighbors.add(rel["subject_concept_id"])

    visited_list = list(visited)
    for vid in visited_list:
        if vid in target_neighbors:
            hop_index = visited_list.index(vid) + 1
            return BfsResult(
                found=False,
                nearest_forward_hop={
                    "concept_id": vid,
                    "hops_from_intervention": hop_index,
                },
            )

    return BfsResult(found=False, nearest_forward_hop=None)


def analyze_coverage(
    questions: list[dict[str, Any]],
    concept_index: list[dict[str, Any]],
    syn_lookup: dict[str, list[str]],
    ontology: _Ontology,
) -> dict[str, Any]:
    """Analyse la couverture de l'ontologie vis-à-vis des questions PICOT.

    Port de ``analyzeCoverage()`` dans enrich-propose.js.

    Returns:
        dict avec clés ``summary``, ``missing_concepts``, ``path_gaps``.
    """
    missing_concept_map: dict[str, dict[str, Any]] = {}
    path_gaps: list[dict[str, Any]] = []
    total_pairs = 0
    covered_forward = 0
    covered_backward = 0

    for q in questions:
        picot: dict[str, Any] = q.get("picot") or {}
        iv_phrases: list[str] = list(picot.get("intervention") or []) + list(
            picot.get("comparator") or []
        )
        out_phrases: list[str] = list(picot.get("outcome") or [])

        iv_matched, iv_unmatched = match_tokens(iv_phrases, syn_lookup, concept_index)
        out_matched, out_unmatched = match_tokens(out_phrases, syn_lookup, concept_index)

        for token in iv_unmatched:
            key = normalize(token)
            if key not in missing_concept_map:
                missing_concept_map[key] = {
                    "token": token,
                    "appeared_in": [],
                    "picot_field": "intervention_or_comparator",
                    "suggested_layer": 2,
                    "suggested_domain": "therapeutics",
                }
            missing_concept_map[key]["appeared_in"].append(q["id"])

        for token in out_unmatched:
            key = normalize(token)
            if key not in missing_concept_map:
                missing_concept_map[key] = {
                    "token": token,
                    "appeared_in": [],
                    "picot_field": "outcome",
                    "suggested_layer": 2,
                    "suggested_domain": "measurement",
                }
            missing_concept_map[key]["appeared_in"].append(q["id"])

        # Aplatissement et déduplication des concept IDs matchés
        iv_concept_ids: list[str] = list(
            dict.fromkeys(cid for ids in iv_matched.values() for cid in ids)
        )
        out_concept_ids: list[str] = list(
            dict.fromkeys(cid for ids in out_matched.values() for cid in ids)
        )

        if not iv_concept_ids or not out_concept_ids:
            continue

        total_pairs += 1
        fwd = directed_bfs(ontology, iv_concept_ids, out_concept_ids, HOP_LIMIT)
        bwd = directed_bfs(ontology, out_concept_ids, iv_concept_ids, HOP_LIMIT)

        if fwd.found:
            covered_forward += 1
        if bwd.found:
            covered_backward += 1

        if not fwd.found and not bwd.found:
            iv_slice = iv_concept_ids[:3]
            out_slice = out_concept_ids[:3]
            concept_by_id = {c["id"]: c for c in concept_index}
            path_gaps.append(
                {
                    "question_id": q["id"],
                    "therapeutic_area": q.get("therapeutic_area") or "general",
                    "intervention_concept_ids": iv_slice,
                    "outcome_concept_ids": out_slice,
                    "intervention_labels": [
                        concept_by_id.get(cid, {}).get("label", cid) for cid in iv_slice
                    ],
                    "outcome_labels": [
                        concept_by_id.get(cid, {}).get("label", cid) for cid in out_slice
                    ],
                    "forward_path_found": False,
                    "backward_path_found": False,
                    "nearest_forward_hop": fwd.nearest_forward_hop,
                }
            )

    pairs_covered_pct = (
        round(max(covered_forward, covered_backward) / total_pairs * 100) if total_pairs > 0 else 0
    )

    return {
        "summary": {
            "picot_questions_total": len(questions),
            "picot_pairs_total": total_pairs,
            "pairs_with_forward_path": covered_forward,
            "pairs_with_backward_path": covered_backward,
            "pairs_covered_pct": pairs_covered_pct,
            "missing_concept_tokens": len(missing_concept_map),
        },
        "missing_concepts": list(missing_concept_map.values()),
        "path_gaps": path_gaps,
    }


# ── Groupement des concepts manquants ─────────────────────────────────────────


def group_missing_concepts(
    missing: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Regroupe les tokens manquants par similarité lexicale.

    Port de ``groupMissingConcepts()`` dans enrich-propose.js.
    Seuil de Jaccard sur les mots : > 0.4 (identique au JS).
    """
    groups: list[list[dict[str, Any]]] = []
    assigned: set[int] = set()

    for i in range(len(missing)):
        if i in assigned:
            continue
        group: list[dict[str, Any]] = [missing[i]]
        assigned.add(i)
        tok_a: set[str] = set(missing[i]["token"].lower().split())
        for j in range(i + 1, len(missing)):
            if j in assigned:
                continue
            tok_b: set[str] = set(missing[j]["token"].lower().split())
            inter = len(tok_a & tok_b)
            union = len(tok_a | tok_b)
            if union > 0 and inter / union > 0.4:
                group.append(missing[j])
                assigned.add(j)
        groups.append(group)

    return groups


# ── Helpers de consolidation des proposals ────────────────────────────────────


def make_id(prefix: str, counter: int, today: str) -> str:
    """Génère un identifiant structuré type ``ENRC_20260619_001``.

    Port de ``makeId()`` dans scripts/lib/bootstrap.mjs.
    Le paramètre ``today`` est au format YYYYMMDD (déjà calculé par l'appelant).
    """
    return f"{prefix}_{today}_{str(counter).zfill(3)}"


def reassign_ids(
    batch: dict[str, Any],
    counters: dict[str, int],
    today: str,
) -> None:
    """Réassigne des identifiants séquentiels aux entités du batch.

    Port de ``reassignIds()`` dans enrich-propose.js (mutation in-place).
    ``today`` doit être au format YYYYMMDD (e.g. ``"20260619"``).
    """
    concept_id_map: dict[str, str] = {}
    relation_id_map: dict[str, str] = {}

    for c in batch.get("taxonomy_concepts", []):
        old_id: str = c["local_concept_id"]
        counters["concept"] += 1
        c["local_concept_id"] = make_id("ENRC", counters["concept"], today)
        concept_id_map[old_id] = c["local_concept_id"]

    for s in batch.get("taxonomy_synonyms", []):
        if s.get("local_concept_id") in concept_id_map:
            s["local_concept_id"] = concept_id_map[s["local_concept_id"]]

    for s in batch.get("taxonomy_standard_codes", []):
        if s.get("local_concept_id") in concept_id_map:
            s["local_concept_id"] = concept_id_map[s["local_concept_id"]]

    for r in batch.get("ontology_relations", []):
        old_id = r["relation_id"]
        counters["relation"] += 1
        r["relation_id"] = make_id("ENRR", counters["relation"], today)
        relation_id_map[old_id] = r["relation_id"]
        if r.get("subject_concept_id") in concept_id_map:
            r["subject_concept_id"] = concept_id_map[r["subject_concept_id"]]
        if r.get("object_concept_id") in concept_id_map:
            r["object_concept_id"] = concept_id_map[r["object_concept_id"]]

    for e in batch.get("ontology_relation_evidence", []):
        counters["evidence"] += 1
        e["evidence_id"] = make_id("ENRV", counters["evidence"], today)
        if e.get("relation_id") in relation_id_map:
            e["relation_id"] = relation_id_map[e["relation_id"]]

    for q in batch.get("ontology_relation_qualifiers", []):
        counters["qualifier"] += 1
        q["qualifier_id"] = make_id("ENRQ", counters["qualifier"], today)
        if q.get("relation_id") in relation_id_map:
            q["relation_id"] = relation_id_map[q["relation_id"]]


def merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Fusionne les listes de ``source`` dans ``target`` (mutation in-place).

    Port de ``mergeInto()`` dans enrich-propose.js.
    """
    for key in target:
        if isinstance(source.get(key), list):
            target[key].extend(source[key])


def stamp_rows(proposals: dict[str, Any], version: str) -> None:
    """Ajoute les métadonnées de revue sur toutes les entités du batch.

    Port de ``stampRows()`` dans enrich-propose.js (mutation in-place).
    """

    def _stamp(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "review_status": "pending_review", "active": False, "version": version}

    def _stamp_simple(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "review_status": "pending_review"}

    proposals["taxonomy_concepts"] = [_stamp(r) for r in proposals.get("taxonomy_concepts", [])]
    proposals["ontology_relations"] = [_stamp(r) for r in proposals.get("ontology_relations", [])]
    proposals["taxonomy_synonyms"] = [
        _stamp_simple(r) for r in proposals.get("taxonomy_synonyms", [])
    ]
    proposals["taxonomy_standard_codes"] = [
        _stamp_simple(r) for r in proposals.get("taxonomy_standard_codes", [])
    ]
    proposals["ontology_relation_evidence"] = [
        _stamp_simple(r) for r in proposals.get("ontology_relation_evidence", [])
    ]
    proposals["ontology_relation_qualifiers"] = [
        _stamp_simple(r) for r in proposals.get("ontology_relation_qualifiers", [])
    ]


# ── Pré-vérifications (pre-checks) ────────────────────────────────────────────


def apply_prechecks(
    batch: dict[str, Any],
    *,
    existing_concept_ids: set[str],
    existing_relation_keys: set[str],
    valid_predicate_ids: set[str],
    log: list[str],
    id_counters: dict[str, int],
    today: str | None = None,
) -> list[dict[str, Any]]:
    """Applique les règles de validation et de dédoublonnage sur un batch.

    Port de ``applyPreChecks()`` dans enrich-propose.js.

    Règles de rejet (fidèles au JS) :
    - Self-loop : subject == object
    - Doublon de relation : clé ``subject|predicate|object|polarity`` déjà vue
    - Sujet orphelin : subject_concept_id inconnu du batch + existants
    - Objet orphelin : idem pour object
    - Prédicat inconnu : predicate non dans valid_predicate_ids
    - Concept L1 sans code standard

    Effets secondaires :
    - Détection et retour des conflits de polarité opposée
    - Auto-stub d'evidence pour les relations sans evidence

    Args:
        today: date au format YYYYMMDD pour les IDs auto-stubs. Si None,
            utilise la date du jour.

    Returns:
        Liste des conflits de polarité détectés (chaque élément contient
        ``proposed`` et ``opposite_key``).
    """
    _today = today or date.today().strftime("%Y%m%d")

    # Ensemble de tous les concept IDs connus à l'entrée du batch
    batch_concept_ids: set[str] = existing_concept_ids | {
        c["local_concept_id"] for c in batch.get("taxonomy_concepts", [])
    }
    batch_relation_keys: set[str] = set(existing_relation_keys)
    conflicts: list[dict[str, Any]] = []

    # ── Filtrage des relations ─────────────────────────────────────────────────
    kept_relations: list[dict[str, Any]] = []
    for rel in batch.get("ontology_relations", []):
        subj: str = rel.get("subject_concept_id", "")
        obj: str = rel.get("object_concept_id", "")
        pred: str = rel.get("predicate", "")
        pol: str = rel.get("polarity", "")

        # Self-loop
        if subj == obj:
            log.append(f"  REJECT self-loop: {rel.get('relation_id')} ({subj})")
            continue

        # Doublon par clé composite
        key = f"{subj}|{pred}|{obj}|{pol}"
        if key in batch_relation_keys:
            log.append(f"  REJECT duplicate: {rel.get('relation_id')} ({key})")
            continue

        # Sujet orphelin
        if subj not in batch_concept_ids:
            log.append(f"  REJECT orphan subject: {rel.get('relation_id')} → {subj}")
            continue

        # Objet orphelin
        if obj not in batch_concept_ids:
            log.append(f"  REJECT orphan object: {rel.get('relation_id')} → {obj}")
            continue

        # Prédicat inconnu
        if pred not in valid_predicate_ids:
            log.append(f"  REJECT unknown predicate: {rel.get('relation_id')} → {pred}")
            continue

        # Détection de conflit de polarité opposée
        opposite_polarity: str | None
        if pol == "increases":
            opposite_polarity = "decreases"
        elif pol == "decreases":
            opposite_polarity = "increases"
        else:
            opposite_polarity = None

        if opposite_polarity:
            conflict_key = f"{subj}|{pred}|{obj}|{opposite_polarity}"
            if conflict_key in existing_relation_keys:
                conflicts.append({"proposed": rel, "opposite_key": conflict_key})

        batch_relation_keys.add(key)
        kept_relations.append(rel)

    batch["ontology_relations"] = kept_relations

    # ── Dédoublonnage des concepts ─────────────────────────────────────────────
    seen_concept_ids: set[str] = set(existing_concept_ids)
    kept_concepts: list[dict[str, Any]] = []
    for c in batch.get("taxonomy_concepts", []):
        cid: str = c["local_concept_id"]
        if cid in seen_concept_ids:
            log.append(f"  REJECT duplicate concept: {cid}")
            continue
        seen_concept_ids.add(cid)
        kept_concepts.append(c)
    batch["taxonomy_concepts"] = kept_concepts

    # ── Rejet L1 sans code standard ───────────────────────────────────────────
    batch_code_ids: set[str] = {
        s["local_concept_id"] for s in batch.get("taxonomy_standard_codes", [])
    }
    kept_concepts_final: list[dict[str, Any]] = []
    for c in batch["taxonomy_concepts"]:
        if int(c.get("layer", 2)) == 1 and c["local_concept_id"] not in batch_code_ids:
            log.append(
                f'  REJECT L1-no-code: {c["local_concept_id"]} "{c.get("concept_name")}"'
                " — re-propose as layer=2 or add a code"
            )
            continue
        kept_concepts_final.append(c)
    batch["taxonomy_concepts"] = kept_concepts_final

    # ── Re-filtrage des relations après rejet de concepts ─────────────────────
    # Un concept accepté au filtrage des orphelins peut avoir été rejeté
    # ensuite (doublon, L1-sans-code). On nettoie les relations correspondantes.
    final_concept_ids: set[str] = existing_concept_ids | {
        c["local_concept_id"] for c in batch["taxonomy_concepts"]
    }
    final_relations: list[dict[str, Any]] = []
    for rel in batch["ontology_relations"]:
        if rel.get("subject_concept_id") not in final_concept_ids:
            log.append(
                f"  REJECT relation (concept rejected): {rel.get('relation_id')}"
                f" → subject {rel.get('subject_concept_id')}"
            )
            continue
        if rel.get("object_concept_id") not in final_concept_ids:
            log.append(
                f"  REJECT relation (concept rejected): {rel.get('relation_id')}"
                f" → object {rel.get('object_concept_id')}"
            )
            continue
        final_relations.append(rel)
    batch["ontology_relations"] = final_relations

    final_rel_ids: set[str] = {r["relation_id"] for r in batch["ontology_relations"]}

    # ── Nettoyage des synonymes et codes pour concepts rejetés ────────────────
    accepted_concept_ids: set[str] = {c["local_concept_id"] for c in batch["taxonomy_concepts"]}
    batch["taxonomy_synonyms"] = [
        s
        for s in batch.get("taxonomy_synonyms", [])
        if s.get("local_concept_id") in accepted_concept_ids
        or s.get("local_concept_id") in existing_concept_ids
    ]
    batch["taxonomy_standard_codes"] = [
        s
        for s in batch.get("taxonomy_standard_codes", [])
        if s.get("local_concept_id") in accepted_concept_ids
        or s.get("local_concept_id") in existing_concept_ids
    ]

    # ── Filtrage de l'evidence pour les relations rejetées ────────────────────
    kept_evidence: list[dict[str, Any]] = []
    for e in batch.get("ontology_relation_evidence", []):
        if e.get("relation_id") not in final_rel_ids:
            log.append(f"  DROP evidence for rejected relation: {e.get('evidence_id')}")
            continue
        kept_evidence.append(e)
    batch["ontology_relation_evidence"] = kept_evidence

    # ── Auto-stub d'evidence manquante ────────────────────────────────────────
    existing_evidence_rel_ids: set[str] = {
        e["relation_id"] for e in batch["ontology_relation_evidence"]
    }
    for rel in batch["ontology_relations"]:
        if rel["relation_id"] not in existing_evidence_rel_ids:
            id_counters["evidence"] += 1
            stub_id = make_id("ENRV", id_counters["evidence"], _today)
            batch["ontology_relation_evidence"].append(
                {
                    "evidence_id": stub_id,
                    "relation_id": rel["relation_id"],
                    "source_type": "established_physiology",
                    "citation_or_url": "established physiology",
                    "evidence_summary": rel.get("mechanism_summary")
                    or "Established causal relationship",
                    "population_notes": "General population",
                    "evidence_strength": "established",
                }
            )
            log.append(f"  AUTO-STUB evidence for: {rel['relation_id']}")

    return conflicts
