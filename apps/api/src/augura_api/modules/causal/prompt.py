"""Forced tool + prompts for the DAG filter (port of dag-llm-schema.js).

Identical in intent to Nico's Anthropic tool: select / discard / assign
roles, and propose missing concepts/relations for the causal pathway.
"""

import json

from anthropic.types import ToolParam

from augura_api.modules.causal.roles import dagitty_json
from augura_api.modules.causal.schemas import MappedConcept, Picot
from augura_api.modules.causal.subgraph import ConceptMeta, Relation
from augura_api.modules.semantic import vocab

_ROLE_ENUM = [
    "exposure",
    "outcome",
    "confounder",
    "mediator",
    "effect_modifier",
    "collider",
    "other",
]

DAG_FILTER_TOOL: ToolParam = {
    "name": "filter_dag_relations",
    "description": "Filter and role-assign ontology relations for a clinical causal DAG",
    "input_schema": {
        "type": "object",
        "required": [
            "selected_relations",
            "excluded_relations",
            "node_roles",
            "missing_variables",
            "proposed_concepts",
            "proposed_relations",
            "llm_reasoning",
        ],
        "properties": {
            "selected_relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "relation_id",
                        "dag_role_subject",
                        "dag_role_object",
                        "inclusion_reason",
                    ],
                    "properties": {
                        "relation_id": {"type": "string"},
                        "dag_role_subject": {"type": "string", "enum": _ROLE_ENUM},
                        "dag_role_object": {"type": "string", "enum": _ROLE_ENUM},
                        "inclusion_reason": {"type": "string"},
                    },
                },
            },
            "excluded_relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["relation_id", "exclusion_reason"],
                    "properties": {
                        "relation_id": {"type": "string"},
                        "exclusion_reason": {"type": "string"},
                        "recommendation": {
                            "type": "string",
                            "enum": ["remove", "qualifier"],
                            "description": (
                                "remove = the relation is wrong/misleading in general; "
                                "qualifier = true in general but not in this clinical context"
                            ),
                        },
                    },
                },
            },
            "node_roles": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": _ROLE_ENUM},
                        "reasoning": {"type": "string"},
                    },
                },
            },
            "missing_variables": {"type": "array", "items": {"type": "string"}},
            "proposed_concepts": {
                "type": "array",
                "description": (
                    "New taxonomy concepts needed for the causal pathway, absent from both "
                    "mapped concepts and the ontology subgraph. Use provisional IDs prefixed "
                    "PROP_ (e.g. PROP_icm_detection_sensitivity). Persisted for human review."
                ),
                "items": {
                    "type": "object",
                    "required": ["provisional_id", "label", "domain", "layer", "rationale"],
                    "properties": {
                        "provisional_id": {"type": "string"},
                        "label": {"type": "string"},
                        "domain": {
                            "type": "string",
                            "enum": [
                                "condition",
                                "measurement",
                                "intervention",
                                "biomarker",
                                "demographic",
                                "device",
                                "event",
                                "procedure",
                                "other",
                            ],
                        },
                        "layer": {"type": "integer", "minimum": 0, "maximum": 3},
                        "rationale": {"type": "string"},
                    },
                },
            },
            "proposed_relations": {
                "type": "array",
                "description": (
                    "Causal relations absent from the candidate set needed to connect exposure "
                    "to outcome. May reference any mapped/subgraph concept ID or a provisional_id."
                ),
                "items": {
                    "type": "object",
                    "required": [
                        "subject_concept_id",
                        "object_concept_id",
                        "predicate",
                        "polarity",
                        "default_strength",
                        "mechanism_summary",
                    ],
                    "properties": {
                        "subject_concept_id": {"type": "string"},
                        "object_concept_id": {"type": "string"},
                        "predicate": {
                            "type": "string",
                            "enum": [
                                "causally_influences",
                                "precedes",
                                "associated_with",
                                "modifies_effect_of",
                                "prevents",
                                "predicts",
                            ],
                        },
                        "polarity": {
                            "type": "string",
                            "enum": vocab.POLARITY,
                        },
                        "default_strength": {
                            "type": "string",
                            "enum": ["strong", "moderate", "weak"],
                        },
                        "mechanism_summary": {"type": "string"},
                    },
                },
            },
            "llm_reasoning": {"type": "string"},
        },
    },
}


