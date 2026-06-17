"""Modèles SQLAlchemy du module reference (DDL créé par le bundle SQL)."""

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    cesl_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class CeslSource(Base):
    __tablename__ = "cesl_sources"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    result_unit: Mapped[str | None] = mapped_column(Text)
    default_evidence_type: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class CeslStudyDesign(Base):
    __tablename__ = "cesl_study_designs"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    group_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    estimands: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class OutcomeCatalog(Base):
    __tablename__ = "outcome_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    short_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text)
    regulatory_tags: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    verdict: Mapped[str | None] = mapped_column(Text)
    verdict_label: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EstimandCatalog(Base):
    __tablename__ = "estimand_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    regulatory: Mapped[str | None] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    tag: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EstimatorCatalog(Base):
    __tablename__ = "estimator_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    short: Mapped[str] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bootstrap_pending: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    interpretability: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    stability: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    tooltip: Mapped[str | None] = mapped_column(Text)
    eligible_study_types: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class FrameworkCatalog(Base):
    __tablename__ = "framework_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EvidenceTypeCatalog(Base):
    __tablename__ = "evidence_type_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DomainCatalog(Base):
    __tablename__ = "domain_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class JurisdictionCatalog(Base):
    __tablename__ = "jurisdiction_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class LiteratureDesignCatalog(Base):
    __tablename__ = "literature_design_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class PiiPatternCatalog(Base):
    __tablename__ = "pii_pattern_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    pattern: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class BiomarkerRangeCatalog(Base):
    __tablename__ = "biomarker_range_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    pattern: Mapped[str] = mapped_column(Text)
    value_min: Mapped[float | None] = mapped_column(Numeric)
    value_max: Mapped[float | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class VariableGroupCatalog(Base):
    __tablename__ = "variable_group_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    alias_of: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class VariableRoleCatalog(Base):
    __tablename__ = "variable_role_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    group_code: Mapped[str | None] = mapped_column(Text)
    selectable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
