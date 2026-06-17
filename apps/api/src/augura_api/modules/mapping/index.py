"""Index de concepts pour l'appariement lexical (depuis la taxonomie A1)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from augura_api.modules.mapping.normalize import normalize


class _ConceptRow(Protocol):
    local_concept_id: str
    concept_name: str
    dq_column_role: str | None


class _SynonymRow(Protocol):
    local_concept_id: str
    synonym: str


@dataclass
class ConceptIndex:
    concept_ids: list[str] = field(default_factory=list[str])
    label: dict[str, str] = field(default_factory=dict[str, str])
    role: dict[str, str | None] = field(default_factory=dict[str, str | None])
    norm_label: dict[str, str] = field(default_factory=dict[str, str])
    norm_synonyms: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    synonym_lookup: dict[str, list[str]] = field(default_factory=dict[str, list[str]])


def build_index(concepts: Sequence[_ConceptRow], synonyms: Sequence[_SynonymRow]) -> ConceptIndex:
    syn_by: dict[str, list[str]] = defaultdict(list)
    for s in synonyms:
        syn_by[s.local_concept_id].append(s.synonym)
    idx = ConceptIndex()
    lookup: dict[str, list[str]] = defaultdict(list)
    for c in concepts:
        cid = c.local_concept_id
        idx.concept_ids.append(cid)
        idx.label[cid] = c.concept_name
        idx.role[cid] = c.dq_column_role
        nl = normalize(c.concept_name)
        idx.norm_label[cid] = nl
        if nl:
            lookup[nl].append(cid)
        ns: list[str] = []
        for syn in syn_by.get(cid, []):
            n = normalize(syn)
            ns.append(n)
            if n:
                lookup[n].append(cid)
        idx.norm_synonyms[cid] = ns
    idx.synonym_lookup = dict(lookup)
    return idx