SYSTEM_PROMPT = (
    "You are a biomedical causal ontology expert assisting in constructing causal directed "
    "acyclic graphs (DAGs) for MedTech real-world evidence studies.\n\n"
    "Your task is to contextualize a pre-curated set of ontology relationships to a specific "
    "clinical question and dataset.\n\n"
    "Core principles:\n"
    "- DAG roles (exposure, outcome, confounder, mediator, effect_modifier, collider) are "
    "CONTEXT-SPECIFIC. They are not permanent properties of a concept.\n"
    "- The same concept (e.g., HbA1c) can be an outcome in one question, a confounder in "
    "another, and an eligibility criterion in a third.\n"
    "- Your job is to SELECT relevant relationships, ASSIGN appropriate roles, and PRUNE "
    "irrelevant ones.\n"
    "- Be conservative: only include relationships genuinely relevant to this question.\n"
    "- Consider relationship qualifiers carefully — hard constraints must be respected.\n"
    "- If the candidate relations do not cover the main exposure-to-outcome causal path (or "
    "key mediators/confounders on it), fill the gaps: first reference an ONTOLOGY SUBGRAPH "
    "concept if present; otherwise add a PROP_ concept to proposed_concepts and reference it "
    "in proposed_relations. Return empty arrays when the candidate set is sufficient.\n\n"
    "Role definitions:\n"
    "- exposure: the primary intervention, treatment, or device under investigation\n"
    "- outcome: the primary or secondary endpoint the question is evaluating\n"
    "- confounder: affects both exposure and outcome (must be accounted for)\n"
    "- mediator: an intermediate variable on the causal pathway exposure→outcome\n"
    "- effect_modifier: changes the magnitude/direction of the exposure-outcome relationship\n"
    "- collider: caused by both exposure and outcome (conditioning opens a spurious path)\n"
    "- other: a relevant variable not fitting one of the causal roles above\n\n"
    "Reason in two stages within this single response:\n"
    "Stage A — Independent derivation: first reason through the causal question from your own "
    "medical knowledge: which variables lie on the exposure→outcome path, which are confounders, "
    "which are mediators, and the key mechanisms.\n"
    "Stage B — Subgraph comparison: then compare your independent model against the CANDIDATE "
    "ONTOLOGY RELATIONS and the DETERMINISTIC STRUCTURAL ROLES provided. Keep relations that "
    "align, exclude those that do not fit the clinical context, and add anything missing from the "
    "candidate set (present in your independent model) via proposed_relations/proposed_concepts. "
    "Begin llm_reasoning with a short summary of your Stage A independent model."
)


def _roles_lines(roles: dict[str, str]) -> str:
    if not roles:
        return "  (none)"
    return "\n".join(f"  {cid}: {role}" for cid, role in sorted(roles.items()))


def _concept_lines(mapped: list[MappedConcept]) -> str:
    out: list[str] = []
    for c in mapped:
        conf = f" (match confidence: {c.confidence * 100:.0f}%)" if c.confidence else ""
        out.append(
            f'  {c.concept_id}: "{c.concept_label}" [{c.concept_domain}, L{c.concept_layer}]{conf}'
        )
    return "\n".join(out)


def _inferred_lines(inferred: list[tuple[str, ConceptMeta]]) -> str:
    return "\n".join(f'  {cid}: "{m.label}" [{m.domain}, L{m.layer}]' for cid, m in inferred)


