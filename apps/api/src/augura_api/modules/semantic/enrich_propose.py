"""Orchestration LLM pour la proposition d'enrichissement sémantique (B4).

Port de lucis-dashboard/api/enrich-propose.js :
  - PROPOSAL_TOOL : schéma d'entrée outil (enums depuis vocab.py).
  - build_system_prompt : prompt système.
  - propose : orchestration en 4 batches (selectedConcepts / concepts manquants /
    lacunes de chemin / bootstrap bootstrap), préchecks, fusion, tampon.

L'I/O DB et SSE sont remplacés par :
  - `bundle` (données sémantiques brutes passées en argument)
  - `on_progress` (callback async de reporting de progression 0..1)

Les helpers purs viennent de `enrichment.py` ; les enums de `vocab.py`.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from anthropic.types import ToolParam
from pydantic import BaseModel

from augura_api.core.llm.runtime import LLMClient, run_structured_agent
from augura_api.modules.semantic import enrichment, vocab

# ── Modèle de sortie LLM (permissif — validation réelle dans apply_prechecks) ─


class ProposalBatch(BaseModel):
    """Batch de propositions retourné par le LLM.

    Permissif (``list[dict]``) : la validation structurelle fine se fait dans
    ``apply_prechecks``, pas à la frontière LLM, conformément au JS source.
    """

    taxonomy_concepts: list[dict[str, Any]] = []
    taxonomy_synonyms: list[dict[str, Any]] = []
    taxonomy_standard_codes: list[dict[str, Any]] = []
    ontology_relations: list[dict[str, Any]] = []
    ontology_relation_evidence: list[dict[str, Any]] = []
    ontology_relation_qualifiers: list[dict[str, Any]] = []


# ── Schéma de l'outil LLM (ce que l'IA voit) ──────────────────────────────────

PROPOSAL_TOOL: ToolParam = {
    "name": "propose_enrichment_batch",
    "description": (
        "Propose taxonomy concepts, synonyms, standard codes, causal relations, "
        "evidence, and qualifiers to enrich the clinical ontology."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "taxonomy_concepts",
            "taxonomy_synonyms",
            "taxonomy_standard_codes",
            "ontology_relations",
            "ontology_relation_evidence",
            "ontology_relation_qualifiers",
        ],
        "properties": {
            "taxonomy_concepts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "local_concept_id",
                        "concept_name",
                        "layer",
                        "augura_domain",
                        "design_rationale",
                    ],
                    "properties": {
                        "local_concept_id": {
                            "type": "string",
                            "description": "Use format ENRC_{date}_{NNN}",
                        },
                        "concept_name": {"type": "string"},
                        "layer": {"type": "integer", "enum": [1, 2]},
                        "augura_domain": {
                            "type": "string",
                            "enum": vocab.AUGURA_DOMAINS,
                        },
                        "value_type": {
                            "type": "string",
                            "enum": ["numeric", "categorical", "text", "boolean", "date"],
                        },
                        "canonical_unit": {"type": "string"},
                        "design_rationale": {
                            "type": "string",
                            "description": "For layer=2: why no L1 standard concept is adequate",
                        },
                    },
                },
            },
            "taxonomy_synonyms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "local_concept_id",
                        "synonym",
                        "synonym_type",
                        "source",
                    ],
                    "properties": {
                        "local_concept_id": {"type": "string"},
                        "synonym": {"type": "string"},
                        "synonym_type": {
                            "type": "string",
                            "enum": ["preferred", "acceptable", "abbreviation", "brand_name"],
                        },
                        "source": {"type": "string"},
                    },
                },
            },
            "taxonomy_standard_codes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "local_concept_id",
                        "vocabulary_id",
                        "concept_code",
                    ],
                    "properties": {
                        "local_concept_id": {"type": "string"},
                        "vocabulary_id": {
                            "type": "string",
                            "enum": vocab.STANDARD_CODE_VOCABULARIES,
                        },
                        "concept_code": {"type": "string"},
                        "standard_concept_name": {"type": "string"},
                    },
                },
            },
            "ontology_relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "relation_id",
                        "subject_concept_id",
                        "predicate",
                        "object_concept_id",
                        "polarity",
                        "default_strength",
                        "default_temporal_lag",
                        "mechanism_summary",
                    ],
                    "properties": {
                        "relation_id": {
                            "type": "string",
                            "description": "Use format ENRR_{date}_{NNN}",
                        },
                        "subject_concept_id": {"type": "string"},
                        "predicate": {
                            "type": "string",
                            "description": "Must be a valid causal_predicates.predicate_id",
                        },
                        "object_concept_id": {"type": "string"},
                        "polarity": {"type": "string", "enum": vocab.POLARITY},
                        "default_strength": {
                            "type": "string",
                            "enum": ["strong", "moderate", "weak", "unknown"],
                        },
                        "default_temporal_lag": {"type": "string"},
                        "mechanism_summary": {
                            "type": "string",
                            "description": "One sentence: the biological or clinical mechanism",
                        },
                    },
                },
            },
            "ontology_relation_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "evidence_id",
                        "relation_id",
                        "source_type",
                        "citation_or_url",
                        "evidence_summary",
                        "population_notes",
                        "evidence_strength",
                    ],
                    "properties": {
                        "evidence_id": {
                            "type": "string",
                            "description": "Use format ENRV_{date}_{NNN}",
                        },
                        "relation_id": {"type": "string"},
                        "source_type": {
                            "type": "string",
                            "enum": [
                                "established_physiology",
                                "rct",
                                "systematic_review",
                                "observational_cohort",
                                "case_series",
                                "expert_consensus",
                                "guideline",
                            ],
                        },
                        "citation_or_url": {"type": "string"},
                        "evidence_summary": {"type": "string"},
                        "population_notes": {"type": "string"},
                        "evidence_strength": {
                            "type": "string",
                            "enum": ["established", "strong", "moderate", "weak"],
                        },
                    },
                },
            },
            "ontology_relation_qualifiers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "qualifier_id",
                        "relation_id",
                        "qualifier_type",
                        "qualifier_value",
                        "qualifier_effect",
                        "is_hard_constraint",
                        "notes",
                    ],
                    "properties": {
                        "qualifier_id": {
                            "type": "string",
                            "description": "Use format ENRQ_{date}_{NNN}",
                        },
                        "relation_id": {"type": "string"},
                        "qualifier_type": {
                            "type": "string",
                            "enum": vocab.QUALIFIER_TYPES,
                        },
                        "qualifier_value": {"type": "string"},
                        "qualifier_effect": {
                            "type": "string",
                            "enum": vocab.QUALIFIER_EFFECTS,
                        },
                        "is_hard_constraint": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    },
}


# ── Prompt système ─────────────────────────────────────────────────────────────


def build_system_prompt(predicate_list: str, existing_concepts_sample: str) -> str:
    """Construit le prompt système pour le LLM.

    Port de ``buildSystemPrompt()`` dans enrich-propose.js.
    """
    return (
        "You are a clinical knowledge engineer building a causal ontology for MedTech"
        " real-world evidence studies.\n\n"
        "Available causal predicates (you MUST use only these predicate IDs):\n"
        f"{predicate_list}\n\n"
        "Sample of existing taxonomy concepts (for reference when proposing relations):\n"
        f"{existing_concepts_sample}\n\n"
        "LAYER ASSIGNMENT RULES (strictly enforced — violations cause concept rejection):\n"
        "- layer=1: ONLY if you can supply a valid standard code for that concept."
        " You MUST include the code in taxonomy_standard_codes."
        " A layer=1 concept without a code is REJECTED.\n"
        "- layer=2: when no standard code exists. You MUST include design_rationale"
        ' explaining why (e.g. "brand-specific device model —'
        ' no individual SNOMED code distinguishes this variant").\n'
        "- When unsure whether a code exists: assign layer=2."
        " A correct L2 is always better than a rejected L1.\n\n"
        "STANDARD CODE LOOKUP ORDER (use your medical knowledge):\n"
        "1. Drug / biologic / device therapy → RxNorm (rxcui) first, then SNOMED\n"
        '2. Lab measurement / observation → LOINC (6-digit code, e.g. "4548-4" for HbA1c)\n'
        "3. Disease / condition / finding → SNOMED CT (numeric concept ID)\n"
        "4. Procedure / intervention → SNOMED CT\n"
        "5. Device category (not brand-specific) → SNOMED CT\n"
        "6. If OMOP standard concept applies → OMOP concept_id as fallback\n"
        "7. Diagnosis code → ICD10CM as last resort\n\n"
        "OTHER RULES:\n"
        "- Every relation must have at least one evidence row\n"
        "- For established physiology (undisputed mechanisms), use source_type"
        ' "established_physiology" with citation_or_url "established physiology"\n'
        "- Prefer mediator chains over direct relations when the mechanism is indirect\n"
        "- CASCADE RULE (§10.3): every new concept you introduce MUST be the subject or"
        " object of at least one relation in the SAME proposal batch. Never propose a"
        " dangling concept with no path to the rest of the ontology. Where the link to an"
        " existing concept is indirect, introduce the intermediate mediator concept(s)"
        " needed to complete the chain.\n"
        "- PREFERRED SYNONYM (§10.3): every new concept MUST include at least one"
        " taxonomy_synonyms row whose synonym equals the concept's name with synonym_type"
        ' "preferred". Add common abbreviations/acronyms and spelling variants as'
        ' additional rows (synonym_type "abbreviation" or "acceptable") so future PICOT'
        " questions match the concept.\n"
        "- Concept IDs must use format ENRC_YYYYMMDD_NNN (e.g. ENRC_20260613_001)\n"
        "- Relation IDs: ENRR_YYYYMMDD_NNN, Evidence IDs: ENRV_YYYYMMDD_NNN,"
        " Qualifier IDs: ENRQ_YYYYMMDD_NNN\n"
        "- subject_concept_id and object_concept_id must ALWAYS be concept IDs"
        " (ENRC_ or existing L1_/L2_ prefixes) — NEVER relation IDs"
    )


# ── Helpers internes ──────────────────────────────────────────────────────────


def _extract_n(concept_id: str, prefix: str, today: str) -> int:
    """Extrait le numéro séquentiel d'un identifiant du jour.

    Ex. : ``_extract_n("ENRC_20260619_007", "ENRC", "20260619")`` → ``7``.
    Retourne 0 si l'ID ne correspond pas au pattern du jour.
    Port fidèle de la lambda JS ``extractN`` dans enrich-propose.js.
    """
    p = f"{prefix}_{today}_"
    if not concept_id or not concept_id.startswith(p):
        return 0
    tail = concept_id[len(p) :]
    try:
        return int(tail)
    except ValueError:
        return 0


def _seed_id_counters(
    existing_concept_ids: set[str],
    existing_rel_ids: list[str],
    today: str,
) -> dict[str, int]:
    """Initialise les compteurs d'IDs au-delà des IDs existants du jour.

    Évite les collisions avec des IDs déjà appliqués à la DB ce même jour.
    Port de la logique ``maxConceptN / maxRelationN`` dans enrich-propose.js.
    """
    max_concept = max(
        (_extract_n(cid, "ENRC", today) for cid in existing_concept_ids),
        default=0,
    )
    max_rel = max(
        (_extract_n(rid, "ENRR", today) for rid in existing_rel_ids),
        default=0,
    )
    return {"concept": max_concept, "relation": max_rel, "evidence": 0, "qualifier": 0}


async def _call_llm(
    client: LLMClient,
    *,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Appelle le LLM et retourne un batch normalisé (dict à 6 clés)."""
    result = await run_structured_agent(
        client,
        model=model,
        system=system,
        tool=PROPOSAL_TOOL,
        messages=[{"role": "user", "content": user_message}],
        output_model=ProposalBatch,
        max_tokens=max_tokens,
    )
    return result.output.model_dump()


