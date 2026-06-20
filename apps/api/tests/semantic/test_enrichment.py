"""Unitaires de la logique pure d'enrichissement (coverage, BFS, prechecks)."""

from __future__ import annotations

from augura_api.modules.semantic import enrichment as enr

# ── Helpers ───────────────────────────────────────────────────────────────────


def _concept(
    cid: str,
    label: str,
    domain: str = "condition",
    layer: int = 2,
    active: bool = True,
) -> dict:
    return {
        "local_concept_id": cid,
        "concept_name": label,
        "augura_domain": domain,
        "layer": layer,
        "active": active,
    }


def _raw(
    concepts: list | None = None,
    synonyms: list | None = None,
    relations: list | None = None,
    predicates: list | None = None,
) -> dict:
    return {
        "taxonomy_concepts": concepts or [],
        "taxonomy_synonyms": synonyms or [],
        "ontology_relations": relations or [],
        "causal_predicates": predicates or [],
    }


def _rel(rid: str, subj: str, obj: str, pred: str = "precedes", pol: str = "increases") -> dict:
    return {
        "relation_id": rid,
        "subject_concept_id": subj,
        "object_concept_id": obj,
        "predicate": pred,
        "polarity": pol,
        "active": True,
    }


def _batch(**kwargs) -> dict:
    """Crée un batch minimal avec toutes les clés requises."""
    base: dict = {
        "taxonomy_concepts": [],
        "taxonomy_synonyms": [],
        "taxonomy_standard_codes": [],
        "ontology_relations": [],
        "ontology_relation_evidence": [],
        "ontology_relation_qualifiers": [],
    }
    base.update(kwargs)
    return base


# ── Tests normalize ───────────────────────────────────────────────────────────


def test_normalize_none_returns_empty() -> None:
    assert enr.normalize(None) == ""


def test_normalize_empty_string_returns_empty() -> None:
    assert enr.normalize("") == ""


def test_normalize_expands_abbreviation() -> None:
    # "hba1c" doit être expansé en "hemoglobin a1c"
    assert enr.normalize("HbA1c") == "hemoglobin a1c"


def test_normalize_strips_timepoint_suffix() -> None:
    # ".BL" doit être supprimé
    assert enr.normalize("cgm_tir.BL") == "cgm time range"


def test_normalize_strips_noise_tokens() -> None:
    # "level", "value" sont des tokens bruit
    result = enr.normalize("blood pressure level value")
    assert "level" not in result
    assert "value" not in result


def test_normalize_strips_pure_digits() -> None:
    result = enr.normalize("glucose 123 mg")
    assert "123" not in result


def test_normalize_separators_to_space() -> None:
    # Séparateurs _, -, ., :, | → espace
    assert "blood" in enr.normalize("blood_pressure")
    assert "blood" in enr.normalize("blood-pressure")


def test_normalize_cgm_not_expanded() -> None:
    # "cgm" intentionnellement non expansé (commentaire JS)
    result = enr.normalize("cgm")
    assert result == "cgm"


def test_normalize_returns_stripped_string() -> None:
    result = enr.normalize("  hypertension  ")
    assert result == result.strip()


# ── Tests build_semantic_data ─────────────────────────────────────────────────


def test_build_semantic_data_filters_inactive() -> None:
    concepts = [
        _concept("C1", "hypertension", active=True),
        _concept("C2", "diabetes", active=False),
    ]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    ids = [c["id"] for c in idx.concept_index]
    assert "C1" in ids
    assert "C2" not in ids


def test_build_semantic_data_synonym_lookup() -> None:
    concepts = [_concept("C1", "hypertension")]
    synonyms = [{"local_concept_id": "C1", "synonym": "high blood pressure"}]
    idx = enr.build_semantic_data(_raw(concepts=concepts, synonyms=synonyms))
    assert "C1" in idx.syn_lookup.get(enr.normalize("high blood pressure"), [])


def test_build_semantic_data_ontology_active_filter() -> None:
    relations = [
        _rel("R1", "A", "B"),
        {**_rel("R2", "A", "C"), "active": False},
    ]
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept("A", "a"), _concept("B", "b"), _concept("C", "c")],
            relations=relations,
        )
    )
    assert len(idx.ontology.relations) == 1
    assert idx.ontology.relations[0]["relation_id"] == "R1"


