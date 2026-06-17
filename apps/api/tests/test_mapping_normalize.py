"""Tests du normaliseur lexical + similarité."""

from augura_api.modules.mapping.normalize import normalize, string_similarity


def test_normalize_abbrev_and_noise() -> None:
    assert normalize("HbA1c_value") == "hemoglobin a1c"
    assert normalize("Patient_ID") == "patient"  # 'id' is noise; 'patient' kept


def test_normalize_timepoint_and_separators() -> None:
    assert normalize("cgm_tir.BL") == "continuous glucose monitoring tir"


def test_similarity_bounds() -> None:
    assert string_similarity("blood pressure", "blood pressure") > 0.99
    assert string_similarity("", "x") == 0.0
    assert 0.0 <= string_similarity("systolic bp", "systolic blood pressure") <= 1.0
