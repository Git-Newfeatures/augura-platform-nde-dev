"""Unit tests for the search-compare engine. No network access.

Run from this folder:  uv run pytest -q   (or: pytest -q)
"""

from __future__ import annotations

import pytest

import search_lanes as sl
from search_lanes import (
    STATUS_ERROR,
    STATUS_NOT_CONFIGURED,
    STATUS_OK,
    SearchResult,
    Source,
)

# Keys that any lane might read — clear them so tests are independent of the real env.
_LANE_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "CONSENSUS_API_KEY",
    "CONSENSUS_API_BASE",
    "OPENEVIDENCE_API_KEY",
    "OPENEVIDENCE_API_BASE",
    "OPENEVIDENCE_ORG_ID",
    "NCBI_API_KEY",
    "NCBI_EMAIL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in _LANE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _sample_results() -> list[SearchResult]:
    return [
        SearchResult(
            method="PubMed (LLM-curated)",
            status=STATUS_OK,
            answer="Statins reduce LDL [PMID:1].",
            sources=[
                Source(title="A trial", url="https://pubmed.ncbi.nlm.nih.gov/1/", year="2020")
            ],
            latency_s=1.2,
        ),
        SearchResult(
            method="Consensus", status=STATUS_NOT_CONFIGURED, note="Set CONSENSUS_API_KEY."
        ),
        SearchResult(method="OpenEvidence", status=STATUS_ERROR, error="HTTPError: 500"),
    ]


def test_results_to_dataframe_shape():
    df = sl.results_to_dataframe(_sample_results())
    assert list(df.columns) == ["Method", "Status", "Answer", "Top sources", "Latency (s)"]
    assert len(df) == 3
    assert df.iloc[0]["Method"] == "PubMed (LLM-curated)"
    # not_configured row falls back to the note in the Answer cell
    assert "CONSENSUS_API_KEY" in df.iloc[1]["Answer"]
    # error row surfaces the error message
    assert "500" in df.iloc[2]["Answer"]


def test_results_to_html_is_escaped_and_linked():
    results = [
        SearchResult(
            method="PubMed (LLM-curated)",
            answer="answer with <script>",
            sources=[Source(title="Paper <x>", url="https://example.org/a")],
        )
    ]
    html_out = sl.results_to_html(results)
    assert "<table" in html_out
    assert "&lt;script&gt;" in html_out  # answer HTML-escaped
    assert "https://example.org/a" in html_out  # link preserved
    assert "<script>" not in html_out  # no raw injection
    assert "rel='noopener noreferrer'" in html_out  # link hardening


def test_results_to_html_rejects_dangerous_url_schemes():
    results = [
        SearchResult(
            method="Consensus",
            sources=[
                Source(title="evil", url="javascript:alert(document.cookie)"),
                Source(title="also evil", url="data:text/html,<script>x</script>"),
                Source(title="ok", url="https://good.example/p"),
            ],
        )
    ]
    html_out = sl.results_to_html(results)
    assert "javascript:" not in html_out  # dangerous scheme dropped
    assert "data:text/html" not in html_out
    assert "https://good.example/p" in html_out  # safe URL still linked
    # the dangerous-source titles still render as plain text (not as links)
    assert "evil" in html_out


@pytest.mark.parametrize(
    "raw, expected",
    [
        (["Jane Doe", "John Smith"], "Jane Doe, John Smith"),
        ([{"name": "Jane Doe"}, {"name": "John Smith"}], "Jane Doe, John Smith"),
        (None, ""),
    ],
)
def test_consensus_author_coercion(raw, expected):
    assert ", ".join(sl._author_name(a) for a in (raw or [])) == expected


# --------------------------------------------------------------------------- #
# Not-configured paths
# --------------------------------------------------------------------------- #


def test_consensus_not_configured_without_key():
    result = sl.consensus_search("does X work?")
    assert result.status == STATUS_NOT_CONFIGURED
    assert "CONSENSUS_API_KEY" in result.note
    assert result.answer == ""  # no fabricated answer


def test_openevidence_not_configured_without_key():
    result = sl.openevidence_search("does X work?")
    assert result.status == STATUS_NOT_CONFIGURED
    assert "BAA" in result.note or "Enterprise" in result.note
    assert result.sources == []


def test_lane_status_reports_needs(monkeypatch):
    status = sl.lane_status()
    assert status["PubMed (LLM-curated)"].startswith("needs")
    assert "CONSENSUS_API_KEY" in status["Consensus"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert sl.lane_status()["PubMed (LLM-curated)"] == "ready"


# --------------------------------------------------------------------------- #
# PubMed flow (mocked LLM + E-utilities)
# --------------------------------------------------------------------------- #


def test_pubmed_llm_search_happy_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(sl, "_build_pubmed_query", lambda q, *, model: "statins[Title]")
    monkeypatch.setattr(sl, "_pubmed_esearch", lambda term, *, retmax: ["111", "222"])
    monkeypatch.setattr(
        sl,
        "_pubmed_esummary",
        lambda pmids: [Source(title=f"Paper {p}", identifier=f"PMID:{p}") for p in pmids],
    )
    monkeypatch.setattr(
        sl,
        "_pubmed_abstracts",
        lambda pmids: {p: {"title": f"Paper {p}", "abstract": "Evidence text."} for p in pmids},
    )
    monkeypatch.setattr(sl, "_llm_complete", lambda *a, **k: "Statins lower LDL [PMID:111].")

    result = sl.pubmed_llm_search("do statins lower LDL?")
    assert result.status == STATUS_OK
    assert result.query_used == "statins[Title]"
    assert len(result.sources) == 2
    assert "[PMID:111]" in result.answer


def test_pubmed_llm_search_no_hits(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(sl, "_build_pubmed_query", lambda q, *, model: "nonsense[Title]")
    monkeypatch.setattr(sl, "_pubmed_esearch", lambda term, *, retmax: [])
    monkeypatch.setattr(sl, "_pubmed_esummary", lambda pmids: [])
    monkeypatch.setattr(sl, "_pubmed_abstracts", lambda pmids: {})

    result = sl.pubmed_llm_search("obscure question")
    assert result.status == STATUS_OK
    assert "No PubMed abstracts" in result.answer
    assert result.sources == []


# --------------------------------------------------------------------------- #
# Error isolation
# --------------------------------------------------------------------------- #


def test_lane_error_is_captured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(sl, "_build_pubmed_query", boom)
    result = sl.pubmed_llm_search("q")
    assert result.status == STATUS_ERROR
    assert "network down" in result.error


def test_compare_returns_three_results_and_isolates_failures(monkeypatch):
    # PubMed raises, the other two are not configured — compare must still return 3 rows.
    monkeypatch.setattr(
        sl, "pubmed_llm_search", lambda q, *, model: (_ for _ in ()).throw(ValueError("x"))
    )
    # rebuild LANES so compare picks up the patched callable
    monkeypatch.setattr(
        sl, "LANES", [sl.pubmed_llm_search, sl.consensus_search, sl.openevidence_search]
    )
    results = sl.compare("q")
    assert len(results) == 3
    statuses = {r.method: r.status for r in results}
    assert statuses["Consensus"] == STATUS_NOT_CONFIGURED
    assert statuses["OpenEvidence"] == STATUS_NOT_CONFIGURED
    # the raising lane was caught by _safe_lane
    assert any(r.status == STATUS_ERROR for r in results)
