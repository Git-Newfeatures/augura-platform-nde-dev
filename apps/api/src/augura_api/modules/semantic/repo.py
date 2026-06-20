"""Accès base du module semantic — catalogues globaux (lecture seule)."""

import json
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.semantic.models import (
    CausalPredicate,
    DqConstraint,
    OntologyRelation,
    OntologyRelationEvidence,
    OntologyRelationQualifier,
    TableArchetype,
    TaxonomyConcept,
    TaxonomyDqValidValue,
    TaxonomyMeasurementUnit,
    TaxonomyRelationship,
    TaxonomySynonym,
    UnitConversion,
)

# Les 14 tables de la couche sémantique gouvernée exposées par GET /semantic/bundle
# (dans l'ordre du contrat front ; dq_predicates exclu — consommé par le stack DQ).
# Noms en dur (jamais d'entrée utilisateur) → pas de risque d'injection.
_BUNDLE_TABLES = (
    "taxonomy_concepts",
    "taxonomy_synonyms",
    "taxonomy_standard_codes",
    "taxonomy_therapeutic_areas",
    "taxonomy_relationships",
    "taxonomy_dq_valid_values",
    "taxonomy_measurement_units",
    "unit_conversions",
    "causal_predicates",
    "ontology_relations",
    "ontology_relation_evidence",
    "ontology_relation_qualifiers",
    "dq_constraints",
    "table_archetypes",
)

# Bundle = un seul objet jsonb {table: [lignes brutes]} (port du RPC semantic_read_all,
# mais inline sur le schéma public — pas de fonction stockée à maintenir).
_BUNDLE_SQL = (
    "select jsonb_build_object(\n"
    + ",\n".join(
        f"  '{t}', (select coalesce(jsonb_agg(to_jsonb(r)), '[]'::jsonb) from {t} r)"
        for t in _BUNDLE_TABLES
    )
    + "\n)"
)

# Statut de release : ligne courante de semantic_releases + compte par table.
_RELEASE_SQL = (
    "select jsonb_build_object("
    "'release', (select to_jsonb(r) from semantic_releases r "
    "where r.is_current order by r.imported_at desc limit 1), "
    "'counts', (select jsonb_object_agg(table_name, row_count) from ("
    + " union all ".join(
        f"select '{t}' table_name, count(*) row_count from {t}" for t in _BUNDLE_TABLES
    )
    + ") c))"
)


def coerce_jsonb(value: Any) -> dict[str, Any]:
    """asyncpg peut renvoyer le jsonb déjà désérialisé ou son texte ; on normalise."""
    if isinstance(value, str):
        return json.loads(value)
    return value


class SemanticRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[TaxonomyConcept]:
        stmt = select(TaxonomyConcept)
        if active:
            stmt = stmt.where(TaxonomyConcept.active.is_(True))
        if domain:
            stmt = stmt.where(TaxonomyConcept.augura_domain == domain)
        stmt = stmt.order_by(TaxonomyConcept.local_concept_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_synonyms(self) -> list[TaxonomySynonym]:
        return list((await self.session.execute(select(TaxonomySynonym))).scalars().all())

    async def list_valid_values(self) -> list[TaxonomyDqValidValue]:
        return list((await self.session.execute(select(TaxonomyDqValidValue))).scalars().all())

    async def list_measurement_units(self) -> list[TaxonomyMeasurementUnit]:
        return list((await self.session.execute(select(TaxonomyMeasurementUnit))).scalars().all())

    async def list_unit_conversions(self) -> list[UnitConversion]:
        return list((await self.session.execute(select(UnitConversion))).scalars().all())

    async def list_archetypes(self, *, active: bool = True) -> list[TableArchetype]:
        stmt = select(TableArchetype)
        if active:
            stmt = stmt.where(TableArchetype.active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_constraints(self, *, status: str | None = "active") -> list[DqConstraint]:
        stmt = select(DqConstraint)
        if status:
            stmt = stmt.where(DqConstraint.status == status)
        return list((await self.session.execute(stmt)).scalars().all())

    # ── Ontologie/causal (B1) ──────────────────────────────────────────────

    async def list_relations(self, *, active: bool = True) -> list[OntologyRelation]:
        stmt = select(OntologyRelation)
        if active:
            stmt = stmt.where(OntologyRelation.active.is_(True))
        stmt = stmt.order_by(OntologyRelation.relation_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def relations_for_concepts(self, concept_ids: list[str]) -> list[OntologyRelation]:
        """Sous-graphe : relations actives dont le sujet OU l'objet ∈ concept_ids (B2)."""
        stmt = (
            select(OntologyRelation)
            .where(
                OntologyRelation.active.is_(True),
                or_(
                    OntologyRelation.subject_concept_id.in_(concept_ids),
                    OntologyRelation.object_concept_id.in_(concept_ids),
                ),
            )
            .order_by(OntologyRelation.relation_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_relation_evidence(self) -> list[OntologyRelationEvidence]:
        stmt = select(OntologyRelationEvidence)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_relation_qualifiers(self) -> list[OntologyRelationQualifier]:
        stmt = select(OntologyRelationQualifier)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_causal_predicates(self) -> list[CausalPredicate]:
        return list((await self.session.execute(select(CausalPredicate))).scalars().all())

    async def list_relationships(self) -> list[TaxonomyRelationship]:
        return list((await self.session.execute(select(TaxonomyRelationship))).scalars().all())

    # ── Bundle gouverné + statut de release (lecture en bloc) ───────────────

    async def read_bundle(self) -> dict[str, Any]:
        """Les 14 tables sémantiques en un objet jsonb (GET /semantic/bundle)."""
        res = await self.session.execute(text(_BUNDLE_SQL))
        return coerce_jsonb(res.scalar_one())

    async def release_status(self) -> dict[str, Any]:
        """Release courante + compte par table (GET /semantic/release)."""
        res = await self.session.execute(text(_RELEASE_SQL))
        return coerce_jsonb(res.scalar_one())

    # ── Écriture (B4 enrich) : exclusivement via la fonction SECURITY DEFINER ──

    async def apply_release(
        self, manifest: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Applique un batch d'enrichissement + bascule la release courante.

        Le rôle applicatif n'a pas le write direct (RLS FOR SELECT) ; tout passe par
        public.upsert_semantic_release (SECURITY DEFINER). Renvoie {version, concepts,
        relations}."""
        stmt = text(
            "select public.upsert_semantic_release("
            "cast(:manifest as jsonb), cast(:payload as jsonb))"
        ).bindparams(manifest=json.dumps(manifest), payload=json.dumps(payload))
        res = await self.session.execute(stmt)
        return coerce_jsonb(res.scalar_one())

    async def max_relation_seq(self, today: str) -> int:
        """Plus grand NNN des relation_id ENRR_{today}_NNN (évite les collisions d'id)."""
        _pat = r"'ENRR_' || :d || '_(\d{3})'"
        stmt = text(
            f"select coalesce(max(substring(relation_id from {_pat})::int), 0) "
            "from ontology_relations"
        ).bindparams(d=today)
        return int((await self.session.execute(stmt)).scalar_one())

    async def max_qualifier_seq(self, today: str) -> int:
        """Plus grand NNN des qualifier_id ENRQ_{today}_NNN (évite les collisions d'id)."""
        _pat = r"'ENRQ_' || :d || '_(\d{3})'"
        stmt = text(
            f"select coalesce(max(substring(qualifier_id from {_pat})::int), 0) "
            "from ontology_relation_qualifiers"
        ).bindparams(d=today)
        return int((await self.session.execute(stmt)).scalar_one())

    async def existing_concept_ids(self, ids: list[str]) -> set[str]:
        """Sous-ensemble des ids fournis qui existent dans la taxonomie (validation FK)."""
        if not ids:
            return set()
        stmt = select(TaxonomyConcept.local_concept_id).where(
            TaxonomyConcept.local_concept_id.in_(ids)
        )
        return set((await self.session.execute(stmt)).scalars().all())

    async def get_relation_row(self, relation_id: str) -> dict[str, Any] | None:
        """Récupère une relation sous forme dict brut (pour deactivate)."""
        stmt = text(
            "select to_jsonb(r) from ontology_relations r where relation_id = :rid"
        ).bindparams(rid=relation_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return coerce_jsonb(row) if row is not None else None
