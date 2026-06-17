"""Tier 3 (intégration) — gate 9 : RLS par-étude des `literature_snapshots`.

Exige un Postgres avec le rôle non-BYPASSRLS `augura_app` (schema.sql + policies.sql
appliqués). Tourne contre AUGURA_DATABASE_URL (sauté sinon ; jamais le projet de démo,
cf. conftest). TOUT se passe dans une transaction rollback-ée — aucune donnée laissée.

Le cœur de gate 9 : les snapshots rattachés à une étude sont gatés par `study_members`,
JAMAIS par `study_id` seul. Un `study_id`-only fuiterait entre études du même tenant.

Trois cas vérifiés en tant que rôle `augura_app` (RLS active) :
  1. Un MEMBRE de l'étude lit le snapshot rattaché à l'étude.
  2. Un NON-membre du même tenant ne le lit PAS (fail-closed).
  3. Un snapshot standalone (study_id NULL) n'est lisible que de son créateur.
"""

import json
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from augura_api.core.db import to_asyncpg_url

pytestmark = pytest.mark.integration

TENANT = UUID("aaaaaaaa-0000-4000-8000-0000000000a1")
MEMBER = UUID("bbbbbbbb-0000-4000-8000-0000000000b1")
OUTSIDER = UUID("cccccccc-0000-4000-8000-0000000000c1")


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    raw = await engine.connect()
    trans = await raw.begin()
    try:
        exists = (
            await raw.execute(text("select 1 from pg_roles where rolname = 'augura_app'"))
        ).first()
        if exists is None:
            pytest.skip("rôle augura_app absent — RLS par-étude non testable ici")
        yield raw
    finally:
        await trans.rollback()  # ne laisse AUCUNE donnée, quel que soit l'état
        await raw.close()
        await engine.dispose()


async def _seed(conn: AsyncConnection) -> tuple[UUID, UUID, UUID]:
    """Crée org + étude + appartenance (MEMBER) + 3 snapshots, en rôle privilégié
    (avant tout `set role`). Retourne (study_snap, member_standalone, outsider_standalone)."""
    suffix = uuid4().hex[:8]
    study_id = uuid4()
    await conn.execute(
        text("insert into orgs (id, name, slug) values (cast(:t as uuid), :n, :s)").bindparams(
            t=str(TENANT), n=f"RLS test {suffix}", s=f"rls-{suffix}"
        )
    )
    await conn.execute(
        text(
            "insert into studies (id, org_id, name, slug) "
            "values (cast(:sid as uuid), cast(:t as uuid), :n, :sl)"
        ).bindparams(sid=str(study_id), t=str(TENANT), n="Gate9 study", sl=f"gate9-{suffix}")
    )
    await conn.execute(
        text(
            "insert into study_members (study_id, user_id, role) "
            "values (cast(:sid as uuid), cast(:u as uuid), 'member')"
        ).bindparams(sid=str(study_id), u=str(MEMBER))
    )

    async def _snap(study: UUID | None, creator: UUID) -> UUID:
        sid = uuid4()
        payload = json.dumps({"query": "q", "results": []})
        await conn.execute(
            text(
                "insert into literature_snapshots "
                "(id, org_id, study_id, created_by, payload, content_hash) values "
                "(cast(:id as uuid), cast(:t as uuid), :study, cast(:c as uuid), "
                " cast(:p as jsonb), :h)"
            ).bindparams(
                id=str(sid),
                t=str(TENANT),
                study=str(study) if study else None,
                c=str(creator),
                p=payload,
                h=f"hash-{sid.hex}",
            )
        )
        return sid

    study_snap = await _snap(study_id, MEMBER)
    member_standalone = await _snap(None, MEMBER)
    outsider_standalone = await _snap(None, OUTSIDER)
    return study_snap, member_standalone, outsider_standalone


async def _visible(conn: AsyncConnection, *, user: UUID) -> set[UUID]:
    """IDs des snapshots visibles pour `user` dans TENANT, sous RLS (rôle augura_app)."""
    await conn.execute(
        text("select set_config('app.tenant_id', :t, true)").bindparams(t=str(TENANT))
    )
    await conn.execute(text("select set_config('app.user_id', :u, true)").bindparams(u=str(user)))
    rows = (
        await conn.execute(
            text("select id from literature_snapshots where org_id = cast(:t as uuid)").bindparams(
                t=str(TENANT)
            )
        )
    ).all()
    return {r[0] for r in rows}


async def test_gate9_per_study_visibility(conn: AsyncConnection) -> None:
    study_snap, member_standalone, outsider_standalone = await _seed(conn)

    # Bascule en rôle applicatif non-BYPASSRLS : à partir d'ici la RLS s'applique.
    await conn.execute(text("set local role augura_app"))

    # Cas 1 & 3 (côté membre) : le membre voit le snapshot d'étude ET son standalone,
    # mais PAS le standalone d'un autre utilisateur.
    member_view = await _visible(conn, user=MEMBER)
    assert study_snap in member_view, "le membre doit voir le snapshot rattaché à l'étude"
    assert member_standalone in member_view, "le membre doit voir son propre standalone"
    assert outsider_standalone not in member_view, "standalone d'autrui invisible"

    # Cas 2 (fail-closed) : un non-membre du MÊME tenant ne voit PAS le snapshot
    # d'étude — c'est le gating par study_members, pas par study_id seul.
    outsider_view = await _visible(conn, user=OUTSIDER)
    assert study_snap not in outsider_view, "FUITE gate 9 : non-membre voit un snapshot d'étude"
    assert member_standalone not in outsider_view, "standalone d'autrui invisible"
    assert outsider_standalone in outsider_view, "l'outsider voit son propre standalone"


async def test_gate9_write_check_blocks_non_member_study_write(conn: AsyncConnection) -> None:
    """WITH CHECK : on ne peut pas geler un snapshot dans une étude dont on n'est pas
    membre (même tenant). L'INSERT doit être refusé par la RLS."""
    suffix = uuid4().hex[:8]
    study_id = uuid4()
    await conn.execute(
        text("insert into orgs (id, name, slug) values (cast(:t as uuid), :n, :s)").bindparams(
            t=str(TENANT), n=f"RLS wc {suffix}", s=f"rlswc-{suffix}"
        )
    )
    await conn.execute(
        text(
            "insert into studies (id, org_id, name, slug) "
            "values (cast(:sid as uuid), cast(:t as uuid), :n, :sl)"
        ).bindparams(sid=str(study_id), t=str(TENANT), n="WC study", sl=f"wc-{suffix}")
    )
    # MEMBER n'est PAS ajouté à study_members → OUTSIDER (= n'importe qui) n'est pas membre.

    await conn.execute(text("set local role augura_app"))
    await conn.execute(
        text("select set_config('app.tenant_id', :t, true)").bindparams(t=str(TENANT))
    )
    await conn.execute(
        text("select set_config('app.user_id', :u, true)").bindparams(u=str(OUTSIDER))
    )

    with pytest.raises(DBAPIError):  # RLS WITH CHECK violation (SQLSTATE 42501)
        await conn.execute(
            text(
                "insert into literature_snapshots "
                "(org_id, study_id, created_by, payload, content_hash) values "
                "(cast(:t as uuid), cast(:sid as uuid), cast(:u as uuid), "
                " '{}'::jsonb, 'h')"
            ).bindparams(t=str(TENANT), sid=str(study_id), u=str(OUTSIDER))
        )
