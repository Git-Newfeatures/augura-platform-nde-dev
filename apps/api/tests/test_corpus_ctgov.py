"""Tier 1b — ClinicalTrials.gov API v2 client.

httpx.MockTransport (no network). The payloads reproduce the probe-confirmed
shape: search wrapped in `studies[]`, fetch by NCT at the root level,
404 for an unknown NCT.
"""

from datetime import date as _date

import httpx

from augura_api.modules.corpus.ctgov import CTGovApiClient
from augura_api.modules.corpus.filters import SearchFilters

_PROTOCOL = {
    "identificationModule": {
        "nctId": "NCT01691846",
        "briefTitle": "Aleglitazar + Metformin in Type 2 Diabetes",
    },
    "statusModule": {"overallStatus": "COMPLETED"},
    "designModule": {"phases": ["PHASE3"]},
    "conditionsModule": {"conditions": ["Diabetes Mellitus Type 2"]},
    "armsInterventionsModule": {
        "interventions": [{"name": "aleglitazar+metformin"}, {"name": "placebo+metformin"}]
    },
}


def _mock_http(record: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        record.append(request)
        path = request.url.path
        if path.endswith("/NCT01691846"):
            return httpx.Response(200, json={"protocolSection": _PROTOCOL, "hasResults": True})
        if path.endswith("/NCT99999999"):
            return httpx.Response(404, json={"message": "not found"})
        if path.endswith("/studies"):
            return httpx.Response(200, json={"studies": [{"protocolSection": _PROTOCOL}]})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_search_parses_fields_and_uses_query_term() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        studies = await client.search("type 2 diabetes metformin", 5)

    assert len(studies) == 1
    s = studies[0]
    assert s.nct_id == "NCT01691846"
    assert s.status == "COMPLETED"
    assert s.phase == "PHASE3"
    assert s.conditions == ("Diabetes Mellitus Type 2",)
    assert s.interventions == ("aleglitazar+metformin", "placebo+metformin")
    assert s.url == "https://clinicaltrials.gov/study/NCT01691846"

    req = record[0]
    assert req.url.path == "/api/v2/studies"
    assert req.url.params.get("query.term") == "type 2 diabetes metformin"
    assert req.url.params.get("pageSize") == "5"


async def test_fetch_by_nct_known_item() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        study = await client.fetch_by_nct("nct01691846")

    assert study is not None
    assert study.nct_id == "NCT01691846"
    assert study.title.startswith("Aleglitazar")
    # direct fetch by id, without going through topical search
    assert record[0].url.path == "/api/v2/studies/NCT01691846"


async def test_fetch_by_nct_miss_returns_none() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        assert await client.fetch_by_nct("NCT99999999") is None


async def test_fetch_by_nct_empty_returns_none_without_call() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        assert await client.fetch_by_nct("   ") is None
    assert record == []


async def test_search_applies_filters_to_params() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = CTGovApiClient(http)
        await client.search(
            "diabetes",
            5,
            filters=SearchFilters(date_range="1y", study_types=("observational",)),
            today=_date(2026, 6, 19),
        )

    params = record[0].url.params
    assert params.get("query.term") == "diabetes"
    assert params.get("aggFilters") == "studyType:obs"
    assert params.get("filter.advanced") == "AREA[StudyFirstPostDate]RANGE[2025-01-01,MAX]"


async def test_base_url_override_targets_relay() -> None:
    # base_url (Vercel relay) must replace the CT.gov host while still forwarding
    # the query params — this is the workaround for the WAF 403 on datacenter IPs.
    record: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        record.append(request)
        return httpx.Response(200, json={"studies": [{"protocolSection": _PROTOCOL}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = CTGovApiClient(http, base_url="https://relay.example/api/ctgov")
        studies = await client.search("hypertension", 3)

    assert studies and studies[0].nct_id == "NCT01691846"
    req = record[0]
    assert req.url.host == "relay.example"
    assert req.url.path == "/api/ctgov"
    assert req.url.params.get("query.term") == "hypertension"
