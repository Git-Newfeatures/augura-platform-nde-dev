"""Build the manifest + payload for a dimension-grammar / affix-archetype release.

This is the reusable "send an affix update" artifact: it holds the governed
dimension grammar as Python data and emits exactly what
`public.upsert_semantic_release(manifest, payload)` expects — the same SECURITY
DEFINER function that applies taxonomy/ontology enrichment. Mirrors the seed in
supabase/seed.sql (fresh-DB path); this script is the live-DB / pipeline path.

Usage:
  python scripts/affix_release_payload.py            # → {manifest, payload} JSON
  python scripts/affix_release_payload.py --sql      # → ready-to-run SELECT ...

Apply the JSON via SemanticRepo.apply_release(manifest, payload) (the API path),
or the --sql output via the Supabase SQL editor / MCP execute_sql.
"""

from __future__ import annotations

import json
import sys

RELEASE_VERSION = "2.3.0"

MANIFEST = {
    "semantic_release_version": RELEASE_VERSION,
    "taxonomy_version": "2.1.0",  # adds the L1_surgery anchor concept
    "causal_ontology_version": "2.0.0",  # unchanged
    "dq_ontology_version": "1.2.0",  # bumps with the release (§15.1)
    "omop_cdm_version": "5.4",
    "source": "Dimension grammar & affix archetypes (Phase 1): dimension_kinds + "
    "affix archetypes/values/aliases.",
}

# Anchor concept for the relative-time (post-operative) archetype. Generic surgical
# event — PROPOSED, pending domain review (distinct from L1_P002 Bariatric Surgery).
TAXONOMY_CONCEPTS = [
    {
        "local_concept_id": "L1_surgery",
        "layer": 1,
        "concept_name": "Surgery (procedure)",
        "review_section": "procedure",
        "augura_domain": "procedure",
        "omop_domain_id": "Procedure",
        "namespace": "AUG_PROC",
        "design_rationale": "Generic surgical-procedure event used as the anchor for "
        "relative-time affixes (postop/preop). Proposed anchor pending domain review; "
        "not a specific procedure (cf. L1_P002 Bariatric Surgery).",
        "review_status": "proposed",
        "version": RELEASE_VERSION,
        "active": True,
        "temporality": "static",
        "fhir_crosswalk": "Procedure",
        "unit_coverage_status": "not_applicable",
        "range_support_status": "not_applicable",
    }
]


def _kind(kid, label, desc, value_model, comparability, role):
    return {
        "dimension_kind_id": kid,
        "label": label,
        "description": desc,
        "value_model": value_model,
        "default_comparability": comparability,
        "structural_role": role,
        "review_status": "approved",
        "version": RELEASE_VERSION,
        "active": True,
    }


DIMENSION_KINDS = [
    _kind(
        "scheduled_time",
        "Scheduled Time",
        "Study-schedule visit/timepoint carried in a "
        "label (baseline, week12, 6mo), resolved via the study visit map.",
        "scheduled",
        "preserves",
        "observation_time",
    ),
    _kind(
        "relative_time",
        "Relative Time",
        "Time relative to an anchoring clinical event "
        "(postop, day3); reconciles to the same statement as a long-table observation time.",
        "event_anchored",
        "preserves",
        "observation_time",
    ),
    _kind(
        "laterality",
        "Laterality",
        "Body side: left / right / bilateral.",
        "closed_set",
        "preserves",
        None,
    ),
    _kind(
        "body_site",
        "Body Site",
        "Anatomical site qualifier (knee, hip, lumbar).",
        "closed_set",
        "case_by_case",
        None,
    ),
    _kind(
        "specimen",
        "Specimen",
        "Biological specimen the measurement was taken from (serum, plasma, urine, csf).",
        "closed_set",
        "case_by_case",
        None,
    ),
    _kind(
        "method",
        "Method",
        "Measurement method / assay / modality qualifier.",
        "closed_set",
        "case_by_case",
        None,
    ),
    _kind(
        "derived_statistic",
        "Derived Statistic",
        "A statistic computed over a base concept "
        "(mean, delta, AUC, nadir); may change unit/range.",
        "parametric",
        "case_by_case",
        None,
    ),
    _kind(
        "aggregation_window",
        "Aggregation Window",
        "Window over which a value is aggregated (24h, 7d, weekly).",
        "parametric",
        "case_by_case",
        None,
    ),
    _kind(
        "rater",
        "Rater",
        "Who or what produced the rating (clinician, self, device).",
        "closed_set",
        "case_by_case",
        None,
    ),
    _kind(
        "replicate",
        "Replicate",
        "Replicate / sequence index of a repeated measurement (rep1, r2).",
        "ordinal",
        "preserves",
        None,
    ),
    _kind(
        "vocabulary",
        "Vocabulary",
        "Coding vocabulary the value is expressed in (icd10, snomed, loinc).",
        "closed_set",
        "preserves",
        None,
    ),
    _kind(
        "condition_status",
        "Condition Status",
        "Status qualifier that changes clinical meaning (active, history_of, suspected).",
        "closed_set",
        "forks",
        None,
    ),
]


def _afx(
    aid,
    name,
    kind,
    position,
    value_model,
    comparability,
    *,
    anchor=None,
    operator=None,
    rule=None,
    sibling=False,
    weight=1.0,
    threshold=0.60,
    review="approved",
):
    return {
        "affix_archetype_id": aid,
        "archetype_name": name,
        "dimension_kind_id": kind,
        "position": position,
        "separator_style": "_",
        "value_model": value_model,
        "comparability": comparability,
        "anchor_concept_id": anchor,
        "operator": operator,
        "extraction_rule": rule,
        "requires_residual_maps": True,
        "requires_sibling_family": sibling,
        "evidence_weight": weight,
        "confidence_threshold": threshold,
        "review_status": review,
        "version": RELEASE_VERSION,
        "active": True,
    }


