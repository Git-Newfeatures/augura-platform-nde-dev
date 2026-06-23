"""Tests for the document rendering (HTML) — pure function, no database or I/O."""

from datetime import UTC, datetime

from augura_api.modules.documents.render import render_document_html


def _ctx() -> datetime:
    return datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def test_render_includes_study_and_sections() -> None:
    html = render_document_html(
        doc_type="protocol",
        study={"name": "ACME DiGA", "framework": "DiGA", "status": "active"},
        state={"estimand": "ATT", "design": "target_trial"},
        results=[],
        sources=[],
        generated_at=_ctx(),
    )
    assert "<!doctype html>" in html
    assert "ACME DiGA" in html
    assert "Study Protocol" in html
    assert "Study overview" in html
    assert "Causal design" in html
    assert "ATT" in html


def test_render_results_table_when_present() -> None:
    html = render_document_html(
        doc_type="report",
        study={"name": "S"},
        state=None,
        results=[
            {
                "cohort_name": "cohort",
                "scenario": "baseline",
                "estimator": "lme",
                "effect_size": -0.2,
                "ci_lower": -0.3,
                "ci_upper": -0.1,
                "power": 87.0,
                "p_value": 0.001,
            }
        ],
        sources=[{"source_id": "pubmed", "count": 12}],
        generated_at=_ctx(),
    )
    assert "Evidence Report" in html
    assert "baseline" in html
    assert "lme" in html
    assert "87.0%" in html
    assert "pubmed" in html


def test_render_escapes_html_in_study_name() -> None:
    html = render_document_html(
        doc_type="protocol",
        study={"name": "<script>alert(1)</script>"},
        state=None,
        results=[],
        sources=[],
        generated_at=_ctx(),
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
