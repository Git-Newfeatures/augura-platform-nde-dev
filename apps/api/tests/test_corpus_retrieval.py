"""Tier 1c — multi-source fan-out (retrieve-only) + query_string capture.

Recording fake clients (no network). Checks: known-item routing to the
identifier's single source, topical fan-out over both sources, query_string
capture per result, and the hard rule "no topical fallback on a miss".
"""

from datetime import date
from typing import cast

import pytest

from augura_api.core.errors import BadRequestError
from augura_api.core.llm.runtime import AgentUpstreamError
from augura_api.modules.corpus.ctgov import CTGovClient, CTGovStudy
from augura_api.modules.corpus.curation import CuratedRef, CurationCandidate
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


class FakeCurator:
    """Returns the ids in reverse order of receipt, with a rationale, and can
    simulate a failure (raise) or a partial selection."""

    def __init__(self, *, error: Exception | None = None, only: list[str] | None = None) -> None:
        self.error = error
        self.only = only
        self.calls: list[tuple[str, str, int]] = []  # (source, first id, num candidates)

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        first = candidates[0].id if candidates else ""
        self.calls.append((source, first, len(candidates)))
        if self.error is not None:
            raise self.error
        ids = [c.id for c in candidates]
        if self.only is not None:
            ids = [i for i in ids if i in self.only]
        return [CuratedRef(id=i, rationale=f"rat-{i}") for i in reversed(ids)]


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
    # query_string captured per result == that of the group
    assert pmg.items[0].id == "35319473"
    assert pmg.items[0].query_string == "engagement and hba1c"
    assert ctg.items[0].id == "NCT01691846"
    assert ctg.items[0].query_string == "query.term=engagement and hba1c"
    # structured record present
    assert pmg.items[0].record["pmid"] == "35319473"
    assert ctg.items[0].record["nct_id"] == "NCT01691846"
    # both were searched (topical), no known-item fetch
    assert pm.calls == [("search", "engagement and hba1c", 5)]
    assert ct.calls == [("search", "engagement and hba1c", 5)]


async def test_topical_isolates_failing_source() -> None:
    # CT.gov fails (e.g. 403 WAF from a datacenter IP): PubMed must still come
    # through and CT.gov returns an annotated empty group — NEVER an exception
    # that would crash the whole fan-out (and tear the stream → 'network error').
    pm = FakePubMed(search_res=[ART])
    ct = FakeCTGov(search_error=RuntimeError("403 Forbidden"))
    r = await _retriever(pm, ct).retrieve("hypertension telemonitoring", max_results=5, today=DAY)

    assert r.sources == [SOURCE_PUBMED, SOURCE_CTGOV]  # order preserved
    by_source = {g.source: g for g in r.groups}
    assert by_source[SOURCE_PUBMED].items[0].id == "35319473"  # PubMed intact
    assert by_source[SOURCE_CTGOV].items == []  # failing source → empty
    assert by_source[SOURCE_CTGOV].note  # unavailability note present


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
    # efetch by id, and CT.gov never queried
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
    ct = FakeCTGov(fetch_res=None)  # unknown NCT → miss
    r = await _retriever(pm, ct).retrieve("NCT99999999", today=DAY)

    g = r.groups[0]
    assert g.items == []
    assert g.note == KNOWN_ITEM_MISS_MESSAGE
    # NO fallback: only the known-item fetch, no topical search
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
    # NCT (ctgov) but only PubMed selected → nothing queried
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

    # the filters reach both clients
    assert pm.last_filters == filters
    assert ct.last_filters == filters
    # the captured query_string reflects the filtered PubMed term (for freezing)
    pmg = r.groups[0]
    assert pmg.query_string == ("(engagement and hba1c) AND (Randomized Controlled Trial[pt])")
    assert pmg.items[0].query_string == pmg.query_string


# ---------------------------------------------------------------------------
# Curation tests
# ---------------------------------------------------------------------------

ART2 = PubMedArticle(
    pmid="40000000",
    title="PubMed paper 2",
    abstract="abstract2",
    url="https://doi.org/10.1/y",
    evidence_type="review",
)
STUDY2 = CTGovStudy(
    nct_id="NCT02000000",
    title="CT study 2",
    status="RECRUITING",
    phase="PHASE2",
    conditions=("Hypertension",),
    interventions=("drug",),
    url="https://clinicaltrials.gov/study/NCT02000000",
)


def _retriever_c(pm: FakePubMed, ct: FakeCTGov, cur: FakeCurator) -> LiteratureRetriever:
    return LiteratureRetriever(cast(PubMedClient, pm), cast(CTGovClient, ct), curator=cur)


async def test_curation_reorders_and_annotates_both_sources() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[STUDY, STUDY2])
    cur = FakeCurator()  # reverses the order
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["40000000", "35319473"]
    assert pmg.items[0].rationale == "rat-40000000"
    ctg = next(g for g in r.groups if g.source == SOURCE_CTGOV)
    assert [i.id for i in ctg.items] == ["NCT02000000", "NCT01691846"]
    assert ctg.items[0].rationale == "rat-NCT02000000"
    assert pm.calls == [("search", "hba1c", 25)]  # pool = min(50, max(25, 5*2)) = 25
    assert ct.calls == [("search", "hba1c", 25)]


async def test_curation_failure_falls_back_to_relevance_order() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator(error=AgentUpstreamError("LLM down"))
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]
    assert all(i.rationale is None for i in pmg.items)


async def test_curation_empty_selection_falls_back() -> None:
    pm = FakePubMed(search_res=[ART, ART2])
    ct = FakeCTGov(search_res=[])
    cur = FakeCurator(only=["zzz"])  # nothing matches
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=5, today=DAY)
    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["35319473", "40000000"]
    assert all(i.rationale is None for i in pmg.items)


async def test_known_item_is_not_curated() -> None:
    pm = FakePubMed(fetch_res=[ART])
    ct = FakeCTGov(search_res=[STUDY])
    cur = FakeCurator()
    r = await _retriever_c(pm, ct, cur).retrieve("35319473", today=DAY)
    assert cur.calls == []
    assert r.groups[0].items[0].rationale is None


async def test_curation_caps_at_max_results_end_to_end() -> None:
    # The curator returns 3 refs without capping; the cap to max_results must apply
    # end-to-end (via apply_curation in _curate_pubmed), not only in the helper.
    art3 = PubMedArticle(
        pmid="50000000",
        title="P3",
        abstract="a3",
        url="https://doi.org/10.1/z",
        evidence_type="rct",
    )
    pm = FakePubMed(search_res=[ART, ART2, art3])
    ct = FakeCTGov(search_res=[])
    cur = FakeCurator()  # returns the 3 ids reversed
    r = await _retriever_c(pm, ct, cur).retrieve("hba1c", max_results=2, today=DAY)

    pmg = next(g for g in r.groups if g.source == SOURCE_PUBMED)
    assert [i.id for i in pmg.items] == ["50000000", "40000000"]  # reversed then capped to 2
