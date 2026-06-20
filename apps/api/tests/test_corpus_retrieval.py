"""Tier 1c — fan-out multi-sources (retrieve-only) + capture du query_string.

Clients factices enregistreurs (aucun réseau). Vérifie : routage known-item vers
la seule source de l'identifiant, fan-out topique sur les deux sources, capture du
query_string par résultat, et la règle dure « pas de repli topique sur un miss ».
"""

from datetime import date
from typing import cast

import pytest

from augura_api.core.errors import BadRequestError
from augura_api.modules.corpus.ctgov import CTGovClient, CTGovStudy
from augura_api.modules.corpus.filters import SearchFilters
from augura_api.modules.corpus.known_item import (
    KNOWN_ITEM_MISS_MESSAGE,
    SOURCE_CTGOV,
    SOURCE_PUBMED,
)
from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient
from augura_api.modules.corpus.retrieval import LiteratureRetriever

DAY = date(2026, 6, 16)

ART = PubMedArticle(
    pmid="35319473",
    title="PubMed paper",
    abstract="abstract",
    url="https://doi.org/10.1/x",
    evidence_type="rct",
    published_at=date(2022, 3, 1),
    doi="10.1/x",
    journal="J Test",
)
STUDY = CTGovStudy(
    nct_id="NCT01691846",
    title="CT study",
    status="COMPLETED",
    phase="PHASE3",
    conditions=("Type 2 Diabetes",),
    interventions=("metformin",),
    url="https://clinicaltrials.gov/study/NCT01691846",
)


class FakePubMed:
    def __init__(
        self,
        *,
        search_res: list[PubMedArticle] | None = None,
        fetch_res: list[PubMedArticle] | None = None,
    ) -> None:
        self.search_res = search_res or []
        self.fetch_res = fetch_res or []
        self.calls: list[tuple[object, ...]] = []
        self.last_filters: object = None

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: object = None,
        today: object = None,
    ) -> list[PubMedArticle]:
        self.calls.append(("search", query, max_results))
        self.last_filters = filters
        return self.search_res

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]:
        self.calls.append(("fetch_by_ids", tuple(pmids)))
        return self.fetch_res


class FakeCTGov:
    def __init__(
        self,
        *,
        search_res: list[CTGovStudy] | None = None,
        fetch_res: CTGovStudy | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self.search_res = search_res or []
        self.fetch_res = fetch_res
        self.search_error = search_error
        self.calls: list[tuple[object, ...]] = []
        self.last_filters: object = None

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: object = None,
        today: object = None,
    ) -> list[CTGovStudy]:
        self.calls.append(("search", query, max_results))
        self.last_filters = filters
        if self.search_error is not None:
            raise self.search_error
        return self.search_res

    async def fetch_by_nct(self, nct_id: str) -> CTGovStudy | None:
        self.calls.append(("fetch_by_nct", nct_id))
        return self.fetch_res


def _retriever(pm: FakePubMed, ct: FakeCTGov) -> LiteratureRetriever:
    return LiteratureRetriever(cast(PubMedClient, pm), cast(CTGovClient, ct))


async def test_topical_fans_out_to_both_sources() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    r = await _retriever(pm, ct).retrieve("engagement and hba1c", max_results=5, today=DAY)

    assert r.known_item is False
    assert r.kind is None
    assert r.sources == [SOURCE_PUBMED, SOURCE_CTGOV]
    assert [g.source for g in r.groups] == [SOURCE_PUBMED, SOURCE_CTGOV]

    pmg, ctg = r.groups[0], r.groups[1]
    assert pmg.query_string == "engagement and hba1c"
    assert ctg.query_string == "query.term=engagement and hba1c"
    # query_string capturé par résultat == celui du groupe
    assert pmg.items[0].id == "35319473"
    assert pmg.items[0].query_string == "engagement and hba1c"
    assert ctg.items[0].id == "NCT01691846"
    assert ctg.items[0].query_string == "query.term=engagement and hba1c"
    # enregistrement structuré présent
    assert pmg.items[0].record["pmid"] == "35319473"
    assert ctg.items[0].record["nct_id"] == "NCT01691846"
    # les deux ont été cherchés (topique), aucun fetch known-item
    assert pm.calls == [("search", "engagement and hba1c", 5)]
    assert ct.calls == [("search", "engagement and hba1c", 5)]


