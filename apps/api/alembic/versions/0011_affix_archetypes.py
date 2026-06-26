"""affix archetypes / dimension grammar: governed recognition shapes (A1)

Adds the dimension-grammar capability (semantic layer v3 §2.7): four governed,
read-only tables that decompose a column label into a base concept + governed
dimensions — the wide-encoding sibling of table_archetypes. Idempotent (CREATE …
IF NOT EXISTS, DROP POLICY IF EXISTS): they also live in the canonical bundle
schema.sql + policies.sql executed by 0001_baseline. RLS backend_read like the
other governed catalogs (read open to any backend session, writes only via the
privileged role / upsert_semantic_release).

Revision ID: 0011_affix_archetypes
Revises: 0010_dataset_files
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_affix_archetypes"
down_revision: str | None = "0010_dataset_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AFFIX_TABLES = (
    "dimension_kinds",
    "affix_archetypes",
    "affix_archetype_values",
    "affix_archetype_aliases",
)


def upgrade() -> None:
    op.execute(
        """
        create table if not exists dimension_kinds (
          dimension_kind_id     text primary key,
          label                 text not null,
          description           text not null,
          value_model           text not null,
          default_comparability text not null check (default_comparability in
                                  ('preserves','forks','case_by_case')),
          structural_role       text,
          review_status         text not null,
          version               text not null,
          active                boolean not null
        );
        """
    )
    op.execute(
        """
        create table if not exists affix_archetypes (
          affix_archetype_id      text primary key,
          archetype_name          text not null,
          dimension_kind_id       text not null references dimension_kinds(dimension_kind_id),
          position                text not null check (position in ('prefix','suffix','separator')),
          separator_style         text,
          value_model             text not null check (value_model in
                                    ('closed_set','parametric','event_anchored')),
          comparability           text not null check (comparability in ('preserves','forks')),
          anchor_concept_id       text references taxonomy_concepts(local_concept_id),
          operator                text,
          extraction_rule         text,
          requires_residual_maps  boolean not null default true,
          requires_sibling_family boolean not null default false,
          evidence_weight         numeric not null,
          confidence_threshold    numeric not null check (confidence_threshold between 0 and 1),
          review_status           text not null,
          version                 text not null,
          active                  boolean not null
        );
        """
    )
    op.execute(
        """
        create table if not exists affix_archetype_values (
          affix_archetype_id text not null references affix_archetypes(affix_archetype_id),
          canonical_value    text not null,
          label              text not null,
          review_status      text not null,
          primary key (affix_archetype_id, canonical_value)
        );
        """
    )
    op.execute(
        """
        create table if not exists affix_archetype_aliases (
          affix_archetype_id text not null references affix_archetypes(affix_archetype_id),
          token              text not null,
          canonical_value    text,
          source             text not null,
          review_status      text not null,
          primary key (affix_archetype_id, token)
        );
        """
    )
    op.execute(
        "create index if not exists affix_archetype_aliases_token_idx "
        "on affix_archetype_aliases (lower(token));"
    )

    # RLS: backend_read (FOR SELECT) gated on a backend session, like the other
    # governed catalogs. No write policy ⇒ writes only via the privileged role.
    for t in _AFFIX_TABLES:
        op.execute(f"alter table {t} enable row level security;")
        op.execute(f"alter table {t} force row level security;")
        op.execute(f"drop policy if exists backend_read on {t};")
        op.execute(
            f"create policy backend_read on {t} for select "
            "using (nullif(current_setting('app.tenant_id', true), '') is not null);"
        )


def downgrade() -> None:
    # Drop in reverse FK order.
    for t in reversed(_AFFIX_TABLES):
        op.execute(f"drop table if exists {t} cascade;")
