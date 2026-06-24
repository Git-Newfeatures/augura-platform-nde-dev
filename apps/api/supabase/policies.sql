-- Augura Platform — Row-Level Security (defense in depth)
-- To apply AFTER schema.sql. Ref: spec §7.
--
-- Model: the FastAPI backend opens each transaction with
--   SET LOCAL app.tenant_id = '<uuid>';
-- and connects with a Postgres role NOT exempt from RLS (not service_role).
-- The policies read current_setting('app.tenant_id').
--
-- Infrastructure tables NOT tenant-scoped: agent_cache (shared deterministic
-- cache) and outbox_events (system audit) — RLS enabled with a "backend session"
-- gate (deny PostgREST anon, allow backend) instead of tenant scoping.

begin;

-- Application connection role (non superuser, non BYPASSRLS).
-- On Supabase, map the API's connection user onto this role.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'augura_app') then
        create role augura_app nologin;
    end if;
end
$$;

grant usage on schema public to augura_app;
grant select, insert, update, delete on all tables in schema public to augura_app;
alter default privileges in schema public
    grant select, insert, update, delete on tables to augura_app;
grant execute on all functions in schema public to augura_app;

-- Connection role (LOGIN) carried by the API (AUGURA_DATABASE_URL = augura_api…).
-- Inherits augura_app; NON superuser / NON BYPASSRLS ⇒ RLS applies.
-- The password is set out-of-bundle (Supabase). This grant makes the bundle
-- self-contained: without it, a rebuilt project would have NO table privilege.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'augura_api') then
        create role augura_api login;
    end if;
end
$$;
grant augura_app to augura_api;

-- Lockdown of the default Supabase grants (PostgREST). ALL data access goes
-- through the backend (role augura_app); anon/authenticated must not read/write
-- the tables directly. Login events are now recorded via the backend
-- (POST /analytics/events/login, Task 2), not a direct PostgREST insert.
-- Guarded by existence: anon/authenticated are specific to Supabase; on a bare
-- Postgres (CI pgvector, alembic upgrade head) these roles do not exist → no-op.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on all tables in schema public from anon;
        alter default privileges in schema public revoke all on tables from anon;
        revoke all on v_coverage_map from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke insert, update, delete, truncate, references, trigger
            on all tables in schema public from authenticated;
        alter default privileges in schema public
            revoke insert, update, delete, truncate, references, trigger on tables from authenticated;
    end if;
end
$$;
-- NOTE: authenticated keeps SELECT for now — a few cockpit views still read
-- via direct PostgREST (backend migration = P7). To revoke once these views
-- are wired to the backend, so that ALL data access goes through augura_app.

-- Helper: expression of the current tenant (NULL if not set).
-- (inlined in the policies below; kept here for reference)
--   nullif(current_setting('app.tenant_id', true), '')::uuid

-- ── Tables with direct org_id ─────────────────────────────────────────────
do $$
declare
    t text;
