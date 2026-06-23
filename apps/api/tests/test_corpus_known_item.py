"""Tier 1a — known-item router + efetch-by-id of the PubMed client.

The classifier is pure (synchronous tests). The real client is tested via
httpx.MockTransport (no network) to inspect the BUILT call: a PMID must go
through efetch `id=`, never through esearch with a title tag.
"""

from typing import cast

import httpx

from augura_api.modules.corpus.known_item import (
    SOURCE_CTGOV,
    SOURCE_PUBMED,
    KnownItemKind,
    classify_known_item,
    resolve_pubmed_known_item,
)
from augura_api.modules.corpus.pubmed import NCBIPubMedClient, PubMedArticle, PubMedClient

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>35319473</PMID>
      <Article>
        <Journal><Title>J Test</Title>
          <JournalIssue><PubDate><Year>2022</Year><Month>Mar</Month></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Exact known-item paper</ArticleTitle>
        <Abstract><AbstractText>An abstract.</AbstractText></Abstract>
      </Article>
      <PublicationTypeList>
        <PublicationType>Randomized Controlled Trial</PublicationType>
      </PublicationTypeList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="doi">10.1/test</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _mock_http(record: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        record.append(request)
        if "efetch" in request.url.path:
            return httpx.Response(200, text=EFETCH_XML)
        if "esearch" in request.url.path:
            return httpx.Response(200, json={"esearchresult": {"idlist": ["35319473"]}})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ── Classifier (pure) ─────────────────────────────────────────────────────────


def test_classify_pmid() -> None:
    item = classify_known_item("  35319473 ")
    assert item is not None
    assert item.kind is KnownItemKind.PMID
    assert item.source == SOURCE_PUBMED
    assert item.value == "35319473"
    assert item.query_string == "efetch:id=35319473"


def test_classify_long_digit_string_is_not_pmid() -> None:
    # 10 digits: outside the PMID range (1–9) → topical (None).
    assert classify_known_item("1234567890") is None


def test_classify_doi_bare_and_url() -> None:
    bare = classify_known_item("10.1001/jama.2020.1585")
    assert bare is not None and bare.kind is KnownItemKind.DOI
    assert bare.query_string == "10.1001/jama.2020.1585[DOI]"

    url = classify_known_item("https://doi.org/10.1001/jama.2020.1585")
    assert url is not None and url.kind is KnownItemKind.DOI
    assert url.value == "10.1001/jama.2020.1585"
    assert url.query_string == "10.1001/jama.2020.1585[DOI]"


def test_classify_quoted_title() -> None:
    item = classify_known_item('"Digital engagement and glycemic control"')
    assert item is not None
    assert item.kind is KnownItemKind.TITLE
    assert item.source == SOURCE_PUBMED
    assert item.query_string == '"Digital engagement and glycemic control"[Title]'


def test_classify_nct_routes_to_ctgov() -> None:
    item = classify_known_item("nct01234567")
    assert item is not None
    assert item.kind is KnownItemKind.NCT
    assert item.source == SOURCE_CTGOV
    assert item.value == "NCT01234567"
    assert item.query_string == "NCT01234567"


def test_classify_topical_and_empty_are_none() -> None:
    assert classify_known_item("digital engagement and hba1c in type 2 diabetes") is None
    assert classify_known_item("   ") is None


# ── Client: efetch-by-id (gate 1) ─────────────────────────────────────────────


async def test_fetch_by_pmid_uses_efetch_not_esearch() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = NCBIPubMedClient(http)
        articles = await client.fetch_by_ids(["35319473"])

    assert len(articles) == 1
    assert articles[0].pmid == "35319473"
    assert articles[0].title == "Exact known-item paper"

    paths = [r.url.path for r in record]
    assert any("efetch" in p for p in paths), "must call efetch"
    assert not any("esearch" in p for p in paths), "must NEVER call esearch"

    efetch = next(r for r in record if "efetch" in r.url.path)
    assert efetch.url.params.get("id") == "35319473"
    assert "[Title]" not in str(efetch.url), "no title tag in an id lookup"


async def test_fetch_by_ids_empty_returns_empty_without_call() -> None:
    record: list[httpx.Request] = []
    async with _mock_http(record) as http:
        client = NCBIPubMedClient(http)
        assert await client.fetch_by_ids(["", "  "]) == []
    assert record == []


# ── PubMed resolver: routing by type ─────────────────────────────────────────


class RecordingPubMed:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def search(self, query: str, max_results: int) -> list[PubMedArticle]:
        self.calls.append(("search", query, max_results))
        return []

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]:
        self.calls.append(("fetch_by_ids", tuple(pmids)))
        return []


async def test_resolve_pmid_calls_fetch_by_ids() -> None:
    fake = RecordingPubMed()
    item = classify_known_item("35319473")
    assert item is not None
    await resolve_pubmed_known_item(item, cast(PubMedClient, fake))
    assert fake.calls == [("fetch_by_ids", ("35319473",))]


async def test_resolve_doi_calls_search_with_doi_tag() -> None:
    fake = RecordingPubMed()
    item = classify_known_item("10.1001/jama.2020.1585")
    assert item is not None
    await resolve_pubmed_known_item(item, cast(PubMedClient, fake))
    assert fake.calls == [("search", "10.1001/jama.2020.1585[DOI]", 1)]


async def test_resolve_title_calls_search_with_title_tag() -> None:
    fake = RecordingPubMed()
    item = classify_known_item('"Some Exact Title"')
    assert item is not None
    await resolve_pubmed_known_item(item, cast(PubMedClient, fake))
    assert fake.calls == [("search", '"Some Exact Title"[Title]', 1)]
