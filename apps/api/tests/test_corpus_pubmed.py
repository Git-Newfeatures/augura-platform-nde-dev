"""NCBIPubMedClient: esearch + efetch + XML parsing, no network (httpx MockTransport)."""

from datetime import date
from datetime import date as _date

import httpx

from augura_api.modules.corpus.filters import SearchFilters
from augura_api.modules.corpus.pubmed import NCBIPubMedClient

_ESEARCH = {"esearchresult": {"idlist": ["111", "222"]}}

_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <Journal><Title>JAMA Network Open</Title>
          <JournalIssue><PubDate><Year>2023</Year><Month>Dec</Month><Day>01</Day></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Digital engagement and glycemic control: a randomized trial.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Engagement matters.</AbstractText>
          <AbstractText Label="RESULTS">HbA1c improved.</AbstractText>
        </Abstract>
        <PublicationTypeList>
          <PublicationType>Randomized Controlled Trial</PublicationType>
          <PublicationType>Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList>
      <ArticleId IdType="pubmed">111</ArticleId>
      <ArticleId IdType="doi">10.1001/jamanetworkopen.2023.40232</ArticleId>
    </ArticleIdList></PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article>
        <Journal><Title>Diabetes Care</Title>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>A narrative review of RPM.</ArticleTitle>
        <Abstract><AbstractText>Overview.</AbstractText></Abstract>
        <PublicationTypeList><PublicationType>Review</PublicationType></PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList>
      <ArticleId IdType="pubmed">222</ArticleId>
    </ArticleIdList></PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""


def _handler(request: httpx.Request) -> httpx.Response:
    if "esearch" in request.url.path:
        assert request.url.params.get("db") == "pubmed"
        return httpx.Response(200, json=_ESEARCH)
    if "efetch" in request.url.path:
        assert request.url.params.get("id") == "111,222"
        return httpx.Response(200, text=_EFETCH_XML)
    return httpx.Response(404)


async def test_search_parses_articles() -> None:
    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        articles = await NCBIPubMedClient(http).search("digital engagement HbA1c", 5)

    assert len(articles) == 2
    rct, review = articles

    assert rct.pmid == "111"
    assert rct.evidence_type == "rct"
    assert rct.abstract == "Engagement matters.\n\nHbA1c improved."
    assert rct.url == "https://doi.org/10.1001/jamanetworkopen.2023.40232"
    assert rct.published_at == date(2023, 12, 1)
    assert rct.journal == "JAMA Network Open"

    assert review.evidence_type == "review"
    assert review.published_at == date(2021, 1, 1)  # year only → January 1st
    assert review.url == "https://pubmed.ncbi.nlm.nih.gov/222/"  # no DOI → PubMed link


async def test_search_empty_when_no_pmids() -> None:
    transport = httpx.MockTransport(
        lambda _r: httpx.Response(200, json={"esearchresult": {"idlist": []}})
    )
    async with httpx.AsyncClient(transport=transport) as http:
        assert await NCBIPubMedClient(http).search("nonsense xyzzy", 5) == []


async def test_search_applies_filters_to_term_and_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "esearch" in request.url.path:
            captured.update(dict(request.url.params))
            return httpx.Response(200, json=_ESEARCH)
        if "efetch" in request.url.path:
            return httpx.Response(200, text=_EFETCH_XML)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await NCBIPubMedClient(http).search(
            "digital engagement",
            5,
            filters=SearchFilters(date_range="5y", study_types=("rct",)),
            today=_date(2026, 6, 19),
        )

    assert captured["term"] == "(digital engagement) AND (Randomized Controlled Trial[pt])"
    assert captured["datetype"] == "pdat"
    assert captured["mindate"] == "2021"
    assert captured["maxdate"] == "2026"
