"""
Pure semantic enrichment logic (no I/O, no LLM, no DB).

Faithful port of:
  - lucis-dashboard/api/enrich-propose.js  (buildSemanticData, matchTokens,
    directedBFS, analyzeCoverage, groupMissingConcepts, applyPreChecks,
    reassignIds, stampRows, mergeInto)
  - lucis-dashboard/src/semantic/lexical-normalizer.js  (normalize)

The numeric thresholds and branching conditions are reproduced identically
from the JS source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# ── Global constant ────────────────────────────────────────────────────────────

HOP_LIMIT = 3

# ── Lexical normalization ──────────────────────────────────────────────────────
# Port of lexical-normalizer.js → `normalize` function.
#
# Steps (identical to the JS):
#   1. Lowercase
#   2. Removal of ".." encoding artifacts
#   3. Removal of timepoint suffixes (.BL, .3M, .6M, …)
#   4. Replacement of separators (_, . : - / \ |) with spaces
#   5. Removal of non-alphanumeric characters (excluding space)
#   6. Tokenization
#   7. Expansion of known medical abbreviations
#   8. Removal of purely numeric tokens and noise tokens
#   9. Join + trim

# Abbreviation expansion map (exact port of the JS)
_ABBREV_MAP: dict[str, str] = {
    # Clinical measurements
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
    # Devices / procedures
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
    # NOTE: "cgm" intentionally NOT expanded (same as JS)
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
    # Common short forms
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

# Noise tokens to remove (exact port of the JS)
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

# Timepoint suffix pattern (port of the JS regex)
_TIMEPOINT_RE = re.compile(
    r"\.(bl|baseline|3m|6m|12m|24m|36m|w0|w2|w4|w8|w12|pre|post|fu)\b",
    re.IGNORECASE,
)
# Separators → space
_SEPARATOR_RE = re.compile(r"[_.:\-\/\\|]")
# Non-alphanumeric characters excluding space
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")
# Purely numeric token
_DIGITS_RE = re.compile(r"^\d+$")


def normalize(text: str | None) -> str:
    """Normalizes raw text for lexical matching.

    Exact port of ``lexical-normalizer.js → normalize()``.
    Returns an empty string if the input is None or an empty string.
    """
    if not text:
        return ""

    s = text.lower()

    # Removal of encoding artifacts (..)
    s = s.replace("..", " ")

    # Removal of timepoint suffixes
    s = _TIMEPOINT_RE.sub("", s)

    # Replacement of separators with spaces
    s = _SEPARATOR_RE.sub(" ", s)

    # Removal of non-semantic characters
    s = _NON_ALNUM_RE.sub("", s)

    # Tokenization
    tokens: list[str] = [t for t in s.split() if t]

    # Abbreviation expansion
    expanded: list[str] = []
    for tok in tokens:
        if tok in _ABBREV_MAP:
            expanded.extend(_ABBREV_MAP[tok].split())
        else:
            expanded.append(tok)

    # Removal of numeric tokens and noise tokens
    filtered = [
        tok for tok in expanded if tok and tok not in _NOISE_TOKENS and not _DIGITS_RE.match(tok)
    ]

    return " ".join(filtered).strip()


# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class _Ontology:
    """In-memory index of the causal ontology."""

    relations: list[dict[str, Any]]
    by_subject: dict[str, list[dict[str, Any]]]
    by_object: dict[str, list[dict[str, Any]]]
    predicates: dict[str, dict[str, Any]]


@dataclass
class SemanticIndex:
    """Result of ``build_semantic_data``: full index for the analysis."""

    concept_index: list[dict[str, Any]]
    syn_lookup: dict[str, list[str]]
    ontology: _Ontology


@dataclass
class BfsResult:
    """Result of a directed BFS traversal."""

    found: bool
    nearest_forward_hop: dict[str, Any] | None = None


# ── Index construction ───────────────────────────────────────────────────────


def _parse_boolean(v: Any) -> bool:
    """Converts a potentially serialized value to a boolean.

    Reproduces the JS behavior: ``v === true || v === 'true' || v === 1``.
    """
    return v is True or v == "true" or v == 1


def build_semantic_data(raw_data: dict[str, Any]) -> SemanticIndex:
    """Builds the in-memory semantic indexes from the raw data.

    Port of ``buildSemanticData()`` in enrich-propose.js.

    Args:
        raw_data: dict with keys ``taxonomy_concepts``, ``taxonomy_synonyms``,
            ``ontology_relations``, ``causal_predicates`` (each a list or an
            empty list by default).

    Returns:
        :class:`SemanticIndex` with concept_index, syn_lookup, ontology.
    """
    taxonomy_concepts: list[dict[str, Any]] = raw_data.get("taxonomy_concepts", [])
    taxonomy_synonyms: list[dict[str, Any]] = raw_data.get("taxonomy_synonyms", [])
    ontology_relations: list[dict[str, Any]] = raw_data.get("ontology_relations", [])
    causal_predicates: list[dict[str, Any]] = raw_data.get("causal_predicates", [])

    # Grouping of synonyms by concept
    synonyms_by_concept_id: dict[str, list[str]] = {}
    for s in taxonomy_synonyms:
        if not s.get("synonym"):
            continue
        cid: str = s["local_concept_id"]
        synonyms_by_concept_id.setdefault(cid, []).append(s["synonym"])

    # Building the concept index (active concepts only)
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

    # Building the syn_lookup: normalized text → list of concept IDs
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

    # Building the ontology with directional maps
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


# ── Coverage analysis (Phase 2) ────────────────────────────────────────────────


def match_tokens(
    phrases: list[str],
    syn_lookup: dict[str, list[str]],
    concept_index: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], set[str]]:
    """Maps PICOT phrases to taxonomy concepts.

    Port of ``matchTokens()`` in enrich-propose.js.

    Rules (faithful to the JS):
    - Exact match via syn_lookup → highest priority.
    - Otherwise, scan of the concept_index:
      - The normalized concept label must be contained in the normalized phrase
        AND be at least 4 characters long.
      - If the label does not pass, the normalized synonyms are tested (same
        length constraint ≥ 4).
      - The word-coverage rule: accepted if the phrase is short
        (≤ 3 words) OR if the ratio label_words / phrase_words ≥ 0.5.

    Returns:
        Tuple (matched, unmatched) where matched is a dict phrase→list_of_concept_ids
        and unmatched is a set of phrases without a match.
    """
    matched: dict[str, list[str]] = {}
    unmatched: set[str] = set()

    for phrase in phrases:
        if not phrase:
            continue
        norm_phrase = normalize(phrase)
        if not norm_phrase:
            continue

        # Exact match via the syn_lookup — maximum confidence
        if norm_phrase in syn_lookup:
            matched[phrase] = list(syn_lookup[norm_phrase])
            continue

        phrase_words = len([w for w in norm_phrase.split() if w])

        found: list[str] = []
        for c in concept_index:
            norm_label: str = c["_norm_label"]

            # Exact port of the JS if/else (enrich-propose.js ~lines 233-253):
            #   if (!normPhrase.includes(c._normLabel) || c._normLabel.length < 4)
            #     → try the synonyms
            #   else
            #     → the label is present AND ≥ 4 chars: label-coverage check
            #       ONLY, the synonyms are NEVER tried.
            if norm_phrase and (norm_label not in norm_phrase or len(norm_label) < 4):
                # Label absent or too short → try the normalized synonyms
                for syn in c["_norm_synonyms"]:
                    if not syn or len(syn) < 4 or syn not in norm_phrase:
                        continue
                    syn_words = len([w for w in syn.split() if w])
                    # Accepted if phrase is short (≤3 words) or synonym covers ≥50% of words
                    if phrase_words <= 3 or syn_words / phrase_words >= 0.5:
                        found.append(c["id"])
                        break
            else:
                # Label present AND ≥ 4 chars → coverage check only
                # (the synonyms are NEVER tried in this branch)
                label_words = len([w for w in norm_label.split() if w])
                if phrase_words <= 3 or label_words / phrase_words >= 0.5:
                    found.append(c["id"])

        if found:
            # Deduplication (like JS: [...new Set(found)])
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
    """Directed breadth-first traversal of the causal ontology.

    Port of ``directedBFS()`` in enrich-propose.js.

    Returns :class:`BfsResult` with ``found=True`` if a direct path exists,
    otherwise ``found=False`` with an optional ``nearest_forward_hop`` indicating
    the concept closest to the targets seen from the visited frontier.
    """
    to_set: set[str] = set(to_ids)
    # visited is an insertion-ordered dict[str, None] to reproduce the
    # JS behavior which uses an ES6 Set (insertion-ordered).
    # list(visited) thus reflects the insertion order, like [...visited] in JS,
    # which makes hops_from_intervention deterministic.
    visited: dict[str, None] = {nid: None for nid in from_ids}
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
                    visited[target] = None
        if not next_frontier:
            break
        frontier = next_frontier

    # Search for the neighbor closest to the targets among the visited nodes
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
    """Analyzes the ontology coverage against the PICOT questions.

    Port of ``analyzeCoverage()`` in enrich-propose.js.

    Returns:
        dict with keys ``summary``, ``missing_concepts``, ``path_gaps``.
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

        # Flattening and deduplication of the matched concept IDs
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


