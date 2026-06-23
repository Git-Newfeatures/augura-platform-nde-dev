"""Deterministic graph assembly from the LLM decision.

Port of the second half of `dag-generator.js` (makeNode/makeEdge, role upgrade,
deduplication, anti-cycle, layout, quality). Pure, no I/O — directly testable.
"""

from dataclasses import dataclass
from typing import cast

from augura_api.modules.causal import schemas
from augura_api.modules.causal.schemas import (
    DagEdge,
    DagFilterResult,
    DagNode,
    Graph,
    MappedConcept,
    MissingVariable,
    Picot,
)
from augura_api.modules.causal.subgraph import ConceptMeta, Relation

_MIN_NODE_CONFIDENCE = 0.40  # cf. dag-generator.js: low-confidence mapped concepts ignored

_ROLES = {"exposure", "outcome", "confounder", "mediator", "effect_modifier", "collider", "other"}
_ROLE_X = {
    "exposure": 200.0,
    "confounder": 30.0,
    "effect_modifier": 30.0,
    "mediator": 350.0,
    "outcome": 520.0,
    "collider": 350.0,
    "other": 200.0,
}


def normalize_role(role: str | None) -> schemas.Role:
    return cast(schemas.Role, role) if role in _ROLES else "other"


def _meta(meta_index: dict[str, ConceptMeta], concept_id: str) -> ConceptMeta:
    return meta_index.get(concept_id, ConceptMeta(concept_id, "unknown", 0))


def make_node(
    concept_id: str,
    role: str,
    source: schemas.NodeSource,
    meta_index: dict[str, ConceptMeta],
    confidence: float | None = None,
) -> DagNode:
    m = _meta(meta_index, concept_id)
    r = normalize_role(role)
    observed = source == "mapping"
    return DagNode(
        id=concept_id,
        label=m.label,
        domain=m.domain,
        layer=m.layer,
        role=r,
        source=source,
        observed=observed,
        adjusted=r == "confounder" and observed,
        confidence=confidence,
    )


def make_edge(rel: Relation, role_from: str, role_to: str, data_backed: bool) -> DagEdge:
    direction = "inhibitory" if rel.polarity == "decreases" else "forward"
    edge_type = (
        "associative"
        if rel.predicate == "associated_with"
        else "temporal"
        if rel.predicate == "precedes"
        else "causal"
    )
    provenance = (
        rel.evidence[0]["citation"] if rel.evidence else rel.mechanism_summary or "Causal ontology"
    )
    return DagEdge.model_validate(
        {
            "id": rel.id,
            "from": rel.subject_concept_id,
            "to": rel.object_concept_id,
            "type": edge_type,
            "strength": rel.default_strength or "moderate",
            "direction": direction,
            "polarity": rel.polarity,
            "temporal_lag": rel.default_temporal_lag or "unknown",
            "predicate": rel.predicate,
            "dag_role_from": role_from or "unknown",
            "dag_role_to": role_to or "unknown",
            "provenance": provenance,
            "notes": rel.mechanism_summary or "",
            "supported_by_data": data_backed,
            "has_qualifier": len(rel.qualifiers) > 0,
            "qualifiers": list(rel.qualifiers),
        }
    )


def _adjacency(edges: list[DagEdge]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.source, []).append(e.to)
    return adj


def has_directed_path(edges: list[DagEdge], start: str, target: str) -> bool:
    if start == target:
        return True
    adj = _adjacency(edges)
    stack = [start]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, []))
    return False


def has_directed_cycle(nodes: list[DagNode], edges: list[DagEdge]) -> bool:
    adj = _adjacency(edges)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(n) for n in adj.get(node_id, [])):
            return True
        visiting.discard(node_id)
        visited.add(node_id)
        return False

    return any(visit(n.id) for n in nodes)


def assign_layout(nodes: list[DagNode]) -> None:
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n.role] = counts.get(n.role, 0) + 1
    index: dict[str, int] = {}
    for n in nodes:
        i = index.get(n.role, 0)
        total = (counts[n.role] - 1) * 80
        n.x = _ROLE_X.get(n.role, 200.0)
        n.y = 100 + i * 80 - total / 2
        index[n.role] = i + 1