def _relation_lines(candidates: list[Relation]) -> str:
    out: list[str] = []
    for rel in candidates:
        qual = ""
        if rel.qualifiers:
            parts = [
                f"[{'HARD CONSTRAINT' if q['is_hard_constraint'] else 'advisory'}] {q['effect']}"
                for q in rel.qualifiers
            ]
            qual = f"\n    ⚠ QUALIFIER: {'; '.join(parts)}"
        ev = ""
        if rel.evidence:
            ev = f"\n    Evidence: {rel.evidence[0]['citation']} ({rel.evidence[0]['strength']})"
        out.append(
            f'  {rel.id}: "{rel.subject_concept_id}" '
            f"--[{rel.predicate}, polarity:{rel.polarity}, strength:{rel.default_strength}]--> "
            f'"{rel.object_concept_id}"\n    Mechanism: {rel.mechanism_summary}{ev}{qual}'
        )
    return "\n".join(out)


def _picot_lines(picot: Picot | None) -> str:
    if picot is None:
        return "  (not parsed)"
    rows = [
        f"  Intervention/Exposure: {picot.intervention}" if picot.intervention else None,
        f"  Comparator: {picot.comparator}" if picot.comparator else None,
        (
            f"  Outcomes: {', '.join(o.label or o.concept_id or '' for o in picot.outcomes)}"
            if picot.outcomes
            else None
        ),
        f"  Timeframe: {picot.timeframe}" if picot.timeframe else None,
        f"  Population: {picot.population}" if picot.population else None,
        f"  Therapeutic Area: {picot.therapeutic_area}" if picot.therapeutic_area else None,
    ]
    kept = [r for r in rows if r]
    return "\n".join(kept) if kept else "  (not parsed)"


def _node_roles_requirement(mapped: list[MappedConcept], picot: Picot | None) -> str:
    if not mapped:
        return ""
    iv = picot.intervention_concept_id if picot else None
    outs = [o.concept_id for o in (picot.outcomes if picot else []) if o.concept_id]
    iv_note = f'\n  Intervention/exposure concept (role "exposure"): {iv}' if iv else ""
    out_note = f'\n  Outcome concepts (role "outcome"): {", ".join(outs)}' if outs else ""
    return (
        "\nREQUIREMENT — node_roles completeness: include an entry in node_roles for EVERY "
        "concept in MAPPED DATASET CONCEPTS above, even if it has no candidate relations."
        f"{iv_note}{out_note}\n  Use the PICOT and clinical question to determine each role."
    )


def build_user_prompt(
    *,
    clinical_question: str | None,
    picot: Picot | None,
    mapped: list[MappedConcept],
    candidates: list[Relation],
    inferred: list[tuple[str, ConceptMeta]],
    structural_roles: dict[str, str] | None = None,
) -> str:
    structural_roles = structural_roles or {}
    dag_json = json.dumps(dagitty_json(candidates, structural_roles))
    inferred_section = (
        "\nONTOLOGY SUBGRAPH CONCEPTS (inferred neighbors — usable in proposed_relations "
        f"without declaring in proposed_concepts):\n{_inferred_lines(inferred)}\n"
        if inferred
        else ""
    )
    return (
        f'CLINICAL QUESTION:\n"{clinical_question or "Not specified"}"\n\n'
        f"PARSED PICOT:\n{_picot_lines(picot)}\n\n"
        f"MAPPED DATASET CONCEPTS (present in uploaded data):\n"
        f"{_concept_lines(mapped) or '  (none mapped)'}\n"
        f"{inferred_section}\n"
        f"CANDIDATE ONTOLOGY RELATIONS (retrieved for this concept set):\n"
        f"{_relation_lines(candidates) or '  (none found)'}\n\n"
        f"DETERMINISTIC STRUCTURAL ROLES (pre-LLM, from graph topology + PICOT):\n"
        f"{_roles_lines(structural_roles)}\n\n"
        f"CANDIDATE DAG (dagitty-like JSON):\n  {dag_json}\n"
        f"{_node_roles_requirement(mapped, picot)}\n"
        "Return the filter_dag_relations tool call selecting/excluding relations, assigning "
        "node_roles, and proposing concepts/relations only where the candidate set is "
        "insufficient to connect the exposure to the outcome."
    )