# ── Point d'entrée public ──────────────────────────────────────────────────────


async def propose(
    *,
    client: LLMClient,
    model: str,
    bundle: dict[str, Any],
    questions: list[dict[str, Any]] | None,
    selected_concepts: list[dict[str, Any]] | None,
    on_progress: Callable[[float, str], Awaitable[None]],
) -> dict[str, Any]:
    """Orchestre la proposition d'enrichissement sémantique.

    Renvoie un dict ``{proposals, coverage_summary, precheck_log, summary}``.

    - ``proposals`` : dict à 6 clés (tables) après ``stamp_rows``.
    - ``coverage_summary`` : résumé de couverture (None pour le raccourci
      selectedConcepts, conformément à la spec).
    - ``precheck_log`` : liste de messages de préchecks.
    - ``summary`` : comptage par table.

    Port de l'handler principal de enrich-propose.js.
    """
    today = datetime.now(UTC).strftime("%Y%m%d")

    # ── Construction des index sémantiques ────────────────────────────────────
    sem = enrichment.build_semantic_data(bundle)

    existing_concept_ids: set[str] = {c["id"] for c in sem.concept_index}
    existing_relation_keys: set[str] = set()
    existing_rel_ids: list[str] = []
    for rel in sem.ontology.relations:
        key = (
            f"{rel['subject_concept_id']}|{rel['predicate']}"
            f"|{rel['object_concept_id']}|{rel['polarity']}"
        )
        existing_relation_keys.add(key)
        existing_rel_ids.append(rel["relation_id"])

    valid_predicate_ids: set[str] = set(sem.ontology.predicates.keys())

    predicate_list = "\n".join(
        f"{p['predicate_id']}: {p.get('description', '')}" for p in sem.ontology.predicates.values()
    )
    existing_concepts_sample = "\n".join(
        f"{c['id']}: {c['label']} [{c['domain']}]" for c in sem.concept_index[:80]
    )
    system = build_system_prompt(predicate_list, existing_concepts_sample)

    all_proposals: dict[str, Any] = {
        "taxonomy_concepts": [],
        "taxonomy_synonyms": [],
        "taxonomy_standard_codes": [],
        "ontology_relations": [],
        "ontology_relation_evidence": [],
        "ontology_relation_qualifiers": [],
    }
    id_counters = _seed_id_counters(existing_concept_ids, existing_rel_ids, today)
    precheck_log: list[str] = []

    # ══════════════════════════════════════════════════════════════════════════
    # Raccourci selectedConcepts
    # ══════════════════════════════════════════════════════════════════════════
    if selected_concepts and len(selected_concepts) > 0:
        await on_progress(0.1, "Chargement du store sémantique…")
        await on_progress(
            0.2,
            f"Chargé : {len(sem.concept_index)} concepts, {len(sem.ontology.relations)} relations",
        )

        iv_domains = {"therapeutics", "device", "procedure"}
        out_domains = {"measurement", "outcome", "biomarker", "condition"}
        iv_concepts = [c for c in selected_concepts if c.get("domain") in iv_domains]
        out_concepts = [c for c in selected_concepts if c.get("domain") in out_domains]

        effective_iv = iv_concepts if iv_concepts else selected_concepts
        effective_out = out_concepts if out_concepts else selected_concepts

        iv_lines = "\n".join(
            f"{c['id']}: {c['label']} [{c.get('domain', '')}]" for c in effective_iv
        )
        out_lines = "\n".join(
            f"{c['id']}: {c['label']} [{c.get('domain', '')}]" for c in effective_out
        )

        await on_progress(
            0.5,
            f"Proposition de relations causales pour {len(selected_concepts)}"
            " concept(s) sélectionné(s)…",
        )

        try:
            batch = await _call_llm(
                client,
                model=model,
                system=system,
                user_message=(
                    "These concepts already exist in the taxonomy with the EXACT IDs shown. "
                    "You MUST use these IDs verbatim as subject_concept_id or object_concept_id "
                    "— never invent alternative IDs for them.\n\n"
                    f"Intervention / exposure side:\n{iv_lines}\n\n"
                    f"Outcome side:\n{out_lines}\n\n"
                    "Requirements:\n"
                    "1. EVERY concept listed above must appear as the subject or object of"
                    " at least one relation — do not skip any.\n"
                    "2. Propose the causal chain from each intervention concept toward each"
                    " outcome concept.\n"
                    "3. Where the pathway is indirect, you may introduce new intermediate"
                    " mediator concepts in taxonomy_concepts "
                    "(e.g. a physiological process or biomarker between intervention and"
                    " outcome). Assign standard codes and layer per system prompt rules.\n"
                    "4. For new mediator concepts use ENRC_{today}_{NNN} placeholder IDs"
                    " — they will be reassigned automatically.\n"
                    "5. Provide at least one evidence row per relation."
                ),
                max_tokens=8192,
            )
        except Exception as exc:
            precheck_log.append(f"  ERROR relation proposal: {exc}")
            await on_progress(0.9, f"⚠ Proposition de relations échouée : {exc}")
            batch = ProposalBatch().model_dump()

        enrichment.reassign_ids(batch, id_counters, today)
        enrichment.apply_prechecks(
            batch,
            existing_concept_ids=existing_concept_ids,
            existing_relation_keys=existing_relation_keys,
            valid_predicate_ids=valid_predicate_ids,
            log=precheck_log,
            id_counters=id_counters,
            today=today,
        )
        for msg in precheck_log:
            await on_progress(0.95, msg)
        enrichment.merge_into(all_proposals, batch)

        enrichment.stamp_rows(all_proposals, "pending")
        await on_progress(1.0, "Terminé.")

        summary = {k: len(v) for k, v in all_proposals.items()}
        return {
            "proposals": all_proposals,
            "coverage_summary": None,
            "precheck_log": precheck_log,
            "summary": summary,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Flux complet : Phase 2 (couverture) + Phase 3 (batches de propositions)
    # ══════════════════════════════════════════════════════════════════════════
    if not questions:
        raise ValueError("questions ou selected_concepts est obligatoire")

    await on_progress(0.0, "Chargement du store sémantique…")
    await on_progress(
        0.05,
        f"Chargé : {len(sem.concept_index)} concepts, {len(sem.ontology.relations)} relations",
    )

    # Phase 2 — analyse de couverture
    await on_progress(0.1, f"Analyse de couverture pour {len(questions)} questions PICOT…")
    coverage = enrichment.analyze_coverage(
        questions, sem.concept_index, sem.syn_lookup, sem.ontology
    )
    cov_summary = coverage["summary"]
    await on_progress(
        0.15,
        (
            f"Couverture : {cov_summary['pairs_covered_pct']}% — "
            f"{cov_summary['missing_concept_tokens']} tokens manquants, "
            f"{len(coverage['path_gaps'])} lacunes de chemin"
        ),
    )

    missing_concepts: list[dict[str, Any]] = coverage["missing_concepts"]
    path_gaps: list[dict[str, Any]] = coverage["path_gaps"]

    # Estimations de fraction pour la progression
    # Batch 1 : 0.15 → 0.50 ; Batch 2 : 0.50 → 0.75 ; Batch 3 : 0.75 → 0.95
    b1_groups = enrichment.group_missing_concepts(missing_concepts) if missing_concepts else []
    n_b1 = math.ceil(len(b1_groups) / 20) if b1_groups else 0
    n_b2 = math.ceil(len(path_gaps) / 5) if path_gaps else 0

    batch_index = 0  # numéro global de sous-batch traité

    def _progress_frac() -> float:
        """Fraction 0..1 estimée à partir du nombre de batches traités."""
        total = n_b1 + n_b2 + (1 if missing_concepts else 0)
        if total == 0:
            return 0.5
        done = min(batch_index, total)
        return 0.15 + (done / total) * 0.80

    # ── Batch 1 : concepts manquants ──────────────────────────────────────────
    if missing_concepts:
        total_b1 = n_b1 or 1
        await on_progress(
            0.15,
            f"Proposition de concepts pour {len(missing_concepts)} tokens non couverts "
            f"({total_b1} batch{'es' if total_b1 != 1 else ''})…",
        )

        for i in range(0, len(b1_groups), 20):
            batch_groups = b1_groups[i : i + 20]
            batch_num = i // 20 + 1
            token_lines = "\n".join(
                "- "
                + " | ".join(
                    f'"{m["token"]}" ({m["picot_field"]}, in: {", ".join(m["appeared_in"][:2])})'
                    for m in group
                )
                for group in batch_groups
            )

            await on_progress(_progress_frac(), f"  Batch concepts {batch_num}/{total_b1}…")

            try:
                batch = await _call_llm(
                    client,
                    model=model,
                    system=system,
                    user_message=(
                        "Propose taxonomy concepts for these unmatched clinical tokens"
                        " from PICOT questions. "
                        "Each line is a group of related tokens that should map to ONE"
                        " concept:\n\n"
                        f"{token_lines}\n\n"
                        "For each group, create exactly one concept. Include synonyms"
                        " covering all token variants. "
                        "If a standard code exists: assign layer=1 AND include the code. "
                        "If no standard code: assign layer=2 AND explain in design_rationale."
                    ),
                )
            except Exception as exc:
                precheck_log.append(f"  ERROR concept batch {batch_num}: {exc}")
                await on_progress(
                    _progress_frac(), f"  ⚠ Batch concepts {batch_num} échoué : {exc}"
                )
                batch_index += 1
                continue

            enrichment.reassign_ids(batch, id_counters, today)

            # Injection du token original comme synonyme (garantit le match futur)
            for gi, group in enumerate(batch_groups):
                concept = (
                    batch["taxonomy_concepts"][gi] if gi < len(batch["taxonomy_concepts"]) else None
                )
                if not concept:
                    continue
                for missing in group:
                    norm_token = enrichment.normalize(missing["token"])
                    already = any(
                        s.get("local_concept_id") == concept["local_concept_id"]
                        and enrichment.normalize(s.get("synonym", "")) == norm_token
                        for s in batch["taxonomy_synonyms"]
                    )
                    if not already:
                        batch["taxonomy_synonyms"].append(
                            {
                                "local_concept_id": concept["local_concept_id"],
                                "synonym": missing["token"],
                                "synonym_type": "acceptable",
                                "source": "auto_phrase_link",
                            }
                        )

            # Préchecks : on ne passe que concepts/synonymes/codes (pas les relations)
            checked: dict[str, Any] = {
                **batch,
                "ontology_relations": [],
                "ontology_relation_evidence": [],
                "ontology_relation_qualifiers": [],
            }
            prev_len = len(precheck_log)
            enrichment.apply_prechecks(
                checked,
                existing_concept_ids=existing_concept_ids,
                existing_relation_keys=existing_relation_keys,
                valid_predicate_ids=valid_predicate_ids,
                log=precheck_log,
                id_counters=id_counters,
                today=today,
            )
            for msg in precheck_log[prev_len:]:
                await on_progress(_progress_frac(), msg)

            enrichment.merge_into(all_proposals, checked)
            for c in checked["taxonomy_concepts"]:
                existing_concept_ids.add(c["local_concept_id"])

            await on_progress(
                _progress_frac(),
                f"  Concepts jusqu'ici : {len(all_proposals['taxonomy_concepts'])}",
            )
            batch_index += 1

    # ── Batch 2 : lacunes de chemin ───────────────────────────────────────────
    if path_gaps:
        batch_size = 5
        total_b2 = n_b2 or 1
        await on_progress(
            _progress_frac(),
            f"Proposition de relations pour {len(path_gaps)} lacunes de chemin "
            f"({total_b2} batch{'es' if total_b2 != 1 else ''})…",
        )

        for i in range(0, len(path_gaps), batch_size):
            batch_gaps = path_gaps[i : i + batch_size]
            batch_num = i // batch_size + 1

            gap_lines = "\n\n".join(
                (
                    f"Gap for question {g['question_id']}"
                    f" ({g.get('therapeutic_area', 'general')}):\n"
                    f"  Intervention: {', '.join(g['intervention_labels'])} "
                    f"[{', '.join(g['intervention_concept_ids'])}]\n"
                    f"  Outcome:      {', '.join(g['outcome_labels'])} "
                    f"[{', '.join(g['outcome_concept_ids'])}]"
                    + (
                        f"\n  Nearest forward hop: concept "
                        f"{g['nearest_forward_hop']['concept_id']} at "
                        f"{g['nearest_forward_hop']['hops_from_intervention']} hops"
                        if g.get("nearest_forward_hop")
                        else ""
                    )
                )
                for g in batch_gaps
            )

            new_concepts_ctx = ""
            if all_proposals["taxonomy_concepts"]:
                lines = "\n".join(
                    f"{c['local_concept_id']}: {c.get('concept_name', '')}"
                    for c in all_proposals["taxonomy_concepts"]
                )
                new_concepts_ctx = f"\nNewly proposed concepts available:\n{lines}"

            await on_progress(_progress_frac(), f"  Batch relations {batch_num}/{total_b2}…")

            try:
                batch = await _call_llm(
                    client,
                    model=model,
                    system=system,
                    user_message=(
                        "Propose causal ontology relations to fill these coverage gaps. "
                        "For each gap, propose the shortest plausible causal chain."
                        f"{new_concepts_ctx}\n\n{gap_lines}\n\n"
                        "Provide at least one evidence row per relation. "
                        "Use existing concept IDs or newly proposed IDs (ENRC_ format)."
                    ),
                    max_tokens=8192,
                )
            except Exception as exc:
                precheck_log.append(f"  ERROR gap batch {batch_num}: {exc}")
                await on_progress(
                    _progress_frac(), f"  ⚠ Batch relations {batch_num} échoué : {exc}"
                )
                batch_index += 1
                continue

            enrichment.reassign_ids(batch, id_counters, today)
            prev_len = len(precheck_log)
            enrichment.apply_prechecks(
                batch,
                existing_concept_ids=existing_concept_ids,
                existing_relation_keys=existing_relation_keys,
                valid_predicate_ids=valid_predicate_ids,
                log=precheck_log,
                id_counters=id_counters,
                today=today,
            )
            for msg in precheck_log[prev_len:]:
                await on_progress(_progress_frac(), msg)

            enrichment.merge_into(all_proposals, batch)
            for c in batch["taxonomy_concepts"]:
                existing_concept_ids.add(c["local_concept_id"])

            await on_progress(
                _progress_frac(),
                f"  Relations jusqu'ici : {len(all_proposals['ontology_relations'])}",
            )
            batch_index += 1

    # ── Batch 3 : bootstrap des relations pour les nouveaux concepts ──────────
    if all_proposals["taxonomy_concepts"]:
        # IDs côté intervention (phrases PICOT matchées + nouveaux concepts IV)
        intervention_concept_ids: list[str] = []
        for q in questions:
            iv_phrases = list(q.get("picot", {}).get("intervention") or []) + list(
                q.get("picot", {}).get("comparator") or []
            )
            iv_matched, _ = enrichment.match_tokens(iv_phrases, sem.syn_lookup, sem.concept_index)
            for ids in iv_matched.values():
                intervention_concept_ids.extend(ids)

        for c in all_proposals["taxonomy_concepts"]:
            if c.get("augura_domain") in {"therapeutics", "device", "procedure"}:
                intervention_concept_ids.append(c["local_concept_id"])

        # IDs côté outcome
        outcome_concept_ids: list[str] = []
        for q in questions:
            out_phrases = list(q.get("picot", {}).get("outcome") or [])
            out_matched, _ = enrichment.match_tokens(out_phrases, sem.syn_lookup, sem.concept_index)
            for ids in out_matched.values():
                outcome_concept_ids.extend(ids)

        for c in all_proposals["taxonomy_concepts"]:
            if c.get("augura_domain") in {"measurement", "outcome", "biomarker", "condition"}:
                outcome_concept_ids.append(c["local_concept_id"])

        unique_iv_ids = list(dict.fromkeys(intervention_concept_ids))
        unique_out_ids = list(dict.fromkeys(outcome_concept_ids))

        if unique_iv_ids and unique_out_ids:
            new_concept_ids_set = {
                c["local_concept_id"] for c in all_proposals["taxonomy_concepts"]
            }
            existing_by_id = {c["id"]: c["label"] for c in sem.concept_index}

            def _label_of(cid: str) -> str:
                if cid in existing_by_id:
                    return existing_by_id[cid]
                found = next(
                    (
                        c.get("concept_name", cid)
                        for c in all_proposals["taxonomy_concepts"]
                        if c["local_concept_id"] == cid
                    ),
                    cid,
                )
                return found

            iv_lines = "\n".join(
                f"{cid}: {_label_of(cid)}{' [NEW]' if cid in new_concept_ids_set else ''}"
                for cid in unique_iv_ids
            )
            out_lines = "\n".join(
                f"{cid}: {_label_of(cid)}{' [NEW]' if cid in new_concept_ids_set else ''}"
                for cid in unique_out_ids
            )

            await on_progress(
                0.80,
                f"Proposition de relations bootstrap pour"
                f" {len(all_proposals['taxonomy_concepts'])} nouveau(x) concept(s)…",
            )

            try:
                batch = await _call_llm(
                    client,
                    model=model,
                    system=system,
                    user_message=(
                        "The following concepts were just added to the ontology and have"
                        " no causal relations yet "
                        "(marked [NEW]). Propose the causal relation chain from each"
                        " intervention concept to each "
                        "outcome concept. Include mediator concepts where the mechanism"
                        " is indirect.\n\n"
                        f"Intervention / exposure concepts:\n{iv_lines}\n\n"
                        f"Outcome concepts:\n{out_lines}\n\n"
                        "For each [NEW] concept, propose at least one relation. "
                        "Use exact concept IDs as subject/object."
                        " Provide at least one evidence row per relation."
                    ),
                    max_tokens=8192,
                )
            except Exception as exc:
                precheck_log.append(f"  ERROR bootstrap batch: {exc}")
                await on_progress(0.85, f"  ⚠ Batch bootstrap échoué : {exc}")
                batch = ProposalBatch().model_dump()

            enrichment.reassign_ids(batch, id_counters, today)
            prev_len = len(precheck_log)
            enrichment.apply_prechecks(
                batch,
                existing_concept_ids=existing_concept_ids,
                existing_relation_keys=existing_relation_keys,
                valid_predicate_ids=valid_predicate_ids,
                log=precheck_log,
                id_counters=id_counters,
                today=today,
            )
            for msg in precheck_log[prev_len:]:
                await on_progress(0.85, msg)
            enrichment.merge_into(all_proposals, batch)

            await on_progress(
                0.90,
                f"  Relations bootstrap : {len(all_proposals['ontology_relations'])} au total",
            )

    # ── Finalisation ──────────────────────────────────────────────────────────
    enrichment.stamp_rows(all_proposals, "pending")
    await on_progress(1.0, "Terminé.")

    summary = {k: len(v) for k, v in all_proposals.items()}
    return {
        "proposals": all_proposals,
        "coverage_summary": cov_summary,
        "precheck_log": precheck_log,
        "summary": summary,
    }
