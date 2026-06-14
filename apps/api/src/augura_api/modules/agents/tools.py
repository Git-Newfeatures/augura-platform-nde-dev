"""Outils forcés + prompts des agents (ports de lucis-dashboard/api/*.js)."""

from typing import Any

from anthropic.types import ToolParam

from augura_api.modules.agents.schemas import DagRequest

DAG_TOOL: ToolParam = {
    "name": "build_dag",
    "description": (
        "Construct a minimal, correctly specified causal DAG for an observational health study."
    ),
    "input_schema": {
        "type": "object",
        "required": ["nodes", "edges", "adjustment_set", "rationale"],
        "properties": {
            "nodes": {
                "type": "array",
                "description": "All variables in the causal model",
                "items": {
                    "type": "object",
                    "required": ["id", "label", "role", "measured"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": (
                                "Short unique ID: A (treatment), Y (outcome), "
                                "W1-Wn (confounders), M1-Mn (mediators), "
                                "E1-En (effect modifiers), U1-Un (unmeasured), "
                                "C1-Cn (colliders)"
                            ),
                        },
                        "label": {"type": "string", "description": "Human-readable name"},
                        "role": {
                            "type": "string",
                            "enum": [
                                "intervention",
                                "outcome",
                                "confounder",
                                "mediator",
                                "effect_modifier",
                                "unmeasured_confounder",
                                "collider",
                            ],
                        },
                        "measured": {
                            "type": "boolean",
                            "description": "Whether this variable is in the dataset",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Clinical/methodological rationale",
                        },
                    },
                },
            },
            "edges": {
                "type": "array",
                "description": "Directed edges (from → to)",
                "items": {
                    "type": "object",
                    "required": ["from", "to"],
                    "properties": {
                        "from": {"type": "string", "description": "Source node ID"},
                        "to": {"type": "string", "description": "Target node ID"},
                    },
                },
            },
            "adjustment_set": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Minimal sufficient adjustment set — confounder IDs to control "
                    "for. NEVER include mediators or colliders."
                ),
            },
            "collider_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "IDs of all collider nodes (≥2 incoming edges). Must never be "
                    "adjusted for. Empty array if none."
                ),
            },
            "rationale": {
                "type": "string",
                "description": "2–3 sentence summary of structure and assumptions",
            },
        },
    },
}

DAG_SYSTEM_PROMPT = (
    "You are a causal inference expert building directed acyclic graphs (DAGs) for "
    "real-world evidence studies in digital health. Construct a correctly specified "
    "causal DAG given a study's intervention, outcome, and population, grounded in the "
    "published epidemiological and clinical literature for this specific outcome in "
    "cardiometabolic / preventive health.\n\n"
    "Variable types: confounders (cause BOTH intervention and outcome — the minimal "
    "sufficient adjustment set); mediators (on the causal pathway, never adjusted for "
    "in a total-effect analysis); effect_modifiers (modify the effect magnitude); "
    "unmeasured_confounder (important confounders structurally absent from platform "
    "data, retained for E-value sensitivity); collider (caused by ≥2 other nodes — "
    "NEVER adjust for; conditioning opens collider bias).\n\n"
    "measured=true only if the variable is in the client dataset; measured=false flags "
    "a data gap requiring sensitivity analysis.\n\n"
    "Rules: keep the DAG parsimonious; exactly one intervention (A) and one outcome (Y) "
    "node; ALWAYS include a direct A→Y edge (the total effect of interest); every edge "
    "references valid node IDs; confounders have edges to both A and Y; mediators have "
    "an edge from A and to Y and are NOT in the adjustment set; colliders have ≥2 "
    "incoming edges and are listed in collider_ids, never in adjustment_set; the "
    "collider_ids field is always present (empty [] if none); include a rationale per "
    "node. Other candidate outcomes are alternative endpoints, NOT covariates — never "
    "place them in confounders, mediators, effect_modifiers, unmeasured, or colliders."
)

