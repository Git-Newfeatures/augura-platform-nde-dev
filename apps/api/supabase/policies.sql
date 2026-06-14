-- Augura Platform — Row-Level Security (défense en profondeur)
-- À appliquer APRÈS schema.sql. Réf : spec §7.
--
-- Modèle : le backend FastAPI ouvre chaque transaction avec
--   SET LOCAL app.tenant_id = '<uuid>';
-- et se connecte avec un rôle Postgres NON exempt de RLS (pas service_role).
-- Les policies lisent current_setting('app.tenant_id').
--
-- Tables d'infrastructure NON tenant-scopées : agent_cache (cache déterministe
-- partagé) et outbox_events (audit système) — RLS activée avec un gate « session
-- backend » (refus PostgREST anon, accès backend) au lieu d'un scoping tenant.

begin;

-- Rôle de connexion applicatif (non superuser, non BYPASSRLS).
-- Sur Supabase, mapper le user de connexion de l'API sur ce rôle.
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

-- Helper : expression du tenant courant (NULL si non posé).
-- (inline dans les policies ci-dessous ; gardé ici pour référence)
--   nullif(current_setting('app.tenant_id', true), '')::uuid

-- ── Tables avec org_id direct ────────────────────────────────────────────
do $$
declare
    t text;
begin
    foreach t in array array[
        'studies', 'datasets', 'cohort_members', 'cohort_biomarkers',
        'agent_runs', 'simulation_runs', 'simulation_results', 'jobs', 'generated_documents'
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

-- ── orgs : le tenant ne voit que sa propre ligne ─────────────────────────
alter table orgs enable row level security;
alter table orgs force row level security;
create policy tenant_self on orgs
    using (id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- ── memberships : un utilisateur ne voit que SES appartenances ───────────
-- (scopé sur app.user_id, pas app.tenant_id : c'est le bootstrap qui résout
-- justement le tenant à partir de l'utilisateur — cf. core/deps.py)
alter table memberships enable row level security;
alter table memberships force row level security;
create policy member_self on memberships
    using (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
    with check (user_id = nullif(current_setting('app.user_id', true), '')::uuid);

-- ── Tables enfant scopées via leur parent ────────────────────────────────
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

-- ── Corpus : org_id NULL ⇒ global lisible par tous ───────────────────────
alter table documents enable row level security;
alter table documents force row level security;
create policy tenant_or_global on documents
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );

alter table chunks enable row level security;
alter table chunks force row level security;
create policy tenant_or_global on chunks
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );

-- ── usage_events : ligne tenant ou système (org_id NULL) ─────────────────
alter table usage_events enable row level security;
alter table usage_events force row level security;
create policy tenant_or_system on usage_events
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    )
    with check (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );

-- ── Tables infra (non tenant) : RLS « gate session backend » ─────────────
-- agent_cache (cache déterministe partagé) et outbox_events (audit système) ne
-- sont pas scopés tenant, mais ne doivent JAMAIS être atteignables via PostgREST
-- (anon/authenticated, sans app.tenant_id). RLS activée + gate sur la présence
-- du contexte backend : anon refusé, backend (contexte posé) autorisé.
do $$
declare
    t text;
begin
    foreach t in array array['agent_cache', 'outbox_events']
    loop
        execute format('alter table %I enable row level security;', t);
        execute format('alter table %I force row level security;', t);
        execute format($f$
            create policy backend_session on %I
            using (nullif(current_setting('app.tenant_id', true), '') is not null)
            with check (nullif(current_setting('app.tenant_id', true), '') is not null);
        $f$, t);
    end loop;
end
$$;

commit;