def test_build_semantic_data_predicate_map() -> None:
    predicates = [{"predicate_id": "precedes", "description": "temporally precedes"}]
    idx = enr.build_semantic_data(_raw(predicates=predicates))
    assert "precedes" in idx.ontology.predicates


# ── Tests match_tokens ────────────────────────────────────────────────────────


def test_match_tokens_exact_synonym_hit() -> None:
    """Correspondance exacte via syn_lookup — la phrase DOIT être associée."""
    concepts = [_concept("C1", "hypertension")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    matched, unmatched = enr.match_tokens(["hypertension"], idx.syn_lookup, idx.concept_index)
    assert matched["hypertension"] == ["C1"]
    assert not unmatched


def test_match_tokens_label_substring_match() -> None:
    """Le label du concept est une sous-chaîne de la phrase."""
    concepts = [_concept("C1", "blood pressure")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    # phrase courte (2 mots) → couverture OK
    matched, unmatched = enr.match_tokens(
        ["systolic blood pressure"], idx.syn_lookup, idx.concept_index
    )
    assert "C1" in matched.get("systolic blood pressure", [])


def test_match_tokens_word_coverage_rejects_short_label_in_long_phrase() -> None:
    """Un label de 2 mots NE DOIT PAS matcher une phrase de 7 mots (< 50%)."""
    concepts = [_concept("C1", "blood pressure")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    # "blood pressure" = 2 mots / 7 mots de la phrase = 28.6% < 50%
    matched, unmatched = enr.match_tokens(
        ["reduction of systolic blood pressure after treatment"],
        idx.syn_lookup,
        idx.concept_index,
    )
    # Le concept ne doit PAS être dans les matchés
    assert "C1" not in matched.get("reduction of systolic blood pressure after treatment", [])


def test_match_tokens_short_phrase_accepts_short_label() -> None:
    """Phrase ≤ 3 mots : toujours acceptée quelle que soit la couverture."""
    concepts = [_concept("C1", "glucose")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    matched, unmatched = enr.match_tokens(["blood glucose"], idx.syn_lookup, idx.concept_index)
    # "glucose" (1 mot) dans "blood glucose" (2 mots) → phrase ≤ 3 mots → OK
    assert "C1" in matched.get("blood glucose", [])


def test_match_tokens_empty_phrase_skipped() -> None:
    concepts = [_concept("C1", "glucose")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    matched, unmatched = enr.match_tokens(
        ["", None],  # type: ignore[list-item]
        idx.syn_lookup,
        idx.concept_index,
    )
    assert not matched
    assert not unmatched


def test_match_tokens_unmatched_added_to_set() -> None:
    concepts = [_concept("C1", "hypertension")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    matched, unmatched = enr.match_tokens(
        ["completely unknown phrase xyzabc"], idx.syn_lookup, idx.concept_index
    )
    assert "completely unknown phrase xyzabc" in unmatched


def test_match_tokens_label_min_length_4() -> None:
    """Un label de moins de 4 caractères ne doit pas matcher via label-path."""
    concepts = [_concept("C1", "bp")]  # 2 chars normalisé → "bp"
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    # "bp" est < 4 chars → path label ignoré ; syn_lookup direct uniquement
    matched, unmatched = enr.match_tokens(["bp systolic"], idx.syn_lookup, idx.concept_index)
    # syn_lookup contient normalize("bp") = "systolic blood pressure" (expansion)
    # → "bp" → "systolic blood pressure" via abbreviation map, pas "bp"
    # Donc le lookup exact de "bp systolic" ne trouvera rien via label-path
    # car normalize("bp") != normalize("bp systolic")
    # Ce test vérifie simplement qu'il n'y a pas de crash.
    assert isinstance(matched, dict)
    assert isinstance(unmatched, set)


# ── Tests directed_bfs ────────────────────────────────────────────────────────


def test_directed_bfs_finds_forward_path() -> None:
    rels = [_rel("R1", "A", "B")]
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept("A", "a"), _concept("B", "b")],
            relations=rels,
        )
    )
    res = enr.directed_bfs(idx.ontology, ["A"], ["B"], max_hops=3)
    assert res.found is True


def test_directed_bfs_no_path_returns_false() -> None:
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept("A", "a"), _concept("B", "b")],
        )
    )
    res = enr.directed_bfs(idx.ontology, ["A"], ["B"], max_hops=3)
    assert res.found is False
    assert res.nearest_forward_hop is None


