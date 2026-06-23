"""Tier 3 (integration) — gate 9: per-study RLS of `literature_snapshots`.

Requires a Postgres with the non-BYPASSRLS role `augura_app` (schema.sql + policies.sql
applied). Runs against AUGURA_DATABASE_URL (skipped otherwise; never the demo project,
see conftest). EVERYTHING runs in a rolled-back transaction — no data left behind.

The core of gate 9: snapshots attached to a study are gated by `study_members`,
NEVER by `study_id` alone. A `study_id`-only check would leak across studies of the same tenant.

Three cases verified as the `augura_app` role (RLS active):
  1. A MEMBER of the study reads the snapshot attached to the study.
  2. A NON-member of the same tenant does NOT read it (fail-closed).
  3. A standalone snapshot (study_id NULL) is readable only by its creator.
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
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    raw = await engine.connect()
    trans = await raw.begin()
    try:
        exists = (
            await raw.execute(text("select 1 from pg_roles where rolname = 'augura_app'"))
        ).first()
        if exists is None:
            pytest.skip("augura_app role missing — per-study RLS not testable here")
        yield raw
    finally:
        await trans.rollback()  # leaves NO data behind, whatever the state
        await raw.close()
        await engine.dispose()


async def _seed(conn: AsyncConnection) -> tuple[UUID, UUID, UUID]:
    """Create org + study + membership (MEMBER) + 3 snapshots, as privileged role
    (before any `set role`). Returns (study_snap, member_standalone, outsider_standalone)."""
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
    """IDs of snapshots visible to `user` in TENANT, under RLS (augura_app role)."""
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

    # Switch to the non-BYPASSRLS application role: from here on RLS applies.
    await conn.execute(text("set local role augura_app"))

    # Cases 1 & 3 (member side): the member sees the study snapshot AND their standalone,
    # but NOT another user's standalone.
    member_view = await _visible(conn, user=MEMBER)
    assert study_snap in member_view, "the member must see the snapshot attached to the study"
    assert member_standalone in member_view, "the member must see their own standalone"
    assert outsider_standalone not in member_view, "another user's standalone is invisible"

    # Case 2 (fail-closed): a non-member of the SAME tenant does NOT see the study
    # snapshot — gating is by study_members, not by study_id alone.
    outsider_view = await _visible(conn, user=OUTSIDER)
    assert study_snap not in outsider_view, "gate 9 LEAK: non-member sees a study snapshot"
    assert member_standalone not in outsider_view, "another user's standalone is invisible"
    assert outsider_standalone in outsider_view, "the outsider sees their own standalone"


async def test_gate9_write_check_blocks_non_member_study_write(conn: AsyncConnection) -> None:
    """WITH CHECK: you cannot freeze a snapshot into a study you are not a member
    of (same tenant). The INSERT must be rejected by RLS."""
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
    # MEMBER is NOT added to study_members → OUTSIDER (= anyone) is not a member.

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
