"""Sous-graphe causal déterministe (sans LLM).

Port de `reference/data-intake-nde/src/causal/ontology-loader.js` (jointure relations
+ evidence + qualifiers) et de la collecte/cap de `dag-generator.js`. Aucune dérive :
les arêtes proviennent exclusivement de l'ontologie B1 revue.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from augura_api.modules.semantic.models import (
    OntologyRelation,
    OntologyRelationEvidence,
    OntologyRelationQualifier,
    TaxonomyConcept,
)

MAX_CANDIDATES = 40  # au-delà, le prompt LLM devient ingérable (cf. dag-generator.js)


@dataclass(frozen=True)
class ConceptMeta:
    label: str
    domain: str
    layer: int


@dataclass(frozen=True)
class Relation:
    """Relation d'ontologie enrichie (evidence + qualifiers) prête pour le prompt."""

    id: str
    subject_concept_id: str
    object_concept_id: str
    predicate: str
    polarity: str
    default_strength: str
    default_temporal_lag: str
    mechanism_summary: str
    evidence: tuple[dict[str, str], ...] = ()
    qualifiers: tuple[dict[str, object], ...] = ()


def concept_index(rows: list[TaxonomyConcept]) -> dict[str, ConceptMeta]:
    return {r.local_concept_id: ConceptMeta(r.concept_name, r.augura_domain, r.layer) for r in rows}


def _evidence_dict(e: OntologyRelationEvidence) -> dict[str, str]:
    return {
        "source_type": e.source_type,
        "citation": e.citation_or_url,
        "summary": e.evidence_summary,
        "strength": e.evidence_strength,
    }


def _qualifier_dict(q: OntologyRelationQualifier) -> dict[str, object]:
    return {
        "type": q.qualifier_type,
        "value": q.qualifier_value,
        "effect": q.qualifier_effect,
        "is_hard_constraint": q.is_hard_constraint,
        "notes": q.notes,
    }


def build_relations(
    rows: list[OntologyRelation],
    evidence: list[OntologyRelationEvidence],
    qualifiers: list[OntologyRelationQualifier],
) -> list[Relation]:
    """Joint relations actives + evidence + qualifiers (port de buildOntology)."""
    ev_by_rel: dict[str, list[dict[str, str]]] = defaultdict(list)
    for e in evidence:
        ev_by_rel[e.relation_id].append(_evidence_dict(e))
    q_by_rel: dict[str, list[dict[str, object]]] = defaultdict(list)
    for q in qualifiers:
        q_by_rel[q.relation_id].append(_qualifier_dict(q))
    return [
        Relation(
            id=r.relation_id,
            subject_concept_id=r.subject_concept_id,
            object_concept_id=r.object_concept_id,
            predicate=r.predicate,
            polarity=r.polarity,
            default_strength=r.default_strength,
            default_temporal_lag=r.default_temporal_lag,
            mechanism_summary=r.mechanism_summary,
            evidence=tuple(ev_by_rel.get(r.relation_id, ())),
            qualifiers=tuple(q_by_rel.get(r.relation_id, ())),
        )
        for r in rows
        if r.active
    ]


@dataclass
class _Index:
    by_subject: dict[str, list[Relation]] = field(default_factory=lambda: defaultdict(list))
    by_object: dict[str, list[Relation]] = field(default_factory=lambda: defaultdict(list))


def _index(relations: list[Relation]) -> _Index:
    idx = _Index()
    for rel in relations:
        idx.by_subject[rel.subject_concept_id].append(rel)
        idx.by_object[rel.object_concept_id].append(rel)
    return idx


def causal_subgraph(
    relations: list[Relation], concept_ids: list[str], *, hops: int = 2
) -> list[Relation]:
    """BFS multi-sauts autour des concepts (port de getCausalSubgraph)."""
    idx = _index(relations)
    seen: set[str] = set()
    result: list[Relation] = []
    frontier = set(concept_ids)
    for h in range(hops + 1):
        nxt: set[str] = set()
        for cid in frontier:
            for rel in idx.by_subject.get(cid, []):
                if rel.id not in seen:
                    seen.add(rel.id)
                    result.append(rel)
                    nxt.add(rel.object_concept_id)
            for rel in idx.by_object.get(cid, []):
                if rel.id not in seen:
                    seen.add(rel.id)
                    result.append(rel)
                    nxt.add(rel.subject_concept_id)
        if h < hops:
            frontier = nxt
    return result


def cap_candidates(candidates: list[Relation], concept_ids: list[str]) -> list[Relation]:
    """Priorise les relations directes puis tronque à MAX_CANDIDATES (port dag-generator)."""
    if len(candidates) <= MAX_CANDIDATES:
        return candidates
    seeds = set(concept_ids)
    direct = [
        r for r in candidates if r.subject_concept_id in seeds or r.object_concept_id in seeds
    ]
    indirect = [r for r in candidates if r not in direct]
    return [*direct, *indirect][:MAX_CANDIDATES]
