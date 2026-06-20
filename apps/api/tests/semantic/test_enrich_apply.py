"""Unitaires : construction manifest/payload des 4 chemins d'apply (sans DB)."""

from augura_api.modules.semantic.enrich_apply import (
    build_direct_relations_payload,
    bump_version,
)
from augura_api.modules.semantic.enrich_schemas import DirectRelationIn


def test_bump_version_patch_minor_major() -> None:
    assert bump_version("3.0.0", "patch") == "3.0.1"
    assert bump_version("3.1.4", "minor") == "3.2.0"
    assert bump_version("3.1.4", "major") == "4.0.0"
    assert bump_version(None, "patch") == "3.0.1"  # fallback 3.0.0


def test_build_direct_relations_assigns_ids_and_autostubs_evidence() -> None:
    rels = [DirectRelationIn(subject_concept_id="A", object_concept_id="B", predicate="precedes")]
    payload, id_map = build_direct_relations_payload(
        rels, version="3.0.1", existing_max_rel_n=2, today="20260619"
    )
    assert payload["ontology_relations"][0]["relation_id"] == "ENRR_20260619_003"
    assert payload["ontology_relations"][0]["active"] is True
    assert payload["ontology_relations"][0]["polarity"] == "neutral"
    assert len(payload["ontology_relation_evidence"]) == 1
    assert payload["ontology_relation_evidence"][0]["relation_id"] == "ENRR_20260619_003"
