"""Câblage du module studies dans l'app (sans base : auth échoue avant la DB)."""

import httpx

from augura_api.main import create_app


def test_openapi_exposes_routes() -> None:
    paths = create_app().openapi()["paths"]
    for path in (
        "/studies",
        "/studies/{study_id}",
        "/studies/{study_id}/state",
        "/corpus/feed",
        "/corpus/coverage",
        "/corpus/sources",
        "/corpus/search",
        "/datasets",
        "/datasets/upload",
        "/datasets/{dataset_id}",
        "/datasets/{dataset_id}/columns",
        "/datasets/cohorts",
        "/datasets/cohorts/{cohort_name}/members",
        "/datasets/cohorts/{cohort_name}/biomarkers",
        "/agents/dag",
        "/agents/gaps",
        "/agents/variable-check",
        "/agents/profiling/stream",
        "/simulations/power",
        "/simulations/results",
        "/simulations",
        "/jobs/{job_id}",
        "/documents",
        "/documents/{document_id}",
        "/datasets/{dataset_id}/dq",
        "/analytics/admin",
        "/reference/tenant",
        "/reference/cesl-sources",
        "/reference/study-designs",
        "/semantic/concepts",
        "/semantic/relations",
        "/semantic/bundle",
        "/semantic/release",
        "/datasets/{dataset_id}/map",
        "/causal/dag",
        "/semantic/enrich/apply",
        "/semantic/enrich/propose",
        "/semantic/enrich/proposals/{job_id}",
    ):
        assert path in paths, path


def test_openapi_exposes_reference_catalogs() -> None:
    paths = create_app().openapi()["paths"]
    for path in (
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
    ):
        assert path in paths, f"missing route: {path}"


async def test_reference_catalogs_require_auth() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/reference/outcomes", "/reference/dq-rules", "/reference/variable-roles"):
            r = await client.get(path)
            assert r.status_code == 401, path
            assert r.headers["content-type"] == "application/problem+json"
            assert r.json()["code"] == "unauthorized"


async def test_protected_routes_require_auth() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/studies",
            "/corpus/feed",
            "/datasets",
            "/datasets/cohorts",
            "/datasets/{dataset_id}/dq",
            "/reference/tenant",
            "/semantic/concepts",
            "/semantic/relations",
            "/semantic/bundle",
            "/semantic/release",
        ):
            r = await client.get(path)
            assert r.status_code == 401, path
            assert r.headers["content-type"] == "application/problem+json"
            assert r.json()["code"] == "unauthorized"
        # POST-only routes: verify auth guard fires on the correct method
        for path in ("/datasets/{dataset_id}/map",):
            r = await client.post(path)
            assert r.status_code == 401, path
            assert r.headers["content-type"] == "application/problem+json"
            assert r.json()["code"] == "unauthorized"
        # POST routes with a body : corps valide vide ⇒ l'auth (401) précède le métier.
        for path in ("/causal/dag", "/semantic/enrich/apply", "/semantic/enrich/propose"):
            r = await client.post(path, json={})
            assert r.status_code == 401, path
            assert r.json()["code"] == "unauthorized"
        # GET routes avec paramètre de chemin : l'auth (401) précède la résolution.
        for path in ("/semantic/enrich/proposals/00000000-0000-0000-0000-000000000000",):
            r = await client.get(path)
            assert r.status_code == 401, path
            assert r.json()["code"] == "unauthorized"
