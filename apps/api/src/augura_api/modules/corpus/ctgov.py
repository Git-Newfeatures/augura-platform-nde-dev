"""Client ClinicalTrials.gov via l'API officielle v2 (REST/JSON).

Frère de `pubmed.py`, mêmes conventions : `CTGovClient` est un Protocol injectable
(les tests fournissent un faux client sans réseau), l'implémentation réelle tape
l'API publique `https://clinicaltrials.gov/api/v2/studies` via l'`httpx.AsyncClient`
injecté. Champs confirmés par sonde sur l'API v2 (cf. protocolSection.*Module) :

  - search  : GET /studies?query.term=…  → { studies: [ { protocolSection } ], … }
  - by-NCT  : GET /studies/{nct}          → { protocolSection, … }  (404 si inconnu)

Le 404 d'un NCT inconnu = miss known-item → None (pas de repli topique).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol, cast

import httpx

from augura_api.modules.corpus.filters import SearchFilters, ctgov_filter_params

CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"

_HTTP_NOT_FOUND = 404


def _as_dict(v: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", v) if isinstance(v, dict) else {}


def _as_list(v: Any) -> list[Any]:
    return cast("list[Any]", v) if isinstance(v, list) else []


@dataclass(frozen=True)
class CTGovStudy:
    nct_id: str
    title: str
    status: str | None = None
    phase: str | None = None
    conditions: tuple[str, ...] = ()
    interventions: tuple[str, ...] = ()
    url: str = ""


def _study_url(nct_id: str) -> str:
    return f"https://clinicaltrials.gov/study/{nct_id}"


def _parse_study(protocol_section: dict[str, Any]) -> CTGovStudy | None:
    """Parse un `protocolSection` (commun à la recherche et au fetch par id)."""
    ident = _as_dict(protocol_section.get("identificationModule"))
    nct_id = str(ident.get("nctId") or "").strip()
    title = str(ident.get("briefTitle") or ident.get("officialTitle") or "").strip()
    if not nct_id or not title:
        return None

    status_raw = _as_dict(protocol_section.get("statusModule")).get("overallStatus")
    phases = _as_list(_as_dict(protocol_section.get("designModule")).get("phases"))
    conditions_raw = _as_list(_as_dict(protocol_section.get("conditionsModule")).get("conditions"))
    interventions_raw = _as_list(
        _as_dict(protocol_section.get("armsInterventionsModule")).get("interventions")
    )
    return CTGovStudy(
        nct_id=nct_id,
        title=title,
        status=str(status_raw) if status_raw else None,
        phase="/".join(str(p) for p in phases) or None,
        conditions=tuple(str(c) for c in conditions_raw),
        interventions=tuple(
            str(_as_dict(i).get("name")) for i in interventions_raw if _as_dict(i).get("name")
        ),
        url=_study_url(nct_id),
    )


class CTGovClient(Protocol):
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[CTGovStudy]: ...

    async def fetch_by_nct(self, nct_id: str) -> CTGovStudy | None: ...


class CTGovApiClient:
    """Implémentation réelle : API v2 ClinicalTrials.gov (aucune clé requise)."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[CTGovStudy]:
        n = max(1, min(50, max_results))
        day = today or datetime.now(UTC).date()
        params: dict[str, str] = {"query.term": query, "pageSize": str(n), "format": "json"}
        params.update(ctgov_filter_params(filters, day))
        resp = await self._http.get(CTGOV_BASE, params=params)
        resp.raise_for_status()
        studies = _as_list(_as_dict(resp.json()).get("studies"))
        parsed = [_parse_study(_as_dict(s.get("protocolSection"))) for s in studies]
        return [s for s in parsed if s is not None]

    async def fetch_by_nct(self, nct_id: str) -> CTGovStudy | None:
        """Known-item NCT : fetch direct par id. 404 → None (miss honnête)."""
        nct = nct_id.strip().upper()
        if not nct:
            return None
        resp = await self._http.get(f"{CTGOV_BASE}/{nct}", params={"format": "json"})
        if resp.status_code == _HTTP_NOT_FOUND:
            return None
        resp.raise_for_status()
        return _parse_study(_as_dict(_as_dict(resp.json()).get("protocolSection")))