def assess_quality(
    nodes: list[DagNode], edges: list[DagEdge], mapped_ids: set[str], missing: int
) -> schemas.Quality:
    has_exp = any(n.role == "exposure" for n in nodes)
    has_out = any(n.role == "outcome" for n in nodes)
    has_conf = any(n.role == "confounder" for n in nodes)
    backed = sum(1 for e in edges if e.supported_by_data)
    rate = backed / len(edges) if edges else 0.0
    coverage = sum(1 for n in nodes if n.id in mapped_ids) / len(nodes) if nodes else 0.0
    issues: list[str] = []
    if not has_exp:
        issues.append("No exposure node identified")
    if not has_out:
        issues.append("No outcome node identified")
    if not has_conf:
        issues.append("No confounders identified — DAG may be underspecified")
    if missing:
        issues.append(f"{missing} expected variable(s) not found in data")
    if rate < 0.5:
        issues.append("Less than 50% of edges are supported by mapped data")
    score = (
        (0.25 if has_exp else 0)
        + (0.25 if has_out else 0)
        + (0.15 if has_conf else 0)
        + rate * 0.20
        + coverage * 0.15
    )
    return schemas.Quality(
        score=round(score, 3),
        label="High" if score >= 0.80 else "Medium" if score >= 0.55 else "Low",
        has_exposure=has_exp,
        has_outcome=has_out,
        has_confounder=has_conf,
        data_backing_rate=round(rate, 3),
        node_data_coverage=round(coverage, 3),
        data_backed_edges=backed,
        total_edges=len(edges),
        issues=issues,
    )


# ── Assembly (port of generateDAG, steps 4→6) ───────────────────────────────


@dataclass(frozen=True)
class AssembledDag:
    nodes: list[DagNode]
    edges: list[DagEdge]
    missing_variables: list[MissingVariable]
    warnings: list[str]
    graph: Graph
    quality: schemas.Quality


def _role_for(result: DagFilterResult, concept_id: str, fallback: str = "other") -> str:
    info = result.node_roles.get(concept_id)
    return normalize_role(info.role if info else fallback)


def _add_or_upgrade(
    nodes: dict[str, DagNode],
    concept_id: str,
    role: str,
    mapped: dict[str, MappedConcept],
    meta_index: dict[str, ConceptMeta],
) -> None:
    if concept_id not in nodes:
        mc = mapped.get(concept_id)
        source: schemas.NodeSource = "mapping" if mc else "ontology_inferred"
        nodes[concept_id] = make_node(
            concept_id, role, source, meta_index, mc.confidence if mc else None
        )
        return
    existing = nodes[concept_id]
    if existing.role == "other" and role != "other":
        existing.role = normalize_role(role)
        existing.adjusted = existing.role == "confounder" and existing.observed


def _try_add_edge(edges: list[DagEdge], edge: DagEdge, warnings: list[str]) -> None:
    if any(e.source == edge.source and e.to == edge.to for e in edges):
        warnings.append(f"Duplicate relation skipped: {edge.source} → {edge.to}")
    elif has_directed_path(edges, edge.to, edge.source):
        warnings.append(f"Cycle-forming relation skipped: {edge.source} → {edge.to}")
    else:
        edges.append(edge)


def _add_selected(
    result: DagFilterResult,
    by_id: dict[str, Relation],
    mapped_ids: set[str],
    mapped: dict[str, MappedConcept],
    meta_index: dict[str, ConceptMeta],
    nodes: dict[str, DagNode],
    edges: list[DagEdge],
    warnings: list[str],
) -> None:
    for sel in result.selected_relations:
        rel = by_id.get(sel.relation_id)
        if rel is None:
            warnings.append(f"LLM selected unknown relation ID: {sel.relation_id}")
            continue
        role_s = _role_for(result, rel.subject_concept_id, sel.dag_role_subject)
        role_o = _role_for(result, rel.object_concept_id, sel.dag_role_object)
        _add_or_upgrade(nodes, rel.subject_concept_id, role_s, mapped, meta_index)
        _add_or_upgrade(nodes, rel.object_concept_id, role_o, mapped, meta_index)
        data_backed = rel.subject_concept_id in mapped_ids and rel.object_concept_id in mapped_ids
        _try_add_edge(edges, make_edge(rel, role_s, role_o, data_backed), warnings)


def _add_role_only_nodes(
    result: DagFilterResult,
    mapped: dict[str, MappedConcept],
    mapped_ids: set[str],
    meta_index: dict[str, ConceptMeta],
    nodes: dict[str, DagNode],
) -> None:
    for mc in mapped.values():
        if mc.concept_id in nodes or (mc.confidence or 0) < _MIN_NODE_CONFIDENCE:
            continue
        role = _role_for(result, mc.concept_id)
        if role != "other":
            nodes[mc.concept_id] = make_node(
                mc.concept_id, role, "mapping", meta_index, mc.confidence
            )
    for concept_id in result.node_roles:
        role = _role_for(result, concept_id)
        if concept_id in nodes or role == "other":
            continue
        source: schemas.NodeSource = "mapping" if concept_id in mapped_ids else "ontology_inferred"
        conf = mapped[concept_id].confidence if concept_id in mapped else None
        nodes[concept_id] = make_node(concept_id, role, source, meta_index, conf)


