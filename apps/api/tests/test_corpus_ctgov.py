"""Tier 1b — client ClinicalTrials.gov API v2.

httpx.MockTransport (aucun réseau). Les payloads reproduisent la forme confirmée
par sonde : recherche enveloppée dans `studies[]`, fetch par NCT au niveau racine,
404 pour un NCT inconnu.
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
    # fetch direct par id, sans passer par la recherche topique
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
