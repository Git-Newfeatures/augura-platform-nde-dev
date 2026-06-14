"""Outil forcé + prompts de l'agent DAG (port de lucis-dashboard/api/dag.js)."""

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