begin
    foreach t in array array[
        'studies', 'datasets', 'cohort_members', 'cohort_biomarkers',
        'agent_runs', 'simulation_runs', 'simulation_results', 'jobs',
        'generated_documents', 'artifacts'
    ]
    loop
        execute format('alter table %I enable row level security;', t);
        execute format('alter table %I force row level security;', t);
        execute format($f$
            create policy tenant_isolation on %I
            using (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        $f$, t);
    end loop;
end
$$;

-- ── orgs: the tenant only sees its own row ───────────────────────────────
alter table orgs enable row level security;
alter table orgs force row level security;
create policy tenant_self on orgs
    using (id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- ── memberships: a user only sees THEIR OWN memberships ──────────────────
-- (scoped on app.user_id, not app.tenant_id: it is the bootstrap that resolves
-- precisely the tenant from the user — cf. core/deps.py)
alter table memberships enable row level security;
alter table memberships force row level security;
create policy member_self on memberships
    using (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
    with check (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

-- ── Child tables scoped via their parent ──────────────────────────────────
alter table study_members enable row level security;
alter table study_members force row level security;
create policy tenant_via_study on study_members
    using (exists (
        select 1 from studies s
        where s.id = study_members.study_id
          and s.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ));

alter table study_state enable row level security;
alter table study_state force row level security;
create policy tenant_via_study on study_state
    using (exists (
        select 1 from studies s
        where s.id = study_state.study_id
          and s.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ))
    with check (exists (
        select 1 from studies s
        where s.id = study_state.study_id
          and s.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ));

alter table dataset_columns enable row level security;
alter table dataset_columns force row level security;
create policy tenant_via_dataset on dataset_columns
    using (exists (
        select 1 from datasets d
        where d.id = dataset_columns.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ))
    with check (exists (
        select 1 from datasets d
        where d.id = dataset_columns.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ));

alter table dataset_files enable row level security;
alter table dataset_files force row level security;
create policy tenant_via_dataset on dataset_files
    using (exists (
        select 1 from datasets d
        where d.id = dataset_files.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ))
    with check (exists (
        select 1 from datasets d
        where d.id = dataset_files.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ));

-- ── Corpus: org_id NULL ⇒ global, readable by all ────────────────────────
alter table documents enable row level security;
alter table documents force row level security;
create policy tenant_or_global on documents
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    )
    -- Read: global OR tenant. Write: strictly the current tenant — the global
    -- rows (org_id NULL, visible to all) are only ingested via a privileged role
    -- (seed/worker BYPASSRLS), never from a tenant session.
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

alter table chunks enable row level security;
alter table chunks force row level security;
create policy tenant_or_global on chunks
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    )
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- ── usage_events: append-only audit (tenant/system reads; INSERT only) ────
alter table usage_events enable row level security;
alter table usage_events force row level security;
drop policy if exists tenant_or_system on usage_events;
drop policy if exists usage_events_read on usage_events;
drop policy if exists usage_events_insert on usage_events;
create policy usage_events_read on usage_events
    for select
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );
create policy usage_events_insert on usage_events
    for insert
    with check (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );
-- Append-only at the privilege level too: no UPDATE/DELETE/TRUNCATE for the app role.
revoke update, delete, truncate on usage_events from augura_app;

-- ── agent_cache: shared deterministic cache, backend-session gated (read/write) ──
alter table agent_cache enable row level security;
alter table agent_cache force row level security;
drop policy if exists backend_session on agent_cache;
create policy backend_session on agent_cache
    using (nullif(current_setting('app.tenant_id', true), '') is not null)
    with check (nullif(current_setting('app.tenant_id', true), '') is not null);

-- ── outbox_events: append-only system audit, backend-session gated ────────
alter table outbox_events enable row level security;
alter table outbox_events force row level security;
drop policy if exists backend_session on outbox_events;
drop policy if exists outbox_events_read on outbox_events;
drop policy if exists outbox_events_insert on outbox_events;
create policy outbox_events_read on outbox_events
    for select
    using (nullif(current_setting('app.tenant_id', true), '') is not null);
create policy outbox_events_insert on outbox_events
    for insert
    with check (nullif(current_setting('app.tenant_id', true), '') is not null);
-- NOTE: a future outbox relay/dispatcher that sets outbox_events.processed_at must run
-- under a privileged worker role (BYPASSRLS) — like the seed/worker path — because
-- augura_app is intentionally denied UPDATE here to keep the audit trail append-only.
revoke update, delete, truncate on outbox_events from augura_app;

-- ── Reference catalogs (cesl_sources, cesl_study_designs) ─────────────────
-- Global, read-only for tenant sessions. RLS enabled + "backend session"
-- gate on READ only (FOR SELECT): anon/PostgREST denied, backend
-- (app.tenant_id set) allowed to read. No write policy ⇒ INSERT/
-- UPDATE/DELETE denied for augura_app; the seed loads via the privileged role.
alter table cesl_sources enable row level security;
alter table cesl_sources force row level security;
create policy backend_read on cesl_sources
    for select
    using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table cesl_study_designs enable row level security;
alter table cesl_study_designs force row level security;
create policy backend_read on cesl_study_designs
    for select
    using (nullif(current_setting('app.tenant_id', true), '') is not null);

-- ── Reference catalogs (frontend real-only cleanup): global, read-only ──────
do $$
declare t text;
begin
  foreach t in array array[
    'outcome_catalog','estimand_catalog','estimator_catalog','framework_catalog',
    'evidence_type_catalog','domain_catalog','jurisdiction_catalog',
    'literature_design_catalog','pii_pattern_catalog','biomarker_range_catalog',
    'variable_group_catalog','variable_role_catalog'
  ] loop
    execute format('alter table %I enable row level security;', t);
    execute format('alter table %I force row level security;', t);
    execute format('drop policy if exists backend_read on %I;', t);
    execute format($f$create policy backend_read on %I for select
        using (nullif(current_setting('app.tenant_id', true), '') is not null);$f$, t);
  end loop;
end $$;

-- ── Semantic taxonomy (A1): global, read-only (FOR SELECT) ────────────────
alter table taxonomy_concepts enable row level security;
alter table taxonomy_concepts force row level security;
create policy backend_read on taxonomy_concepts
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_synonyms enable row level security;
alter table taxonomy_synonyms force row level security;
create policy backend_read on taxonomy_synonyms
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_dq_valid_values enable row level security;
alter table taxonomy_dq_valid_values force row level security;
create policy backend_read on taxonomy_dq_valid_values
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_measurement_units enable row level security;
alter table taxonomy_measurement_units force row level security;
create policy backend_read on taxonomy_measurement_units
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table unit_conversions enable row level security;
alter table unit_conversions force row level security;
create policy backend_read on unit_conversions
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table table_archetypes enable row level security;
alter table table_archetypes force row level security;
create policy backend_read on table_archetypes
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table dq_constraints enable row level security;
alter table dq_constraints force row level security;
create policy backend_read on dq_constraints
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

-- ── Ontology/causal (B1): global, read-only (FOR SELECT) ──────────────────
-- Same reference catalogs as the A1 taxonomy: RLS enabled + "backend
-- session" gate on read. No write policy ⇒ the seed loads via
-- the privileged role.
do $$
declare t text;
begin
  foreach t in array array[
    'taxonomy_standard_codes','taxonomy_therapeutic_areas','taxonomy_relationships',
    'causal_predicates','dq_predicates','ontology_relations',
    'ontology_relation_evidence','ontology_relation_qualifiers','semantic_releases'
  ] loop
    execute format('alter table %I enable row level security;', t);
    execute format('alter table %I force row level security;', t);
    execute format('drop policy if exists backend_read on %I;', t);
    execute format($f$create policy backend_read on %I for select
        using (nullif(current_setting('app.tenant_id', true), '') is not null);$f$, t);
  end loop;
end $$;

-- ── dq_bundles (A3a): tenant-scoped via org_id ───────────────────────────
alter table dq_bundles enable row level security;
alter table dq_bundles force row level security;
create policy tenant_isolation on dq_bundles
    using (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- ── Corpus live (retrieve-and-freeze) ─────────────────────────────────────
-- search_sessions / literature_events / literature_queries: simple tenant
-- isolation (org_id = app.tenant_id), like the 0002 baseline.
do $$
declare
    t text;
begin
    foreach t in array array['search_sessions', 'literature_events', 'literature_queries']
    loop
        execute format('alter table %I enable row level security;', t);
        execute format('alter table %I force row level security;', t);
        execute format($f$
            create policy tenant_isolation on %I
            using (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        $f$, t);
    end loop;
end
$$;

-- ── literature_snapshots: tenant isolation + PER-STUDY visibility (Tier 3) ──
-- Tenant isolation (org_id) remains the first line of defense. On top of it, access is
-- gated as follows:
--   • study_id NON NULL ⇒ visible to the study MEMBERS (study_members), NOT to
--     the whole tenant. This is the critical point (gate 9): we gate by study_members,
--     never by study_id alone — otherwise a snapshot would leak between studies of the same
--     tenant. A non-member fails closed (the EXISTS is false ⇒ row invisible).
--   • study_id NULL ⇒ standalone snapshot, visible only to its creator.
-- created_by is recorded but is NOT the gate for study snapshots.
-- WITH CHECK: we only write for the current tenant, as the creator, and —
-- if attached to a study — only if we are a member of it (no writing into
-- someone else's study). app.user_id not set ⇒ everything fails closed.
alter table literature_snapshots enable row level security;
alter table literature_snapshots force row level security;
create policy snapshot_tenant_study_access on literature_snapshots
    using (
        org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
        and (
            (study_id is null
                and created_by = nullif(current_setting('app.user_id', true), '')::uuid)
            or (study_id is not null and exists (
                select 1 from study_members m
                where m.study_id = literature_snapshots.study_id
                  and m.user_id = nullif(current_setting('app.user_id', true), '')::uuid
            ))
        )
    )
    with check (
        org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
        and created_by = nullif(current_setting('app.user_id', true), '')::uuid
        and (
            study_id is null
            or exists (
                select 1 from study_members m
                where m.study_id = literature_snapshots.study_id
                  and m.user_id = nullif(current_setting('app.user_id', true), '')::uuid
            )
        )
    );

-- ── Object storage: the datasets bucket must exist and be PRIVATE ─────────
-- Guarded: the `storage` schema only exists on Supabase, not on the bare CI
-- Postgres (pgvector) where the bundle is also applied → no-op there.
do $$
begin
    if exists (select 1 from information_schema.schemata where schema_name = 'storage') then
        insert into storage.buckets (id, name, public)
        values ('datasets', 'datasets', false)
        on conflict (id) do update set public = false;
    end if;
end
$$;

commit;