def _picot_fallback(
    picot: Picot | None,
    mapped: dict[str, MappedConcept],
    nodes: dict[str, DagNode],
    meta_index: dict[str, ConceptMeta],
) -> None:
    outcome_ids: set[str] = (
        {o.concept_id for o in picot.outcomes if o.concept_id} if picot else set()
    )
    for mc in mapped.values():
        if mc.concept_id in nodes or mc.concept_id not in outcome_ids:
            continue
        if (mc.confidence or 0) >= _MIN_NODE_CONFIDENCE:
            nodes[mc.concept_id] = make_node(
                mc.concept_id, "outcome", "mapping", meta_index, mc.confidence
            )
    iv = picot.intervention_concept_id if picot else None
    if iv and iv not in nodes:
        mc = mapped.get(iv)
        if mc and (mc.confidence or 0) >= _MIN_NODE_CONFIDENCE:
            nodes[iv] = make_node(iv, "exposure", "mapping", meta_index, mc.confidence)


def _materialize_proposed(
    result: DagFilterResult,
    meta_index: dict[str, ConceptMeta],
    nodes: dict[str, DagNode],
    edges: list[DagEdge],
) -> None:
    proposed_meta = {
        c.provisional_id: ConceptMeta(c.label, c.domain, c.layer) for c in result.proposed_concepts
    }
    meta = {**meta_index, **proposed_meta}
    for prop in result.proposed_relations:
        role_s = _role_for(result, prop.subject_concept_id)
        role_o = _role_for(result, prop.object_concept_id)
        for cid, role in ((prop.subject_concept_id, role_s), (prop.object_concept_id, role_o)):
            if cid not in nodes:
                nodes[cid] = make_node(cid, role, "llm_proposed", meta)
        edge = DagEdge.model_validate(
            {
                "id": f"proposed_{prop.subject_concept_id}_{prop.object_concept_id}",
                "from": prop.subject_concept_id,
                "to": prop.object_concept_id,
                "type": "causal",
                "strength": prop.default_strength or "moderate",
                "direction": "inhibitory" if prop.polarity == "decreases" else "forward",
                "polarity": prop.polarity,
                "temporal_lag": "unknown",
                "predicate": prop.predicate,
                "dag_role_from": role_s,
                "dag_role_to": role_o,
                "provenance": prop.mechanism_summary or "LLM proposed",
                "notes": prop.mechanism_summary or "",
                "supported_by_data": False,
                "has_qualifier": False,
                "qualifiers": [],
            }
        )
        duplicate = any(e.source == edge.source and e.to == edge.to for e in edges)
        if not duplicate and not has_directed_path(edges, edge.to, edge.source):
            edges.append(edge)


def _missing_vars(
    result: DagFilterResult, meta_index: dict[str, ConceptMeta]
) -> list[MissingVariable]:
    return [
        MissingVariable(concept_id=cid, label=_meta(meta_index, cid).label)
        for cid in result.missing_variables
    ]


def assemble_dag(
    result: DagFilterResult,
    candidates: list[Relation],
    mapped_concepts: list[MappedConcept],
    picot: Picot | None,
    meta_index: dict[str, ConceptMeta],
) -> AssembledDag:
    by_id = {r.id: r for r in candidates}
    mapped = {m.concept_id: m for m in mapped_concepts}
    mapped_ids = set(mapped)
    nodes: dict[str, DagNode] = {}
    edges: list[DagEdge] = []
    warnings: list[str] = []
    if not candidates:
        warnings.append("No reviewed causal ontology relations were found for the mapped concepts")
    _add_selected(result, by_id, mapped_ids, mapped, meta_index, nodes, edges, warnings)
    _add_role_only_nodes(result, mapped, mapped_ids, meta_index, nodes)
    _picot_fallback(picot, mapped, nodes, meta_index)
    _materialize_proposed(result, meta_index, nodes, edges)
    missing = _missing_vars(result, meta_index)
    if not nodes:
        warnings.append("LLM selected no relations — DAG is empty")
    node_list = list(nodes.values())
    assign_layout(node_list)
    if has_directed_cycle(node_list, edges):
        warnings.append("DAG validation failed: selected relations still contain a directed cycle")
    graph = Graph(
        exposure_ids=[n.id for n in node_list if n.role == "exposure"],
        outcome_ids=[n.id for n in node_list if n.role == "outcome"],
        adjusted_ids=[n.id for n in node_list if n.adjusted],
        latent_ids=[n.id for n in node_list if not n.observed],
    )
    quality = assess_quality(node_list, edges, mapped_ids, len(missing))
    return AssembledDag(node_list, edges, missing, warnings, graph, quality)
