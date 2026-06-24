from augura_api.modules.causal.roles import classify_roles, dagitty_json, prune_orphans
from augura_api.modules.causal.subgraph import Relation


def _rel(subj: str, obj: str) -> Relation:
    return Relation(
        id=f"{subj}->{obj}",
        subject_concept_id=subj,
        object_concept_id=obj,
        predicate="causally_influences",
        polarity="neutral",
        default_strength="moderate",
        default_temporal_lag="",
        mechanism_summary="",
    )


def test_classify_roles_mediator_confounder_collider() -> None:
    # E→M→O (M mediator); C→E and C→O (C confounder); X→K and Y→K (K collider).
    rels = [
        _rel("E", "M"),
        _rel("M", "O"),
        _rel("C", "E"),
        _rel("C", "O"),
        _rel("X", "K"),
        _rel("Y", "K"),
    ]
    roles = classify_roles(rels, exposure_ids=["E"], outcome_ids=["O"])
    assert roles["E"] == "exposure"
    assert roles["O"] == "outcome"
    assert roles["M"] == "mediator"
    assert roles["C"] == "confounder"
    assert roles["K"] == "collider"


def test_prune_orphans_drops_branches_not_reaching_outcome() -> None:
    rels = [_rel("E", "O"), _rel("Z", "W")]  # Z→W never reaches the outcome O
    pruned = {r.id for r in prune_orphans(rels, outcome_ids=["O"], keep_ids=["E"])}
    assert "E->O" in pruned
    assert "Z->W" not in pruned


def test_prune_orphans_noop_without_outcome_in_graph() -> None:
    rels = [_rel("A", "B")]
    assert prune_orphans(rels, outcome_ids=["O"]) == rels


def test_dagitty_json_shape() -> None:
    rels = [_rel("E", "O")]
    roles = classify_roles(rels, exposure_ids=["E"], outcome_ids=["O"])
    dj = dagitty_json(rels, roles)
    assert {n["id"] for n in dj["nodes"]} == {"E", "O"}
    assert dj["edges"] == [{"from": "E", "to": "O", "predicate": "causally_influences"}]
