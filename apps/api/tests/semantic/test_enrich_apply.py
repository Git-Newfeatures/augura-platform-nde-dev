"""Unitaires : construction manifest/payload des 4 chemins d'apply (sans DB)."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from augura_api.core.errors import NotFoundError
from augura_api.modules.semantic.enrich_apply import (
    EnrichApplyService,
    build_direct_relations_payload,
    bump_version,
)
from augura_api.modules.semantic.enrich_schemas import (
    DeactivateRelationIn,
    DirectRelationIn,
    EnrichApplyRequest,
)
from augura_api.modules.semantic.repo import SemanticRepo


def test_bump_version_patch_minor_major() -> None:
    assert bump_version("3.0.0", "patch") == "3.0.1"
    assert bump_version("3.1.4", "minor") == "3.2.0"
    assert bump_version("3.1.4", "major") == "4.0.0"
    assert bump_version(None, "patch") == "3.0.1"  # fallback 3.0.0


def test_build_direct_relations_assigns_ids_and_autostubs_evidence() -> None:
    rels = [DirectRelationIn(subject_concept_id="A", object_concept_id="B", predicate="precedes")]
    payload, _ = build_direct_relations_payload(
        rels, version="3.0.1", existing_max_rel_n=2, today="20260619"
    )
    assert payload["ontology_relations"][0]["relation_id"] == "ENRR_20260619_003"
    assert payload["ontology_relations"][0]["active"] is True
    assert payload["ontology_relations"][0]["polarity"] == "neutral"
    assert len(payload["ontology_relation_evidence"]) == 1
    assert payload["ontology_relation_evidence"][0]["relation_id"] == "ENRR_20260619_003"


def _mock_repo(current: str = "3.0.0") -> AsyncMock:
    repo = AsyncMock()
    repo.release_status.return_value = {"release": {"semantic_release_version": current}}
    repo.apply_release.return_value = {"version": "x"}
    return repo


@pytest.mark.asyncio
async def test_deactivate_missing_relation_raises_not_found() -> None:
    repo = _mock_repo()
    repo.get_relation_row.return_value = None
    svc = EnrichApplyService(cast(SemanticRepo, repo))
    req = EnrichApplyRequest(deactivate_relation=DeactivateRelationIn(relation_id="R9"))
    with pytest.raises(NotFoundError):
        await svc.apply(req, today="20260620")


@pytest.mark.asyncio
async def test_deactivate_builds_patch_release() -> None:
    repo = _mock_repo("3.2.1")
    repo.get_relation_row.return_value = {
        "relation_id": "R1",
        "active": True,
        "review_status": "approved",
        "version": "3.2.1",
    }
    svc = EnrichApplyService(cast(SemanticRepo, repo))
    req = EnrichApplyRequest(deactivate_relation=DeactivateRelationIn(relation_id="R1"))
    resp = await svc.apply(req, today="20260620")
    assert resp.new_version == "3.2.2"
    _, payload = repo.apply_release.call_args.args
    assert payload["ontology_relations"][0]["active"] is False
    assert payload["ontology_relations"][0]["review_status"] == "deprecated"


@pytest.mark.asyncio
async def test_proposals_minor_bump_when_concepts_selected() -> None:
    repo = _mock_repo("3.0.0")
    svc = EnrichApplyService(cast(SemanticRepo, repo))
    proposals: dict[str, Any] = {
        "taxonomy_concepts": [{"local_concept_id": "C1", "concept_name": "x"}],
        "ontology_relations": [{"relation_id": "R1"}],
        "taxonomy_synonyms": [{"local_concept_id": "C1", "synonym": "s"}],
    }
    req = EnrichApplyRequest(
        proposals=cast(dict[str, object], proposals),
        selected_concept_ids=["C1"],
        selected_relation_ids=["R1"],
    )
    resp = await svc.apply(req, today="20260620")
    assert resp.new_version == "3.1.0"  # minor : un concept sélectionné
    assert resp.concepts_added == 1
    assert resp.relations_added == 1
    _, payload = repo.apply_release.call_args.args
    assert payload["taxonomy_concepts"][0]["review_status"] == "approved"
    assert payload["taxonomy_concepts"][0]["active"] is True
