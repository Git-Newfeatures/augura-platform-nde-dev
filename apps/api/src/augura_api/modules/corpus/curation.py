"""Curation LLM des résultats live (re-ranking par abstract + rationale).

Frère de `pubmed.py` / `ctgov.py`. `Curator` est un Protocol injectable (tests sans
réseau) ; `LLMCurator` réutilise `run_structured_agent` (outil forcé + validation
Pydantic + 1 retry réparation). Le LLM ne renvoie QUE des ids ordonnés + rationale ;
le mapping vers les enregistrements déjà récupérés est déterministe (`apply_curation`),
donc aucune fabrication de contenu n'est possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from anthropic.types import ToolParam
from pydantic import BaseModel

from augura_api.core.llm.runtime import LLMClient, run_structured_agent

# Version du prompt de curation — épinglée dans la provenance des snapshots.
CURATION_PROMPT_VERSION = "curate-v1"

# Borne de tokens : on tronque le texte de chaque candidat (abstract / résumé CT.gov).
_MAX_TEXT = 1200


@dataclass(frozen=True)
class CurationCandidate:
    """Candidat soumis au LLM : id stable + titre + texte jugeable (abstract ou résumé)."""

    id: str
    title: str
    text: str


@dataclass(frozen=True)
class CuratedRef:
    """Sortie de curation par item : l'ordre de la liste porte le classement."""

    id: str
    rationale: str


def apply_curation[T](
    refs: list[CuratedRef], by_id: dict[str, T], *, max_results: int
) -> list[tuple[T, str]]:
    """Mappe les refs ordonnées du LLM → (enregistrement, rationale), de façon
    déterministe : ignore les ids hors `by_id` (hallucinés) et les doublons, cape à
    `max_results`. Renvoie [] si rien ne matche (l'appelant décide du repli)."""
    seen: set[str] = set()
    out: list[tuple[T, str]] = []
    for ref in refs:
        if ref.id in seen or ref.id not in by_id:
            continue
        seen.add(ref.id)
        out.append((by_id[ref.id], ref.rationale))
        if len(out) >= max_results:
            break
    return out


class Curator(Protocol):
    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]: ...


class _CuratedItem(BaseModel):
    id: str
    rationale: str = ""


class _CurationOutput(BaseModel):
    selected: list[_CuratedItem]


_CURATION_TOOL: ToolParam = {
    "name": "curate_results",
    "description": "Renvoie les résultats les plus pertinents, classés du plus au moins "
    "pertinent, chacun avec un rationale court.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "id exact d'un candidat fourni"},
                        "rationale": {"type": "string", "description": "1 phrase de justification"},
                    },
                    "required": ["id"],
                },
            }
        },
        "required": ["selected"],
    },
}

_SYSTEM = (
    "Tu es un·e documentaliste biomédical·e. À partir d'une question de recherche et "
    "d'une liste de résultats (id, titre, texte), sélectionne et CLASSE les plus "
    "pertinents, du plus au moins pertinent. À pertinence égale, remonte les preuves "
    "les plus fortes (méta-analyses / revues systématiques / RCT > observationnel > "
    "autre). N'invente JAMAIS d'id : n'utilise que les id fournis. Donne un rationale "
    "d'une phrase par résultat retenu. Écarte les résultats hors sujet."
)


def _render(candidates: list[CurationCandidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        text = c.text[:_MAX_TEXT]
        lines.append(f"[{c.id}] {c.title}\n{text}")
    return "\n\n".join(lines)


class LLMCurator:
    """Implémentation réelle : un appel `run_structured_agent` par source."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        if not candidates:
            return []
        user = (
            f"Question : {query}\nSource : {source}\n"
            f"Sélectionne au plus {max_results} résultats parmi :\n\n{_render(candidates)}"
        )
        result = await run_structured_agent(
            self._client,
            model=self._model,
            system=_SYSTEM,
            tool=_CURATION_TOOL,
            messages=[{"role": "user", "content": user}],
            output_model=_CurationOutput,
        )
        return [CuratedRef(id=i.id, rationale=i.rationale) for i in result.output.selected]
