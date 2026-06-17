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

-- Rôle de connexion (LOGIN) que porte l'API (AUGURA_DATABASE_URL = augura_api…).
-- Hérite de augura_app ; NON superuser / NON BYPASSRLS ⇒ la RLS s'applique.
-- Le mot de passe est posé hors-bundle (Supabase). Ce grant rend le bundle
-- autonome : sans lui, un projet reconstruit n'aurait AUCUN privilège de table.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'augura_api') then
        create role augura_api login;
    end if;
end
$$;
grant augura_app to augura_api;

-- Verrouillage des grants Supabase par défaut (PostgREST). Tout l'accès données
-- passe par le backend (rôle augura_app) ; anon/authenticated ne doivent pas
-- lire/écrire les tables directement. On retire les privilèges par défaut puis on
-- re-grante l'unique écriture directe légitime : l'INSERT des events de login par
-- le front (App.jsx) en rôle authenticated.
-- Gardé par existence : anon/authenticated sont propres à Supabase ; sur un Postgres
-- nu (CI pgvector, alembic upgrade head) ces rôles n'existent pas → no-op.
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
        grant insert on usage_events to authenticated;
    end if;
end
$$;
-- NOTE: authenticated conserve SELECT pour l'instant — quelques vues cockpit lisent
-- encore via PostgREST direct (migration backend = P7). À révoquer une fois ces vues
-- branchées sur le backend, pour que TOUT l'accès données passe par augura_app.

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
    )
    -- Lecture : global OU tenant. Écriture : strictement tenant courant — les lignes
    -- globales (org_id NULL, visibles de tous) ne s'ingèrent que via un rôle privilégié
    -- (seed/worker BYPASSRLS), jamais depuis une session tenant.
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

alter table chunks enable row level security;
alter table chunks force row level security;
create policy tenant_or_global on chunks
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    )
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

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

-- ── Catalogues de référence (cesl_sources, cesl_study_designs) ────────────
-- Globaux, lecture seule pour les sessions tenant. RLS activée + gate « session
-- backend » en LECTURE uniquement (FOR SELECT) : anon/PostgREST refusé, backend
-- (app.tenant_id posé) autorisé en lecture. Aucune policy d'écriture ⇒ INSERT/
-- UPDATE/DELETE refusés pour augura_app ; le seed entre via le rôle privilégié.
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

-- ── Reference catalogs (frontend real-only cleanup) : global, lecture seule ──
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

-- ── Taxonomie sémantique (A1) : globale, lecture seule (FOR SELECT) ───────
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

-- ── dq_bundles (A3a) : tenant-scopé via org_id ───────────────────────────
alter table dq_bundles enable row level security;
alter table dq_bundles force row level security;
create policy tenant_isolation on dq_bundles
    using (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
    with check (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- ── Corpus live (retrieve-and-freeze) ─────────────────────────────────────
-- search_sessions / literature_events / literature_queries : isolation tenant
-- simple (org_id = app.tenant_id), comme la base de 0002.
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

-- ── literature_snapshots : isolation tenant + visibilité PAR ÉTUDE (Tier 3) ──
-- L'isolation tenant (org_id) reste le premier rempart. Par-dessus, l'accès est
-- gaté ainsi :
--   • study_id NON NULL ⇒ visible aux MEMBRES de l'étude (study_members), PAS à
--     tout le tenant. C'est le point critique (gate 9) : on gate par study_members,
--     jamais par study_id seul — sinon un snapshot fuiterait entre études du même
--     tenant. Un non-membre échoue fermé (l'EXISTS est faux ⇒ ligne invisible).
--   • study_id NULL ⇒ snapshot standalone, visible de son seul créateur.
-- created_by est enregistré mais n'est PAS le gate pour les snapshots d'étude.
-- WITH CHECK : on n'écrit que pour le tenant courant, en tant que créateur, et —
-- si rattaché à une étude — seulement si on en est membre (pas d'écriture dans
-- l'étude d'autrui). app.user_id non posé ⇒ tout échoue fermé.
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

commit;
