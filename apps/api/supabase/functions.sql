-- Augura Platform — fonctions & vues
-- À appliquer APRÈS schema.sql.

begin;

-- Recherche sémantique sur le corpus (port du RPC match_chunks du front).
-- Scope tenant : chunks du corpus global (org_id NULL) + ceux du tenant courant
-- (app.tenant_id, posé par le backend via SET LOCAL). Filtre optionnel par
-- source_id / evidence_type passé en jsonb.
create or replace function match_chunks(
    query_embedding vector(1536),
    match_count int default 20,
    filter jsonb default '{}'::jsonb
)
returns table (
    id          uuid,
    document_id uuid,
    content     text,
    similarity  float,
    source_id   text,
    title       text
)
language sql
stable
as $$
    select
        c.id,
        c.document_id,
        c.content,
        1 - (c.embedding <=> query_embedding) as similarity,
        d.source_id,
        d.title
    from chunks c
    join documents d on d.id = c.document_id
    where c.embedding is not null
      and (
        c.org_id is null
        or c.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
      )
      and (filter ->> 'source_id' is null or d.source_id = filter ->> 'source_id')
      and (filter ->> 'evidence_type' is null or d.evidence_type = filter ->> 'evidence_type')
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- Matrice de couverture (jurisdiction × evidence_type → doc_count).
-- Les cellules à zéro sont complétées côté service (corpus). gap_score/severity
-- sont dérivés dans le service à partir de doc_count.
create or replace view v_coverage_map as
    select
        coalesce(jurisdiction, 'unknown') as jurisdiction,
        coalesce(evidence_type, 'other')  as evidence_type,
        count(*)                          as doc_count
    from documents
    group by 1, 2;

commit;