async def test_topical_isolates_failing_source() -> None:
    # CT.gov échoue (ex. 403 WAF depuis une IP datacenter) : PubMed doit quand même
    # remonter et CT.gov renvoie un groupe vide annoté — JAMAIS une exception qui
    # ferait planter tout le fan-out (et déchirerait le stream → 'network error').
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_error=RuntimeError("403 Forbidden"))
    r = await _retriever(pm, ct).retrieve("hypertension telemonitoring", max_results=5, today=DAY)

    assert r.sources == [SOURCE_PUBMED, SOURCE_CTGOV]  # ordre préservé
    by_source = {g.source: g for g in r.groups}
    assert by_source[SOURCE_PUBMED].items[0].id == "35319473"  # PubMed intact
    assert by_source[SOURCE_CTGOV].items == []  # source en échec → vide
    assert by_source[SOURCE_CTGOV].note  # note d'indisponibilité présente


async def test_known_item_pmid_routes_to_pubmed_fetch_only() -> None:
    pm = FakePubMed(fetch_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    r = await _retriever(pm, ct).retrieve("35319473", today=DAY)

    assert r.known_item is True
    assert r.kind == "pmid"
    assert r.sources == [SOURCE_PUBMED]
    assert len(r.groups) == 1
    g = r.groups[0]
    assert g.source == SOURCE_PUBMED
    assert g.query_string == "efetch:id=35319473"
    assert g.items[0].query_string == "efetch:id=35319473"
    # efetch par id, et CT.gov jamais sollicité
    assert pm.calls == [("fetch_by_ids", ("35319473",))]
    assert ct.calls == []


async def test_known_item_nct_routes_to_ctgov_only() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(fetch_res=STUDY)
    r = await _retriever(pm, ct).retrieve("NCT01691846", today=DAY)

    assert r.kind == "nct"
    assert r.sources == [SOURCE_CTGOV]
    g = r.groups[0]
    assert g.source == SOURCE_CTGOV
    assert g.items[0].id == "NCT01691846"
    assert g.items[0].query_string == "NCT01691846"
    assert ct.calls == [("fetch_by_nct", "NCT01691846")]
    assert pm.calls == []


async def test_known_item_miss_returns_note_no_topical_fallback() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(fetch_res=None)  # NCT inconnu → miss
    r = await _retriever(pm, ct).retrieve("NCT99999999", today=DAY)

    g = r.groups[0]
    assert g.items == []
    assert g.note == KNOWN_ITEM_MISS_MESSAGE
    # PAS de repli : seulement le fetch known-item, aucune recherche topique
    assert ct.calls == [("fetch_by_nct", "NCT99999999")]
    assert pm.calls == []


async def test_sources_restriction_pubmed_only() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    r = await _retriever(pm, ct).retrieve("hba1c", sources={SOURCE_PUBMED}, today=DAY)

    assert r.sources == [SOURCE_PUBMED]
    assert [g.source for g in r.groups] == [SOURCE_PUBMED]
    assert ct.calls == []


async def test_known_item_source_not_selected_returns_empty() -> None:
    pm = FakePubMed()
    ct = FakeCTGov(fetch_res=STUDY)
    # NCT (ctgov) mais seul PubMed sélectionné → rien interrogé
    r = await _retriever(pm, ct).retrieve("NCT01691846", sources={SOURCE_PUBMED}, today=DAY)

    assert r.known_item is True
    assert r.groups == []
    assert pm.calls == []
    assert ct.calls == []


async def test_invalid_source_raises() -> None:
    pm = FakePubMed()
    ct = FakeCTGov()
    with pytest.raises(BadRequestError):
        await _retriever(pm, ct).retrieve("hba1c", sources={"embase"}, today=DAY)


async def test_topical_passes_filters_to_clients_and_captures_term() -> None:
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    filters = SearchFilters(date_range="5y", study_types=("rct",))
    r = await _retriever(pm, ct).retrieve(
        "engagement and hba1c", max_results=5, today=DAY, filters=filters
    )

    # les filtres atteignent les deux clients
    assert pm.last_filters == filters
    assert ct.last_filters == filters
    # le query_string capturé reflète le terme PubMed filtré (pour le gel)
    pmg = r.groups[0]
    assert pmg.query_string == ("(engagement and hba1c) AND (Randomized Controlled Trial[pt])")
    assert pmg.items[0].query_string == pmg.query_string
