"""Logique d'apply de l'enrichissement (B4) — port de api/enrich-apply.js.

4 chemins, un seul actif par requête : proposals approuvées (pipeline propose) ·
direct_relations (relations proposées par le DAG) · deactivate_relation · add_qualifier.
Tous construisent un (manifest, payload) délégué à SemanticRepo.apply_release.
"""

from typing import Any, cast

from augura_api.core.errors import BadRequestError, NotFoundError
from augura_api.modules.semantic.enrich_schemas import (
    AddQualifierIn,
    DirectRelationIn,
    EnrichApplyRequest,
    EnrichApplyResponse,
)
from augura_api.modules.semantic.repo import SemanticRepo


def bump_version(current: str | None, kind: str) -> str:
    """Bump SemVer (port de bumpVersion). Fallback 3.0.0."""
    parts = [int(x) for x in (current or "3.0.0").split(".")]
    major, minor, patch = (parts + [0, 0, 0])[:3]
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _manifest(version: str, description: str) -> dict[str, Any]:
    return {
        "semantic_release_version": version,
        "taxonomy_version": version,
        "causal_ontology_version": version,
        "dq_ontology_version": version,
        "omop_cdm_version": "5.4",
        "description": description,
    }


def build_direct_relations_payload(
    relations: list[DirectRelationIn], *, version: str, existing_max_rel_n: int, today: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Assigne ENRR_{today}_{NNN}, auto-stub evidence, renvoie (payload, id_map)."""
    id_map: dict[str, str] = {}
    rel_rows: list[dict[str, Any]] = []
    ev_rows: list[dict[str, Any]] = []
    for ev_i, rel in enumerate(relations, start=1):
        rel_n = existing_max_rel_n + ev_i
        rid = f"ENRR_{today}_{rel_n:03d}"
        if rel.relation_id:
            id_map[rel.relation_id] = rid
        rel_rows.append(
            {
                "relation_id": rid,
                "subject_concept_id": rel.subject_concept_id,
                "object_concept_id": rel.object_concept_id,
                "predicate": rel.predicate,
                "polarity": rel.polarity,
                "default_strength": rel.default_strength,
                "default_temporal_lag": "unknown",
                "mechanism_summary": rel.mechanism_summary,
                "version": version,
                "active": True,
                "review_status": "approved",
            }
        )
        ev_rows.append(
            {
                "evidence_id": f"ENRV_{today}_{ev_i:03d}",
                "relation_id": rid,
                "source_type": "established_physiology",
                "citation_or_url": "established physiology",
                "evidence_summary": rel.mechanism_summary or "established physiology",
                "population_notes": "",
                "evidence_strength": "established",
                "review_status": "approved",
            }
        )
    return {"ontology_relations": rel_rows, "ontology_relation_evidence": ev_rows}, id_map


class EnrichApplyService:
    """Orchestre l'apply : choisit le chemin, calcule le bump, délègue au repo."""

    def __init__(self, repo: SemanticRepo) -> None:
        self.repo = repo

    async def apply(self, req: EnrichApplyRequest, *, today: str) -> EnrichApplyResponse:
        status = await self.repo.release_status()
        release: dict[str, Any] = status.get("release") or {}
        current: str = release.get("semantic_release_version") or "3.0.0"

        if req.deactivate_relation is not None:
            return await self._deactivate(req.deactivate_relation.relation_id, current)
        if req.add_qualifier is not None:
            return await self._add_qualifier(req.add_qualifier, current, today)
        if req.direct_relations:
            return await self._direct_relations(req.direct_relations, current, today)
        if req.proposals:
            return await self._proposals(req, current)
        raise BadRequestError("aucun chemin d'apply renseigné")

    async def _direct_relations(
        self, relations: list[DirectRelationIn], current: str, today: str
    ) -> EnrichApplyResponse:
        new_version = bump_version(current, "patch")
        all_ids = {cid for r in relations for cid in (r.subject_concept_id, r.object_concept_id)}
        known = await self.repo.existing_concept_ids(list(all_ids))
        valid = [
            r for r in relations if r.subject_concept_id in known and r.object_concept_id in known
        ]
        if not valid:
            unknown = sorted(all_ids - known)
            raise BadRequestError(
                "aucune relation ne référence des concepts existants",
                unknown_concept_ids=unknown,
            )
        relations = valid
        max_n = await self.repo.max_relation_seq(today)
        payload, id_map = build_direct_relations_payload(
            relations, version=new_version, existing_max_rel_n=max_n, today=today
        )
        manifest = _manifest(
            new_version, f"patch: +{len(payload['ontology_relations'])} relation(s) via DAG"
        )
        await self.repo.apply_release(manifest, payload)
        return EnrichApplyResponse(
            new_version=new_version,
            previous_version=current,
            relations_added=len(payload["ontology_relations"]),
            relation_id_map=id_map,
        )

    async def _deactivate(self, relation_id: str, current: str) -> EnrichApplyResponse:
        existing = await self.repo.get_relation_row(relation_id)
        if existing is None:
            raise NotFoundError("relation introuvable", relation_id=relation_id)
        new_version = bump_version(current, "patch")
        row: dict[str, Any] = {
            **existing,
            "active": False,
            "review_status": "deprecated",
            "version": new_version,
        }
        manifest = _manifest(new_version, f"patch: deactivate {relation_id} via DAG review")
        await self.repo.apply_release(manifest, {"ontology_relations": [row]})
        return EnrichApplyResponse(
            new_version=new_version,
            previous_version=current,
            detail=f"relation_deactivated:{relation_id}",
        )

    async def _add_qualifier(
        self, q: AddQualifierIn, current: str, today: str
    ) -> EnrichApplyResponse:
        new_version = bump_version(current, "patch")
        max_n = await self.repo.max_qualifier_seq(today)
        row: dict[str, Any] = {
            "qualifier_id": f"ENRQ_{today}_{max_n + 1:03d}",
            "relation_id": q.relation_id,
            "qualifier_type": q.qualifier_type,
            "qualifier_concept_id": None,
            "qualifier_value": q.qualifier_value,
            "qualifier_effect": q.qualifier_effect,
            "is_hard_constraint": q.is_hard_constraint,
            "notes": q.notes,
        }
        manifest = _manifest(new_version, f"patch: +1 qualifier on {q.relation_id}")
        await self.repo.apply_release(manifest, {"ontology_relation_qualifiers": [row]})
        return EnrichApplyResponse(
            new_version=new_version,
            previous_version=current,
            detail=f"qualifier_added:{row['qualifier_id']}",
        )

    async def _proposals(self, req: EnrichApplyRequest, current: str) -> EnrichApplyResponse:
        # Port de enrich-apply.js:262-345 — filtre les rows sélectionnés + cascade enfants,
        # stampe approved/active, bump minor si concepts sinon patch.
        p: dict[str, Any] = req.proposals or {}
        csel = set(req.selected_concept_ids)
        rsel = set(req.selected_relation_ids)

        def _dicts(key: str) -> list[dict[str, Any]]:
            """Extrait les items dict[str, Any] d'une liste brute du payload."""
            return [cast(dict[str, Any], row) for row in p.get(key, []) if isinstance(row, dict)]

        all_concepts = _dicts("taxonomy_concepts")
        all_relations = _dicts("ontology_relations")
        concepts = [c for c in all_concepts if c.get("local_concept_id") in csel]
        relations = [r for r in all_relations if r.get("relation_id") in rsel]
        if not concepts and not relations:
            raise BadRequestError("aucun concept/relation approuvé à appliquer")
        cset = {c["local_concept_id"] for c in concepts}
        rset = {r["relation_id"] for r in relations}
        new_version = bump_version(current, "minor" if concepts else "patch")

        def stamp(row: dict[str, Any]) -> dict[str, Any]:
            return {**row, "version": new_version, "active": True, "review_status": "approved"}

        def stamp_sub(row: dict[str, Any]) -> dict[str, Any]:
            return {**row, "review_status": "approved"}

        payload: dict[str, Any] = {
            "taxonomy_concepts": [stamp(c) for c in concepts],
            "taxonomy_synonyms": [
                stamp_sub(s)
                for s in _dicts("taxonomy_synonyms")
                if s.get("local_concept_id") in cset
            ],
            "taxonomy_standard_codes": [
                s for s in _dicts("taxonomy_standard_codes") if s.get("local_concept_id") in cset
            ],
            "ontology_relations": [stamp(r) for r in relations],
            "ontology_relation_evidence": [
                stamp_sub(e)
                for e in _dicts("ontology_relation_evidence")
                if e.get("relation_id") in rset
            ],
            "ontology_relation_qualifiers": [
                stamp_sub(qf)
                for qf in _dicts("ontology_relation_qualifiers")
                if qf.get("relation_id") in rset
            ],
        }
        manifest = _manifest(
            new_version,
            f"patch: +{len(concepts)} concept(s), +{len(relations)} relation(s) via enrichment",
        )
        await self.repo.apply_release(manifest, payload)
        return EnrichApplyResponse(
            new_version=new_version,
            previous_version=current,
            concepts_added=len(concepts),
            relations_added=len(relations),
        )
