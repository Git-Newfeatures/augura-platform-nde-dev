"""Tests de l'index + matcher + confidence."""

from dataclasses import dataclass

from augura_api.modules.mapping.confidence import compute_confidence
from augura_api.modules.mapping.index import build_index
from augura_api.modules.mapping.matcher import match_column
from augura_api.modules.mapping.normalize import normalize


@dataclass
class _C:
    local_concept_id: str
    concept_name: str
    dq_column_role: str | None


@dataclass
class _S:
    local_concept_id: str
    synonym: str


def _index():
    concepts = [
        _C("hba1c", "Hemoglobin A1c", "value"),
        _C("sbp", "Systolic Blood Pressure", "value"),
    ]
    synonyms = [_S("hba1c", "HbA1c"), _S("hba1c", "glycated hemoglobin"), _S("sbp", "SBP")]
    return build_index(concepts, synonyms)


def test_exact_synonym_match() -> None:
    idx = _index()
    cands = match_column(normalize("HbA1c"), idx)
    assert cands and cands[0].concept_id == "hba1c"
    assert cands[0].method == "exact_synonym"
    assert compute_confidence(cands)["label"] == "High"


def test_no_match_is_unmapped() -> None:
    idx = _index()
    cands = match_column(normalize("random_widget_xyz"), idx)
    assert compute_confidence(cands)["score"] == 0.0
