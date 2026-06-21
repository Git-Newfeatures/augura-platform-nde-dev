"""Appariement lexical colonne→concept (exact synonyme → fuzzy label/synonyme)."""

from __future__ import annotations

from dataclasses import dataclass

from augura_api.modules.mapping.index import ConceptIndex
from augura_api.modules.mapping.normalize import string_similarity


@dataclass(frozen=True)
class Candidate:
    concept_id: str
    concept_label: str
    dq_column_role: str | None
    score: float
    method: str
    layer: int | None = None
    domain: str | None = None


def match_column(norm_name: str, index: ConceptIndex, top_n: int = 5) -> list[Candidate]:
    if not norm_name:
        return []
    hits = index.synonym_lookup.get(norm_name)
    if hits:
        seen: set[str] = set()
        out: list[Candidate] = []
        for cid in hits:
            if cid in seen:
                continue
            seen.add(cid)
            out.append(
                Candidate(
                    cid,
                    index.label[cid],
                    index.role[cid],
                    0.95,
                    "exact_synonym",
                    layer=index.layer.get(cid),
                    domain=index.domain.get(cid),
                )
            )
        return out[:top_n]

    cands: list[Candidate] = []
    for cid in index.concept_ids:
        label_sim = string_similarity(norm_name, index.norm_label[cid])
        if label_sim > 0.85:
            cands.append(
                Candidate(
                    cid,
                    index.label[cid],
                    index.role[cid],
                    label_sim * 0.92,
                    "fuzzy_label",
                    layer=index.layer.get(cid),
                    domain=index.domain.get(cid),
                )
            )
            continue
        best_syn = max(
            (string_similarity(norm_name, s) for s in index.norm_synonyms[cid]), default=0.0
        )
        if best_syn > 0.75:
            cands.append(
                Candidate(
                    cid,
                    index.label[cid],
                    index.role[cid],
                    best_syn * 0.88,
                    "fuzzy_synonym",
                    layer=index.layer.get(cid),
                    domain=index.domain.get(cid),
                )
            )
    cands = [c for c in cands if c.score > 0.20]
    cands.sort(key=lambda c: c.score, reverse=True)
    # dedupe by concept, keep highest
    best_by: dict[str, Candidate] = {}
    for c in cands:
        if c.concept_id not in best_by:
            best_by[c.concept_id] = c
    return list(best_by.values())[:top_n]