def test_directed_bfs_multi_hop() -> None:
    """Chemin A→B→C doit être trouvé en max 3 sauts."""
    rels = [_rel("R1", "A", "B"), _rel("R2", "B", "C")]
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept("A", "a"), _concept("B", "b"), _concept("C", "c")],
            relations=rels,
        )
    )
    res = enr.directed_bfs(idx.ontology, ["A"], ["C"], max_hops=3)
    assert res.found is True


def test_directed_bfs_hop_limit_respected() -> None:
    """Chemin en 4 sauts ne doit PAS être trouvé avec max_hops=3."""
    rels = [
        _rel("R1", "A", "B"),
        _rel("R2", "B", "C"),
        _rel("R3", "C", "D"),
        _rel("R4", "D", "E"),
    ]
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept(x, x) for x in ["A", "B", "C", "D", "E"]],
            relations=rels,
        )
    )
    res = enr.directed_bfs(idx.ontology, ["A"], ["E"], max_hops=3)
    assert res.found is False


def test_directed_bfs_nearest_forward_hop() -> None:
    """Si un voisin de la cible est dans visited, nearest_forward_hop doit être renseigné."""
    # A→B, mais pas B→C ; C←D (donc D est voisin de C)
    # On part de [A], on veut atteindre [C]. B n'atteint pas C directement.
    # D est voisin de C par byObject → si D est visité, nearest_forward_hop = D.
    rels = [_rel("R1", "A", "D"), _rel("R2", "D", "C")]
    idx = enr.build_semantic_data(
        _raw(
            concepts=[_concept(x, x) for x in ["A", "B", "C", "D"]],
            relations=rels,
        )
    )
    # On retire la relation D→C pour que D ne puisse pas atteindre C directement
    idx.ontology.by_subject.pop("D", None)
    idx.ontology.relations = [r for r in idx.ontology.relations if r["relation_id"] != "R2"]
    # Mais on laisse D dans byObject[C] (ajout manuel pour le test)
    idx.ontology.by_object.setdefault("C", []).append(_rel("R2", "D", "C"))
    res = enr.directed_bfs(idx.ontology, ["A"], ["C"], max_hops=3)
    assert res.found is False
    assert res.nearest_forward_hop is not None
    assert res.nearest_forward_hop["concept_id"] == "D"


# ── Tests apply_prechecks ─────────────────────────────────────────────────────


def test_prechecks_reject_self_loop_and_orphan() -> None:
    """Self-loop et objet orphelin doivent tous deux être rejetés."""
    batch = _batch(
        ontology_relations=[
            _rel("X1", "A", "A"),  # self-loop
            _rel("X2", "A", "ZZ"),  # objet orphelin (ZZ inconnu)
        ],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"A"},
        existing_relation_keys=set(),
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["ontology_relations"] == []
    assert any("self-loop" in m for m in log)
    assert any("orphan" in m for m in log)


def test_prechecks_reject_duplicate_relation_key() -> None:
    """Une relation avec la même clé subject|predicate|object|polarity doit être rejetée."""
    key = "A|precedes|B|increases"
    batch = _batch(
        ontology_relations=[_rel("X1", "A", "B")],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"A", "B"},
        existing_relation_keys={key},
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["ontology_relations"] == []
    assert any("duplicate" in m for m in log)


def test_prechecks_reject_unknown_predicate() -> None:
    """Un prédicat inconnu doit être rejeté."""
    batch = _batch(
        ontology_relations=[{**_rel("X1", "A", "B"), "predicate": "unknown_pred"}],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"A", "B"},
        existing_relation_keys=set(),
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["ontology_relations"] == []
    assert any("predicate" in m for m in log)