AFFIX_ARCHETYPES = [
    _afx(
        "AFX_LATERALITY",
        "Laterality suffix",
        "laterality",
        "suffix",
        "closed_set",
        "preserves",
        sibling=True,
        weight=1.0,
    ),
    _afx(
        "AFX_SCHEDULED_TIME",
        "Scheduled-time suffix",
        "scheduled_time",
        "suffix",
        "parametric",
        "preserves",
        rule="visit_map",
        sibling=True,
        weight=0.80,
    ),
    _afx(
        "AFX_RELATIVE_TIME_POSTOP",
        "Post-operative relative time",
        "relative_time",
        "prefix",
        "event_anchored",
        "preserves",
        anchor="L1_surgery",
        operator="post",
        rule="offset_regex",
        weight=0.90,
        review="proposed",
    ),
    _afx(
        "AFX_SPECIMEN",
        "Specimen suffix",
        "specimen",
        "suffix",
        "closed_set",
        "forks",
        weight=0.90,
        threshold=0.65,
    ),
    _afx(
        "AFX_DERIVED_STAT",
        "Derived-statistic prefix",
        "derived_statistic",
        "prefix",
        "parametric",
        "preserves",
        operator="statistic",
        rule="stat_fn",
        weight=0.70,
    ),
]


def _val(aid, value, label):
    return {
        "affix_archetype_id": aid,
        "canonical_value": value,
        "label": label,
        "review_status": "approved",
    }


AFFIX_ARCHETYPE_VALUES = [
    _val("AFX_LATERALITY", "left", "Left"),
    _val("AFX_LATERALITY", "right", "Right"),
    _val("AFX_LATERALITY", "bilateral", "Bilateral"),
    _val("AFX_SPECIMEN", "serum", "Serum"),
    _val("AFX_SPECIMEN", "plasma", "Plasma"),
    _val("AFX_SPECIMEN", "urine", "Urine"),
    _val("AFX_SPECIMEN", "csf", "Cerebrospinal fluid"),
]


def _alias(aid, token, value, review="approved"):
    return {
        "affix_archetype_id": aid,
        "token": token,
        "canonical_value": value,
        "source": "curated",
        "review_status": review,
    }


AFFIX_ARCHETYPE_ALIASES = [
    _alias("AFX_LATERALITY", "left", "left"),
    _alias("AFX_LATERALITY", "l", "left"),
    _alias("AFX_LATERALITY", "right", "right"),
    _alias("AFX_LATERALITY", "r", "right"),
    _alias("AFX_LATERALITY", "bilateral", "bilateral"),
    _alias("AFX_LATERALITY", "bilat", "bilateral"),
    _alias("AFX_LATERALITY", "od", "right"),
    _alias("AFX_LATERALITY", "os", "left"),
    _alias("AFX_LATERALITY", "ou", "bilateral"),
    _alias("AFX_SPECIMEN", "serum", "serum"),
    _alias("AFX_SPECIMEN", "plasma", "plasma"),
    _alias("AFX_SPECIMEN", "urine", "urine"),
    _alias("AFX_SPECIMEN", "csf", "csf"),
    _alias("AFX_SCHEDULED_TIME", "baseline", None),
    _alias("AFX_SCHEDULED_TIME", "screening", None),
    _alias("AFX_SCHEDULED_TIME", "eot", None),
    _alias("AFX_SCHEDULED_TIME", "week12", None),
    _alias("AFX_SCHEDULED_TIME", "wk12", None),
    _alias("AFX_SCHEDULED_TIME", "w12", None),
    _alias("AFX_SCHEDULED_TIME", "6mo", None),
    _alias("AFX_SCHEDULED_TIME", "m6", None),
    _alias("AFX_SCHEDULED_TIME", "month6", None),
    _alias("AFX_RELATIVE_TIME_POSTOP", "postop", None, review="proposed"),
    _alias("AFX_RELATIVE_TIME_POSTOP", "post_op", None, review="proposed"),
    _alias("AFX_RELATIVE_TIME_POSTOP", "postoperative", None, review="proposed"),
    _alias("AFX_DERIVED_STAT", "mean", None),
    _alias("AFX_DERIVED_STAT", "min", None),
    _alias("AFX_DERIVED_STAT", "max", None),
    _alias("AFX_DERIVED_STAT", "sd", None),
    _alias("AFX_DERIVED_STAT", "delta", None),
    _alias("AFX_DERIVED_STAT", "change", None),
    _alias("AFX_DERIVED_STAT", "auc", None),
    _alias("AFX_DERIVED_STAT", "nadir", None),
]

PAYLOAD = {
    "taxonomy_concepts": TAXONOMY_CONCEPTS,
    "dimension_kinds": DIMENSION_KINDS,
    "affix_archetypes": AFFIX_ARCHETYPES,
    "affix_archetype_values": AFFIX_ARCHETYPE_VALUES,
    "affix_archetype_aliases": AFFIX_ARCHETYPE_ALIASES,
}


def main() -> None:
    if "--sql" in sys.argv:
        m = json.dumps(MANIFEST, ensure_ascii=False)
        p = json.dumps(PAYLOAD, ensure_ascii=False)
        # Dollar-quoted so the JSON needs no escaping (it never contains the tags).
        print(
            f"select public.upsert_semantic_release(\n  $m${m}$m$::jsonb,\n  $p${p}$p$::jsonb\n);"
        )
    else:
        print(json.dumps({"manifest": MANIFEST, "payload": PAYLOAD}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