# ── Grouping of missing concepts ───────────────────────────────────────────────


def group_missing_concepts(
    missing: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Groups the missing tokens by lexical similarity.

    Port of ``groupMissingConcepts()`` in enrich-propose.js.
    Jaccard threshold on words: > 0.4 (identical to the JS).
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


# ── Proposal consolidation helpers ─────────────────────────────────────────────


def make_id(prefix: str, counter: int, today: str) -> str:
    """Generates a structured identifier of the form ``ENRC_20260619_001``.

    Port of ``makeId()`` in scripts/lib/bootstrap.mjs.
    The ``today`` parameter is in YYYYMMDD format (already computed by the caller).
    """
    return f"{prefix}_{today}_{str(counter).zfill(3)}"


def reassign_ids(
    batch: dict[str, Any],
    counters: dict[str, int],
    today: str,
) -> None:
    """Reassigns sequential identifiers to the batch entities.

    Port of ``reassignIds()`` in enrich-propose.js (in-place mutation).
    ``today`` must be in YYYYMMDD format (e.g. ``"20260619"``).
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
    """Merges the lists of ``source`` into ``target`` (in-place mutation).

    Port of ``mergeInto()`` in enrich-propose.js.
    """
    for key in target:
        if isinstance(source.get(key), list):
            target[key].extend(source[key])


def stamp_rows(proposals: dict[str, Any], version: str) -> None:
    """Adds the review metadata on all the batch entities.

    Port of ``stampRows()`` in enrich-propose.js (in-place mutation).
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


# ── Pre-checks ─────────────────────────────────────────────────────────────────


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
    """Applies the validation and deduplication rules on a batch.

    Port of ``applyPreChecks()`` in enrich-propose.js.

    Rejection rules (faithful to the JS):
    - Self-loop: subject == object
    - Duplicate relation: key ``subject|predicate|object|polarity`` already seen
    - Orphan subject: subject_concept_id unknown to the batch + existing
    - Orphan object: same for object
    - Unknown predicate: predicate not in valid_predicate_ids
    - L1 concept without a standard code

    Side effects:
    - Detection and return of opposite-polarity conflicts
    - Auto-stub of evidence for relations without evidence

    Args:
        today: date in YYYYMMDD format for the auto-stub IDs. If None,
            uses the current date.

    Returns:
        List of detected polarity conflicts (each element contains
        ``proposed`` and ``opposite_key``).
    """
    _today = today or date.today().strftime("%Y%m%d")

    # Set of all concept IDs known at the batch's entry
    batch_concept_ids: set[str] = existing_concept_ids | {
        c["local_concept_id"] for c in batch.get("taxonomy_concepts", [])
    }
    batch_relation_keys: set[str] = set(existing_relation_keys)
    conflicts: list[dict[str, Any]] = []

    # ── Relation filtering ─────────────────────────────────────────────────────
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

        # Duplicate by composite key
        key = f"{subj}|{pred}|{obj}|{pol}"
        if key in batch_relation_keys:
            log.append(f"  REJECT duplicate: {rel.get('relation_id')} ({key})")
            continue

        # Orphan subject
        if subj not in batch_concept_ids:
            log.append(f"  REJECT orphan subject: {rel.get('relation_id')} → {subj}")
            continue

        # Orphan object
        if obj not in batch_concept_ids:
            log.append(f"  REJECT orphan object: {rel.get('relation_id')} → {obj}")
            continue

        # Unknown predicate
        if pred not in valid_predicate_ids:
            log.append(f"  REJECT unknown predicate: {rel.get('relation_id')} → {pred}")
            continue

        # Opposite-polarity conflict detection
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

    # ── Concept deduplication ──────────────────────────────────────────────────
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

    # ── Reject L1 without a standard code ──────────────────────────────────────
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

    # ── Re-filtering relations after concept rejection ─────────────────────────
    # A concept accepted at the orphan-filtering stage may have been rejected
    # afterwards (duplicate, L1-without-code). We clean up the corresponding relations.
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

    # ── Cleanup of synonyms and codes for rejected concepts ────────────────────
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

    # ── Filtering of evidence for rejected relations ───────────────────────────
    kept_evidence: list[dict[str, Any]] = []
    for e in batch.get("ontology_relation_evidence", []):
        if e.get("relation_id") not in final_rel_ids:
            log.append(f"  DROP evidence for rejected relation: {e.get('evidence_id')}")
            continue
        kept_evidence.append(e)
    batch["ontology_relation_evidence"] = kept_evidence

    # ── Auto-stub of missing evidence ──────────────────────────────────────────
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
