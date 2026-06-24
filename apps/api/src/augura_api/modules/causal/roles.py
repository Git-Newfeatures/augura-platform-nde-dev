"""Phase 3 (ENG-187) — deterministic node-role classification, orphan pruning, and a
dagitty-like serialization of the candidate graph. No LLM: pure graph topology + the PICOT
exposure/outcome seeds. The result is shown to the user as a pre-LLM structural summary and
passed to the LLM as context (the LLM may still re-assign roles per the clinical context).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from augura_api.modules.causal.subgraph import Relation


def _adjacency(
    relations: list[Relation],
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    inc: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for r in relations:
        out[r.subject_concept_id].add(r.object_concept_id)
        inc[r.object_concept_id].add(r.subject_concept_id)
        nodes.add(r.subject_concept_id)
        nodes.add(r.object_concept_id)
    return out, inc, nodes


def _reachable(starts: set[str], adj: dict[str, set[str]]) -> set[str]:
    """Nodes reachable from `starts` following directed edges."""
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        n = stack.pop()
        for m in adj.get(n, set()):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    return seen


def classify_roles(
    relations: list[Relation], *, exposure_ids: list[str], outcome_ids: list[str]
) -> dict[str, str]:
    """Assign a structural DAG role to every concept in the candidate graph."""
    out_adj, in_adj, nodes = _adjacency(relations)
    exposures = {e for e in exposure_ids if e in nodes}
    outcomes = {o for o in outcome_ids if o in nodes}
    reach_from_exp = _reachable(exposures, out_adj)
    roles: dict[str, str] = {}
    for n in sorted(nodes):
        if n in exposures:
            roles[n] = "exposure"
            continue
        if n in outcomes:
            roles[n] = "outcome"
            continue
        n_reach = _reachable({n}, out_adj)
        # mediator: lies on a directed path exposure → n → outcome
        if n in reach_from_exp and (n_reach & outcomes):
            roles[n] = "mediator"
            continue
        # confounder: directed path into BOTH exposure and outcome (and not a mediator)
        if (n_reach & exposures) and (n_reach & outcomes):
            roles[n] = "confounder"
            continue
        # collider: receives incoming edges from two or more concepts
        if len(in_adj.get(n, set())) >= 2:
            roles[n] = "collider"
            continue
        roles[n] = "other"
    return roles


def prune_orphans(
    relations: list[Relation], *, outcome_ids: list[str], keep_ids: list[str] | None = None
) -> list[Relation]:
    """Drop relations whose endpoints cannot reach any outcome (orphan branches). Edges touching
    a `keep_ids` concept (e.g. mapped/seed concepts) are always retained. No-op when no outcome
    concept is present in the graph (nothing to anchor to)."""
    _out, in_adj, nodes = _adjacency(relations)
    outcomes = {o for o in outcome_ids if o in nodes}
    if not outcomes:
        return relations
    # reverse BFS from outcomes over incoming edges → nodes that can reach an outcome
    can_reach: set[str] = set(outcomes)
    stack = list(outcomes)
    while stack:
        n = stack.pop()
        for p in in_adj.get(n, set()):
            if p not in can_reach:
                can_reach.add(p)
                stack.append(p)
    keep = set(keep_ids or [])
    return [
        r
        for r in relations
        if (r.subject_concept_id in can_reach and r.object_concept_id in can_reach)
        or r.subject_concept_id in keep
        or r.object_concept_id in keep
    ]


def dagitty_json(relations: list[Relation], roles: dict[str, str]) -> dict[str, Any]:
    """Compact dagitty-like candidate graph (nodes with roles + directed edges) — the optimized
    structure handed to the LLM."""
    return {
        "nodes": [{"id": n, "role": roles.get(n, "other")} for n in sorted(roles)],
        "edges": [
            {"from": r.subject_concept_id, "to": r.object_concept_id, "predicate": r.predicate}
            for r in relations
        ],
    }