# Contexte clinique spécifique à l'outcome (clé = selected_outcome).
OUTCOME_CONTEXT: dict[str, str] = {
    "hba1c": (
        "OUTCOME — HbA1c % change at 12 months. Known confounders: baseline HbA1c "
        "(regression to mean), age, sex, BMI, baseline medication (esp. metformin — "
        "NOT in dataset), disease duration. Mediators: dietary adherence, activity "
        "change, plan completion, weight change. Key gap: medication changes are a "
        "critical unmeasured confounder."
    ),
    "ldl": (
        "OUTCOME — LDL-C mg/dL change at 12 months. Known confounders: baseline LDL-C, "
        "statin use (CRITICAL — NOT in dataset), age, sex, BMI, dietary fat, thyroid "
        "status. Mediators: dietary change, activity, weight loss. Key gap: statin "
        "initiation/dose change is the primary threat to validity."
    ),
    "crp": (
        "OUTCOME — hs-CRP mg/L change at 12 months. Known confounders: baseline hs-CRP, "
        "BMI, smoking (NOT in dataset), acute infection at measurement, sex, age. "
        "Mediators: weight loss (strongest), activity, dietary inflammatory index, "
        "sleep. Key gap: smoking and acute illness; high within-person variability."
    ),
}


def build_dag_user_message(req: DagRequest) -> str:
    others = [c for c in req.candidate_outcomes if c != req.selected_outcome]
    other_block = ""
    if others:
        other_block = (
            f"\n**Other candidate outcomes (DO NOT include in DAG):** {', '.join(others)}\n"
        )

    dataset_block = _dataset_block(req.dataset_variables)
    gap_block = _gap_block(req.gap_variables)
    study = "Prospective" if req.study_type == "prosp" else "Retrospective observational"
    outcome_ctx = OUTCOME_CONTEXT.get(req.selected_outcome or "", "")
    ctx_block = (
        f"\n**Literature guidance for this outcome:**\n{outcome_ctx}\n" if outcome_ctx else ""
    )

    return (
        "Build the causal DAG for this real-world evidence study:\n\n"
        f"**Intervention:** {req.intervention}\n"
        f"**Outcome:** {req.outcome}\n"
        f"**Population:** {req.population or 'Not specified'}\n"
        f"**Study type:** {study}\n"
        f"{other_block}{dataset_block}{gap_block}\n"
        f"**Product context:**\n{req.product_docs or '(none provided)'}\n"
        f"{ctx_block}"
        "Use the dataset inventory and pre-identified gaps to set measured=true/false "
        "accurately. Every variable in the data gaps section MUST appear as a node with "
        "measured=false."
    )


def _dataset_block(dv: dict[str, object] | None) -> str:
    if not dv:
        return ""
    lines: list[str] = []
    mapping = {
        "primaryExposure": "confirmed exposure column (measured=true)",
        "outcomes": "confirmed outcome columns (measured=true)",
        "measuredConfounders": "measured confounders (measured=true)",
        "unmeasuredConfounders": "unmeasured confounders absent from dataset (measured=false)",
        "mediators": "measured mediators (measured=true)",
        "effectModifiers": "effect modifiers (measured=true)",
        "exposureComponents": "exposure components (NOT in adjustment set)",
    }
    for key, label in mapping.items():
        value = dv.get(key)
        if value:
            lines.append(f"**Dataset — {label}:** {value}")
    if not lines:
        return ""
    return (
        "\n**Dataset variable inventory (from uploaded client dataset):**\n"
        + "\n".join(lines)
        + "\n"
    )


def _gap_block(gaps: list[dict[str, object]]) -> str:
    if not gaps:
        return ""
    lines = ["\n**Pre-identified data gaps (include ALL as measured=false nodes):**"]
    for g in gaps:
        lines.append(f"  - {g.get('name')} | role: {g.get('role')} | severity: {g.get('severity')}")
    return "\n".join(lines) + "\n"


# ── gap-detection (port de api/gap-detection.js) ────────────────────────────

GAP_TOOL: ToolParam = {
    "name": "identify_data_gaps",
    "description": (
        "For a given intervention-outcome pair, identify clinically important "
        "variables the literature expects that are absent from the dataset."
    ),
    "input_schema": {
        "type": "object",
        "required": ["missing_variables"],
        "properties": {
            "missing_variables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "role", "category", "rationale", "severity"],
                    "properties": {
                        "name": {"type": "string"},
                        "column_hint": {"type": "string"},
                        "role": {
                            "type": "string",
                            "enum": [
                                "unmeasured_confounder",
                                "unmeasured_mediator",
                                "effect_modifier",
                            ],
                        },
                        "category": {
                            "type": "string",
                            "enum": ["user", "environment", "engagement"],
                        },
                        "rationale": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "moderate", "low"],
                        },
                    },
                },
            }
        },
    },
}

