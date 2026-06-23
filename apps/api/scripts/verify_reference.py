"""End-to-end check of the /reference/* endpoints (real-only catalogs).

Starts the real FastAPI app against an already-bootstrapped database (bundle +
seed), mints an HS256 JWT for a user that has a membership, and ensures that
each catalog endpoint returns the seeded data over HTTP. Run it behind
`scripts/verify_reference_live.sh` (which provisions a throwaway database) or
against an existing database with the AUGURA_* in the env (role augura_api, RLS active).

Usage: AUGURA_DATABASE_URL + AUGURA_SUPABASE_JWT_SECRET + AUGURA_ENV=dev,
        then `uv run python scripts/verify_reference.py`.
"""

import asyncio
import os
import time

import jwt
from httpx import ASGITransport, AsyncClient

from augura_api.main import create_app

SECRET = os.environ["AUGURA_SUPABASE_JWT_SECRET"]
USER = "11111111-1111-4111-8111-111111111111"  # must have a memberships row

ENDPOINTS = [
    "/reference/outcomes",
    "/reference/estimands",
    "/reference/estimators",
    "/reference/frameworks",
    "/reference/evidence-types",
    "/reference/domains",
    "/reference/jurisdictions",
    "/reference/literature-study-designs",
    "/reference/dq-rules",
    "/reference/variable-roles",
    "/reference/cesl-sources",
]


def mint() -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": USER,
            "aud": "authenticated",
            "iat": now,
            "exp": now + 3600,
            "email": "verify@augura.dev",
        },
        SECRET,
        algorithm="HS256",
    )


def check(name: str, cond: bool, evidence: str = "") -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + evidence) if evidence else ''}")
    return bool(cond)


async def main() -> int:
    app = create_app()
    h = {"Authorization": f"Bearer {mint()}"}
    ok = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ok &= check(
            "unauthenticated request rejected (401)",
            (await c.get("/reference/outcomes")).status_code == 401,
        )
        data = {}
        for p in ENDPOINTS:
            r = await c.get(p, headers=h)
            ok &= check(f"GET {p} -> 200", r.status_code == 200, f"status={r.status_code}")
            data[p] = r.json() if r.status_code == 200 else None

    out = data.get("/reference/outcomes") or []
    by = {o.get("code"): o for o in out} if isinstance(out, list) else {}
    ok &= check("outcomes: 8 rows", len(out) == 8, f"n={len(out)}")
    ok &= check(
        "outcomes: hba1c_pct + regulatory_tags",
        "hba1c_pct" in by and bool(by["hba1c_pct"].get("regulatory_tags")),
    )
    ok &= check(
        "outcomes: no 'In dataset' tag seeded (derived from the cohort)",
        all("In dataset" not in str(o.get("regulatory_tags")) for o in out),
    )

    est = data.get("/reference/estimators") or []
    eby = {e.get("key"): e for e in est} if isinstance(est, list) else {}
    ok &= check("estimators: 6 rows", len(est) == 6, f"n={len(est)}")
    ok &= check(
        "estimators: lme eligible_study_types == [retro,prosp]",
        eby.get("lme", {}).get("eligible_study_types") == ["retro", "prosp"],
    )
    ok &= check(
        "estimators: ipw eligible_study_types == [retro]",
        eby.get("ipw", {}).get("eligible_study_types") == ["retro"],
    )

    src = data.get("/reference/cesl-sources") or []
    sby = {s.get("code"): s for s in src} if isinstance(src, list) else {}
    ok &= check(
        "cesl-sources: default_evidence_type exposed",
        sby.get("pubmed", {}).get("default_evidence_type") == "rwe_study",
        f"pubmed={sby.get('pubmed', {}).get('default_evidence_type')!r}",
    )

    dq = data.get("/reference/dq-rules") or {}
    ok &= check(
        "dq-rules: pii_patterns + biomarker_ranges",
        bool(dq.get("pii_patterns")) and bool(dq.get("biomarker_ranges")),
        f"pii={len(dq.get('pii_patterns', []))} ranges={len(dq.get('biomarker_ranges', []))}",
    )

    vr = data.get("/reference/variable-roles") or {}
    ok &= check(
        "variable-roles: groups + alias (environment->engagement)",
        any(g.get("code") == "outcomes" for g in vr.get("groups", []))
        and (vr.get("group_aliases") or {}).get("environment") == "engagement",
    )

    for p, n in [
        ("/reference/estimands", 4),
        ("/reference/frameworks", 6),
        ("/reference/evidence-types", 8),
        ("/reference/domains", 17),
        ("/reference/jurisdictions", 7),
        ("/reference/literature-study-designs", 13),
    ]:
        rows = data.get(p) or []
        ok &= check(f"{p}: {n} rows", len(rows) == n, f"n={len(rows)}")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