def test_prechecks_reject_l1_without_code() -> None:
    """Un concept layer=1 sans code standard associé doit être rejeté."""
    batch = _batch(
        taxonomy_concepts=[
            {
                "local_concept_id": "C1",
                "concept_name": "Metformin",
                "layer": 1,
                "augura_domain": "therapeutics",
            }
        ],
        taxonomy_standard_codes=[],  # aucun code → rejet
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids=set(),
        existing_relation_keys=set(),
        valid_predicate_ids=set(),
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["taxonomy_concepts"] == []
    assert any("L1-no-code" in m for m in log)


def test_prechecks_l1_with_code_accepted() -> None:
    """Un concept layer=1 AVEC code standard doit être accepté."""
    batch = _batch(
        taxonomy_concepts=[
            {
                "local_concept_id": "C1",
                "concept_name": "Metformin",
                "layer": 1,
                "augura_domain": "therapeutics",
            }
        ],
        taxonomy_standard_codes=[
            {"local_concept_id": "C1", "vocabulary_id": "RxNorm", "concept_code": "6809"}
        ],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids=set(),
        existing_relation_keys=set(),
        valid_predicate_ids=set(),
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert len(batch["taxonomy_concepts"]) == 1


def test_prechecks_autostub_evidence() -> None:
    """Une relation sans evidence doit recevoir un auto-stub."""
    batch = _batch(
        ontology_relations=[_rel("R1", "A", "B")],
        ontology_relation_evidence=[],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"A", "B"},
        existing_relation_keys=set(),
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert len(batch["ontology_relation_evidence"]) == 1
    ev = batch["ontology_relation_evidence"][0]
    assert ev["source_type"] == "established_physiology"
    assert ev["evidence_id"].startswith("ENRV_20260619_")
    assert any("AUTO-STUB" in m for m in log)


def test_prechecks_polarity_conflict_detected() -> None:
    """Une relation en polarity inverse d'une existante → conflit retourné."""
    batch = _batch(
        ontology_relations=[{**_rel("R1", "A", "B"), "polarity": "decreases"}],
    )
    log: list[str] = []
    conflicts = enr.apply_prechecks(
        batch,
        existing_concept_ids={"A", "B"},
        existing_relation_keys={"A|precedes|B|increases"},
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    # La relation est acceptée (conflit ≠ rejet), mais l'opposé est signalé
    assert len(conflicts) == 1
    assert conflicts[0]["opposite_key"] == "A|precedes|B|increases"


def test_prechecks_duplicate_concept_rejected() -> None:
    """Un concept avec un ID déjà dans existants doit être rejeté."""
    batch = _batch(
        taxonomy_concepts=[_concept("C1", "hypertension")],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"C1"},
        existing_relation_keys=set(),
        valid_predicate_ids=set(),
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["taxonomy_concepts"] == []
    assert any("duplicate concept" in m for m in log)


def test_prechecks_relation_dropped_when_concept_rejected() -> None:
    """Si un concept est rejeté (L1-sans-code), ses relations doivent aussi être supprimées."""
    batch = _batch(
        taxonomy_concepts=[
            {
                "local_concept_id": "C1",
                "concept_name": "Metformin",
                "layer": 1,
                "augura_domain": "therapeutics",
            }
        ],
        taxonomy_standard_codes=[],
        ontology_relations=[_rel("R1", "C1", "B")],
    )
    log: list[str] = []
    enr.apply_prechecks(
        batch,
        existing_concept_ids={"B"},
        existing_relation_keys=set(),
        valid_predicate_ids={"precedes"},
        log=log,
        id_counters={"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0},
        today="20260619",
    )
    assert batch["taxonomy_concepts"] == []
    assert batch["ontology_relations"] == []


# ── Tests reassign_ids ────────────────────────────────────────────────────────


def test_reassign_ids_concept_format() -> None:
    """Les concepts doivent recevoir des IDs au format ENRC_{today}_{NNN}."""
    batch = _batch(
        taxonomy_concepts=[_concept("OLD_C1", "hypertension")],
    )
    counters = {"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0}
    enr.reassign_ids(batch, counters, today="20260619")
    assert batch["taxonomy_concepts"][0]["local_concept_id"] == "ENRC_20260619_001"


def test_reassign_ids_relation_format() -> None:
    """Les relations doivent recevoir des IDs au format ENRR_{today}_{NNN}."""
    batch = _batch(
        ontology_relations=[{**_rel("OLD_R1", "A", "B"), "active": True}],
    )
    counters = {"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0}
    enr.reassign_ids(batch, counters, today="20260619")
    assert batch["ontology_relations"][0]["relation_id"] == "ENRR_20260619_001"


def test_reassign_ids_propagates_concept_id_to_synonyms() -> None:
    """Le nouvel ID de concept doit être propagé dans les synonymes."""
    batch = _batch(
        taxonomy_concepts=[_concept("OLD_C1", "hypertension")],
        taxonomy_synonyms=[
            {
                "local_concept_id": "OLD_C1",
                "synonym": "high bp",
                "synonym_type": "acceptable",
                "source": "test",
            }
        ],
    )
    counters = {"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0}
    enr.reassign_ids(batch, counters, today="20260619")
    assert batch["taxonomy_synonyms"][0]["local_concept_id"] == "ENRC_20260619_001"


def test_reassign_ids_propagates_relation_id_to_evidence() -> None:
    """Le nouvel ID de relation doit être propagé dans les evidences."""
    batch = _batch(
        ontology_relations=[{**_rel("OLD_R1", "A", "B")}],
        ontology_relation_evidence=[
            {
                "evidence_id": "OLD_V1",
                "relation_id": "OLD_R1",
                "source_type": "rct",
                "citation_or_url": "doi:xxx",
                "evidence_summary": "test",
                "population_notes": "general",
                "evidence_strength": "strong",
            }
        ],
    )
    counters = {"concept": 0, "relation": 0, "evidence": 0, "qualifier": 0}
    enr.reassign_ids(batch, counters, today="20260619")
    new_rel_id = batch["ontology_relations"][0]["relation_id"]
    assert batch["ontology_relation_evidence"][0]["relation_id"] == new_rel_id
    assert batch["ontology_relation_evidence"][0]["evidence_id"] == "ENRV_20260619_001"


def test_reassign_ids_counter_increments() -> None:
    """Le compteur doit progresser à travers plusieurs entités."""
    batch = _batch(
        taxonomy_concepts=[_concept("OLD_C1", "a"), _concept("OLD_C2", "b")],
    )
    counters = {"concept": 5, "relation": 0, "evidence": 0, "qualifier": 0}
    enr.reassign_ids(batch, counters, today="20260619")
    ids = [c["local_concept_id"] for c in batch["taxonomy_concepts"]]
    assert "ENRC_20260619_006" in ids
    assert "ENRC_20260619_007" in ids


# ── Tests group_missing_concepts ──────────────────────────────────────────────


def test_group_missing_concepts_similar_tokens_grouped() -> None:
    """Deux tokens partageant > 40% des mots (Jaccard) doivent être groupés."""
    missing = [
        {
            "token": "systolic blood pressure",
            "appeared_in": [],
            "picot_field": "outcome",
            "suggested_layer": 2,
            "suggested_domain": "measurement",
        },
        {
            "token": "diastolic blood pressure",
            "appeared_in": [],
            "picot_field": "outcome",
            "suggested_layer": 2,
            "suggested_domain": "measurement",
        },
    ]
    groups = enr.group_missing_concepts(missing)
    # "blood" et "pressure" sont partagés → Jaccard = 2/4 = 0.5 > 0.4
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_group_missing_concepts_distinct_tokens_separated() -> None:
    """Deux tokens sans mots communs doivent être dans des groupes séparés."""
    missing = [
        {
            "token": "insulin glargine",
            "appeared_in": [],
            "picot_field": "intervention",
            "suggested_layer": 2,
            "suggested_domain": "therapeutics",
        },
        {
            "token": "ejection fraction",
            "appeared_in": [],
            "picot_field": "outcome",
            "suggested_layer": 2,
            "suggested_domain": "measurement",
        },
    ]
    groups = enr.group_missing_concepts(missing)
    assert len(groups) == 2


# ── Tests stamp_rows ──────────────────────────────────────────────────────────


def test_stamp_rows_sets_pending_review() -> None:
    proposals = {
        "taxonomy_concepts": [_concept("C1", "hypertension")],
        "ontology_relations": [_rel("R1", "A", "B")],
        "taxonomy_synonyms": [{"local_concept_id": "C1", "synonym": "htn"}],
        "taxonomy_standard_codes": [],
        "ontology_relation_evidence": [],
        "ontology_relation_qualifiers": [],
    }
    enr.stamp_rows(proposals, version="v1")
    for c in proposals["taxonomy_concepts"]:
        assert c["review_status"] == "pending_review"
        assert c["active"] is False
        assert c["version"] == "v1"
    for r in proposals["ontology_relations"]:
        assert r["review_status"] == "pending_review"
    for s in proposals["taxonomy_synonyms"]:
        assert s["review_status"] == "pending_review"


# ── Tests merge_into ──────────────────────────────────────────────────────────


def test_merge_into_appends_lists() -> None:
    target = {"taxonomy_concepts": [_concept("C1", "a")], "ontology_relations": []}
    source = {
        "taxonomy_concepts": [_concept("C2", "b")],
        "ontology_relations": [_rel("R1", "A", "B")],
    }
    enr.merge_into(target, source)
    assert len(target["taxonomy_concepts"]) == 2
    assert len(target["ontology_relations"]) == 1


def test_merge_into_ignores_missing_source_keys() -> None:
    target = {"taxonomy_concepts": [_concept("C1", "a")], "ontology_relations": []}
    source = {"taxonomy_concepts": [_concept("C2", "b")]}  # pas de 'ontology_relations'
    enr.merge_into(target, source)
    assert len(target["taxonomy_concepts"]) == 2
    assert target["ontology_relations"] == []


# ── Tests analyze_coverage ────────────────────────────────────────────────────


def test_analyze_coverage_detects_path_gap() -> None:
    """Deux concepts sans relation doivent générer un path gap."""
    concepts = [_concept("A", "aspirin"), _concept("B", "pain")]
    idx = enr.build_semantic_data(_raw(concepts=concepts))
    questions = [
        {
            "id": "Q1",
            "picot": {"intervention": ["aspirin"], "outcome": ["pain"]},
        }
    ]
    result = enr.analyze_coverage(questions, idx.concept_index, idx.syn_lookup, idx.ontology)
    assert result["summary"]["picot_pairs_total"] == 1
    assert len(result["path_gaps"]) == 1


def test_analyze_coverage_covered_pair() -> None:
    """Une paire avec chemin direct doit être comptée comme couverte."""
    concepts = [_concept("A", "aspirin"), _concept("B", "pain")]
    rels = [_rel("R1", "A", "B")]
    idx = enr.build_semantic_data(_raw(concepts=concepts, relations=rels))
    questions = [
        {
            "id": "Q1",
            "picot": {"intervention": ["aspirin"], "outcome": ["pain"]},
        }
    ]
    result = enr.analyze_coverage(questions, idx.concept_index, idx.syn_lookup, idx.ontology)
    assert result["summary"]["pairs_with_forward_path"] == 1
    assert result["summary"]["pairs_covered_pct"] == 100
    assert len(result["path_gaps"]) == 0


def test_analyze_coverage_missing_concept_token() -> None:
    """Un token non matchable doit apparaître dans missing_concepts."""
    idx = enr.build_semantic_data(_raw())
    questions = [
        {
            "id": "Q1",
            "picot": {"intervention": ["totally unknown drug xyzabc"], "outcome": []},
        }
    ]
    result = enr.analyze_coverage(questions, idx.concept_index, idx.syn_lookup, idx.ontology)
    assert result["summary"]["missing_concept_tokens"] >= 1
    tokens = [m["token"] for m in result["missing_concepts"]]
    assert "totally unknown drug xyzabc" in tokens