GAP_SYSTEM_PROMPT = (
    "You are a causal inference expert performing a data gap analysis for a "
    "real-world evidence study. Given an intervention-outcome pair and the list of "
    "variables already measured, identify which clinically important variables the "
    "published literature would expect for this causal question but are ABSENT from "
    "the dataset. Focus on variables that are well-established confounders, mediators, "
    "or effect modifiers; not already present; and would materially affect the "
    "estimate. For digital-health / cardiometabolic RWE always consider: concomitant "
    "medication changes (statins, metformin, GLP-1, antihypertensives — often critical "
    "unmeasured confounders); health motivation / self-efficacy (healthy-user bias); "
    "health literacy; SES / income; concurrent clinical care; acute illness at "
    "measurement (esp. hs-CRP); disease duration (HbA1c). Only return variables "
    "structurally absent (not captured by any proxy column). Keep it parsimonious: "
    "3–6 variables maximum, prioritised by severity."
)


def build_gap_user_message(
    *,
    intervention: str,
    outcome: str,
    population: str | None,
    selected_outcome: str | None,
    measured: list[tuple[str, str | None]],
) -> str:
    if measured:
        measured_list = "\n".join(f"  - {col} (role: {role or '?'})" for col, role in measured)
    else:
        measured_list = "  (no confirmed variables from dataset)"
    return (
        "Identify data gaps for this causal question:\n\n"
        f"**Intervention:** {intervention}\n"
        f"**Outcome:** {outcome}\n"
        f"**Population:** {population or 'Not specified'}\n"
        f"**Selected outcome key:** {selected_outcome or 'unspecified'}\n\n"
        f"**Variables already measured (DO NOT flag these):**\n{measured_list}\n\n"
        "Return the clinically important variables the literature expects for this "
        "intervention-outcome pair but absent from the dataset above."
    )


# ── variable-check 1b (port de api/variable-check.js) ───────────────────────

VARIABLE_CHECK_TOOL: ToolParam = {
    "name": "classify_columns",
    "description": (
        "Classify each uploaded column by its causal role and display group in a "
        "real-world evidence study, and where applicable match it to a canonical outcome."
    ),
    "input_schema": {
        "type": "object",
        "required": ["columns"],
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "sheet",
                        "column",
                        "proposed_role",
                        "proposed_group",
                        "confidence",
                        "rationale",
                    ],
                    "properties": {
                        "sheet": {"type": "string"},
                        "column": {"type": "string"},
                        "proposed_role": {
                            "type": "string",
                            "enum": [
                                "outcome",
                                "exposure",
                                "exposure_component",
                                "measured_confounder",
                                "unmeasured_confounder",
                                "mediator",
                                "effect_modifier",
                                "collider",
                                "id",
                                "time",
                                "unused",
                                "other",
                            ],
                        },
                        "proposed_group": {
                            "type": "string",
                            "enum": [
                                "outcomes",
                                "exposure",
                                "engagement",
                                "user_variables",
                                "environment",
                                "mediators",
                                "identifiers",
                                "time",
                                "unused",
                                "other",
                            ],
                        },
                        "proposed_canonical_id": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "rationale": {"type": "string"},
                        "alternatives": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    },
}

VARCHECK_SYSTEM_PROMPT = (
    "You are the Augura variable-classification agent. For each column in an uploaded "
    "dataset, classify its causal role in a planned real-world evidence study.\n\n"
    "ROLES (proposed_role): outcome (dependent variable at follow-up); exposure (primary "
    "intervention/treatment, e.g. composite engagement score); exposure_component "
    "(sub-signal of a composite exposure — NOT in the adjustment set); measured_confounder "
    "(causes both exposure and outcome AND present); unmeasured_confounder (clinically "
    "important but structurally absent — flag for data gap / E-value); mediator (on the "
    "pathway exposure→outcome, never adjusted for total effect); effect_modifier (modifies "
    "effect magnitude); collider (caused by ≥2 variables, NEVER adjust for); id; time; "
    "unused (present but irrelevant); other.\n\n"
    "DISPLAY GROUPS (proposed_group, independent of role): outcomes; exposure; engagement "
    "(app usage/adherence/logins/completion — regardless of role); user_variables (age, sex, "
    "BMI, ethnicity, country, baseline biomarkers, comorbidities, medications, clinical "
    "scores); environment (geography, SES, healthcare access, HDI, urban/rural, digital "
    "literacy); mediators; identifiers; time; unused; other.\n\n"
    "DATA QUALITY SIGNALS — use them: value_kind='string' with n_distinct≈n_non_null → id; "
    "date/visit/timepoint names → time; binary (n_distinct=2) → flag/binary exposure; high "
    "null_pct → lower confidence; free text → likely unused.\n\n"
    "RULES: every input column gets exactly one entry, preserving sheet+column exactly; "
    "proposed_canonical_id only when role=outcome and a canonical match exists, else null; "
    "confidence 0.9+ unambiguous, 0.6–0.8 plausible, <0.5 uncertain; cite DQ signals in "
    "rationale when they affect the classification."
)


