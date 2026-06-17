"""Rendu de dossiers (protocole d'étude / rapport de preuve) en HTML autonome.

Fonction PURE (pas d'I/O, pas de base) → testable. Produit un document print-friendly
(CSS @media print → « Imprimer en PDF » dans le navigateur donne un PDF propre). Le worker
documents l'appelle puis stocke les octets via core.storage. Un backend PDF natif
(reportlab/WeasyPrint) pourra remplacer ce rendu derrière la même signature.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, cast

_TITLES = {
    "protocol": "Study Protocol",
    "report": "Evidence Report",
}


def _row(label: str, value: Any) -> str:
    return (
        f"<tr><th>{escape(str(label))}</th>"
        f"<td>{escape(str(value)) if value not in (None, '') else '—'}</td></tr>"
    )


def _results_table(results: list[dict[str, Any]]) -> str:
    if not results:
        return "<p class='empty'>No simulation results available for this study yet.</p>"
    head = (
        "<tr><th>Cohort</th><th>Scenario</th><th>Estimator</th><th>Effect</th>"
        "<th>95% CI</th><th>Power</th><th>p-value</th></tr>"
    )
    body: list[str] = []
    for r in results:
        ci = (
            f"[{r.get('ci_lower')}, {r.get('ci_upper')}]"
            if r.get("ci_lower") is not None
            else "—"
        )
        power = f"{r.get('power')}%" if r.get("power") is not None else "—"
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('cohort_name', '—')))}</td>"
            f"<td>{escape(str(r.get('scenario', '—')))}</td>"
            f"<td>{escape(str(r.get('estimator', '—')))}</td>"
            f"<td>{escape(str(r.get('effect_size', '—')))}</td>"
            f"<td>{escape(ci)}</td>"
            f"<td>{escape(power)}</td>"
            f"<td>{escape(str(r.get('p_value', '—')))}</td>"
            "</tr>"
        )
    return f"<table class='data'>{head}{''.join(body)}</table>"


def _sources_list(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "<p class='empty'>No evidence sources indexed yet.</p>"
    items = "".join(
        f"<li>{escape(str(s.get('source_id', '—')))} — "
        f"{escape(str(s.get('count', 0)))} documents</li>"
        for s in sources
    )
    return f"<ul class='sources'>{items}</ul>"


def render_document_html(
    *,
    doc_type: str,
    study: dict[str, Any] | None,
    state: dict[str, Any] | None,
    results: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    generated_at: datetime,
) -> str:
    title = _TITLES.get(doc_type, "Augura Dossier")
    _stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    study_d: dict[str, Any] = study or {}
    study_name = study_d.get("name") or "Untitled study"
    state_d: dict[str, Any] = state or {}
    causal: dict[str, Any] = {}
    _cq = state_d.get("causalQuestion") or state_d.get("causal_question")
    if isinstance(_cq, dict):
        causal = cast("dict[str, Any]", _cq)
    estimand = state_d.get("estimand") or state_d.get("studyEstimand")
    design = state_d.get("design") or state_d.get("studyDesign")
    approach = state_d.get("approach") or state_d.get("studyType")

    overview = "".join(
        [
            _row("Study", study_name),
            _row("Framework", study_d.get("framework")),
            _row("Category", study_d.get("category")),
            _row("Status", study_d.get("status")),
            _row("Lead", study_d.get("lead")),
            _row("Subjects (N)", study_d.get("n_subjects")),
        ]
    )
    design_rows = "".join(
        [
            _row("Approach", approach),
            _row("Design", design),
            _row("Estimand", estimand),
            _row("Population", causal.get("population")),
            _row("Exposure", causal.get("exposure")),
            _row("Outcome", causal.get("outcome")),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(title)} — {escape(study_name)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    color: #0f172a; margin: 0; padding: 48px; max-width: 820px; }}
  header {{ border-bottom: 3px solid #047857; padding-bottom: 16px; margin-bottom: 28px; }}
  .eyebrow {{ text-transform: uppercase; letter-spacing: .08em; color: #047857;
    font-size: 12px; font-weight: 700; }}
  h1 {{ font-size: 28px; margin: 6px 0 4px; }}
  h2 {{ font-size: 16px; margin: 28px 0 10px; color: #047857;
    border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
  .meta {{ color: #64748b; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  table th, table td {{ text-align: left; padding: 7px 10px; vertical-align: top; }}
  table:not(.data) th {{ width: 180px; color: #475569; font-weight: 600; }}
  table.data th {{ background: #f1f5f9; font-weight: 600; }}
  table.data td, table.data th {{ border: 1px solid #e2e8f0; }}
  .empty {{ color: #94a3b8; font-style: italic; }}
  ul.sources {{ font-size: 13px; }}
  footer {{ margin-top: 40px; color: #94a3b8; font-size: 11px;
    border-top: 1px solid #e2e8f0; padding-top: 12px; }}
  @media print {{ body {{ padding: 0; }} h2 {{ break-after: avoid; }} }}
</style>
</head>
<body>
  <header>
    <div class="eyebrow">Augura · {escape(doc_type)}</div>
    <h1>{escape(title)}</h1>
    <div class="meta">{escape(study_name)} · generated {escape(_stamp)}</div>
  </header>

  <h2>Study overview</h2>
  <table>{overview}</table>

  <h2>Causal design</h2>
  <table>{design_rows}</table>

  <h2>Estimation results</h2>
  {_results_table(results)}

  <h2>Evidence base</h2>
  {_sources_list(sources)}

  <footer>
    Augura evidence platform — reproducible dossier. This document is generated from
    live study state, simulation read-model and indexed corpus at generation time.
  </footer>
</body>
</html>"""
