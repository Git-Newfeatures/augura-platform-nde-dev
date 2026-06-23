"""SQLAlchemy models of the semantic module (DDL created by the bundle)."""

from sqlalchemy import Boolean, Integer, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class TaxonomyConcept(Base):
    __tablename__ = "taxonomy_concepts"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    layer: Mapped[int] = mapped_column(SmallInteger)
    concept_name: Mapped[str] = mapped_column(Text)
    augura_domain: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str | None] = mapped_column(Text)
    value_min: Mapped[float | None] = mapped_column(Numeric)
    value_max: Mapped[float | None] = mapped_column(Numeric)
    canonical_unit: Mapped[str | None] = mapped_column(Text)
    unit_source_value: Mapped[str | None] = mapped_column(Text)
    dq_column_role: Mapped[str | None] = mapped_column(Text)
    range_support_status: Mapped[str | None] = mapped_column(Text)
    unit_coverage_status: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class TaxonomySynonym(Base):
    __tablename__ = "taxonomy_synonyms"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    synonym: Mapped[str] = mapped_column(Text, primary_key=True)
    synonym_type: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)


class TaxonomyDqValidValue(Base):
    __tablename__ = "taxonomy_dq_valid_values"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    coding_system: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)


class TaxonomyMeasurementUnit(Base):
    __tablename__ = "taxonomy_measurement_units"
    unit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    concept_id: Mapped[str] = mapped_column(Text)
    ucum_code: Mapped[str] = mapped_column(Text)
    display_label: Mapped[str] = mapped_column(Text)
    source_aliases: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    quantity_kind: Mapped[str] = mapped_column(Text)
    is_preferred: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class UnitConversion(Base):
    __tablename__ = "unit_conversions"
    conversion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_ucum: Mapped[str] = mapped_column(Text)
    to_ucum: Mapped[str] = mapped_column(Text)
    quantity_kind: Mapped[str] = mapped_column(Text)
    applicable_concept_id: Mapped[str | None] = mapped_column(Text)
    conversion_type: Mapped[str] = mapped_column(Text)
    equation_id: Mapped[str] = mapped_column(Text)
    scale_factor: Mapped[float | None] = mapped_column(Numeric)
    offset: Mapped[float | None] = mapped_column("offset", Numeric)
    precision: Mapped[int] = mapped_column(Integer)
    bidirectional: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class TableArchetype(Base):
    __tablename__ = "table_archetypes"
    archetype_id: Mapped[str] = mapped_column(Text, primary_key=True)
    archetype_name: Mapped[str] = mapped_column(Text)
    key_selectors: Mapped[str] = mapped_column(Text)
    semantic_score: Mapped[float] = mapped_column(Numeric)
    is_surrogate: Mapped[bool] = mapped_column(Boolean)
    description_template: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class DqConstraint(Base):
    __tablename__ = "dq_constraints"
    constraint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_scope: Mapped[str] = mapped_column(Text)
    subject_concept_or_role: Mapped[str] = mapped_column(Text)
    operator: Mapped[str] = mapped_column(Text)
    object_concept_or_role: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[str | None] = mapped_column(Text)
    applies_when: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    implementation_id: Mapped[str] = mapped_column(Text)
    evidence_source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


# ── Ontology/causal (B1) — read-only (consumed by B2/B4) ────────────────────


class TaxonomyStandardCode(Base):
    __tablename__ = "taxonomy_standard_codes"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    vocabulary_id: Mapped[str] = mapped_column(Text, primary_key=True)
    concept_code: Mapped[str] = mapped_column(Text, primary_key=True)
    standard_concept_id: Mapped[str | None] = mapped_column(Text)
    standard_concept_name: Mapped[str | None] = mapped_column(Text)
    standard_concept_flag: Mapped[str | None] = mapped_column(Text)
    concept_class_id: Mapped[str | None] = mapped_column(Text)


class TaxonomyTherapeuticArea(Base):
    __tablename__ = "taxonomy_therapeutic_areas"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    therapeutic_area: Mapped[str] = mapped_column(Text, primary_key=True)


class TaxonomyRelationship(Base):
    __tablename__ = "taxonomy_relationships"
    relationship_id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_concept_id: Mapped[str] = mapped_column(Text)
    to_concept_id: Mapped[str] = mapped_column(Text)
    relationship_type: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class CausalPredicate(Base):
    __tablename__ = "causal_predicates"
    predicate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    direction_type: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class DqPredicate(Base):
    __tablename__ = "dq_predicates"
    predicate_id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    direction_type: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class OntologyRelation(Base):
    __tablename__ = "ontology_relations"
    relation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    subject_concept_id: Mapped[str] = mapped_column(Text)
    predicate: Mapped[str] = mapped_column(Text)
    object_concept_id: Mapped[str] = mapped_column(Text)
    polarity: Mapped[str] = mapped_column(Text)
    default_strength: Mapped[str] = mapped_column(Text)
    default_temporal_lag: Mapped[str] = mapped_column(Text)
    mechanism_summary: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class OntologyRelationEvidence(Base):
    __tablename__ = "ontology_relation_evidence"
    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    relation_id: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    citation_or_url: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[str] = mapped_column(Text)
    population_notes: Mapped[str] = mapped_column(Text)
    evidence_strength: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)


class OntologyRelationQualifier(Base):
    __tablename__ = "ontology_relation_qualifiers"
    qualifier_id: Mapped[str] = mapped_column(Text, primary_key=True)
    relation_id: Mapped[str] = mapped_column(Text)
    qualifier_type: Mapped[str] = mapped_column(Text)
    qualifier_concept_id: Mapped[str | None] = mapped_column(Text)
    qualifier_value: Mapped[str] = mapped_column(Text)
    qualifier_effect: Mapped[str] = mapped_column(Text)
    is_hard_constraint: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)