def build_varcheck_user_message(*, product_description: str, sheets: list[dict[str, Any]]) -> str:
    parts = [
        f"PRODUCT / STUDY CONTEXT:\n{product_description or '(not provided)'}",
        "\nCOLUMNS TO CLASSIFY:",
    ]
    for sheet in sheets:
        parts.append(f"\nSheet: {sheet['name']}")
        headers: list[str] = sheet.get("headers", [])
        sample: list[list[Any]] = sheet.get("sample", [])
        for stat in sheet.get("column_stats", []):
            col = stat["column"]
            kind = stat.get("value_kind", "?")
            null_pct = stat.get("null_pct")
            null_str = f"{null_pct * 100:.1f}%" if isinstance(null_pct, (int, float)) else "?"
            n_distinct = stat.get("n_distinct")
            distinct = f" | n_distinct: {n_distinct}" if n_distinct is not None else ""
            rng = ""
            if kind == "numeric" and stat.get("min") is not None:
                rng = f" | range: {stat.get('min')}–{stat.get('max')}"
            sample_vals: list[Any] = []
            if headers and col in headers:
                idx = headers.index(col)
                sample_vals = [r[idx] for r in sample if idx < len(r) and r[idx] not in ("", None)][
                    :5
                ]
            sample_str = f" | sample: {sample_vals}" if sample_vals else ""
            parts.append(f"  - {col} | kind: {kind} | null%: {null_str}{rng}{distinct}{sample_str}")
    return "\n".join(parts)


DATASET_QUESTIONS_TOOL: ToolParam = {
    "name": "answer_dataset_questions",
    "description": "Answer four data-generating-mechanism questions about the uploaded dataset.",
    "input_schema": {
        "type": "object",
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["question_code", "answer", "rationale", "confidence"],
                    "properties": {
                        "question_code": {
                            "type": "string",
                            "enum": [
                                "study_type",
                                "temporal_structure",
                                "exposure_assignment",
                                "control_group",
                            ],
                        },
                        "answer": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"},
                        "evidence_columns": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    },
}

DATASET_QUESTIONS_SYSTEM_PROMPT = (
    "You are the Augura dataset-structure agent. Given a product description and an "
    "uploaded dataset's column inventory with inferred roles, answer four canonical "
    "data-generating-mechanism questions: study_type (Retrospective | Prospective | "
    "Prospective observational | Hybrid); temporal_structure (Cross-sectional | "
    "Longitudinal panel | Repeated cross-section | Event-driven); exposure_assignment "
    "(Randomised | Quasi-randomised | Self-selected/observational | Administratively "
    "assigned); control_group (defined unexposed group | low-engagement comparator | "
    "external comparator | no unexposed group). Use the inventory as evidence (repeated "
    "timepoint columns ⇒ longitudinal panel; no control/arm/group column ⇒ no unexposed "
    "control). Cite specific columns in evidence_columns; offer options the user can pick."
)


def build_dataset_questions_user_message(
    *, product_description: str, matches: list[tuple[str, str, str]]
) -> str:
    inventory = "; ".join(f"{sheet}.{col} ({role})" for sheet, col, role in matches)
    return (
        f"PRODUCT CONTEXT:\n{product_description or '(not provided)'}\n\n"
        f"COLUMN INVENTORY ({len(matches)} columns):\n{inventory}\n\n"
        "Answer all four questions with options the user can choose from if they disagree."
    )
