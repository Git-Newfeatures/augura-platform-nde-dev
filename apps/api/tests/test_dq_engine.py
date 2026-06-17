"""Test du moteur DQ end-to-end sur des feuilles en mémoire (sans base)."""

from augura_api.modules.dq.engine import run_dq

SHEETS = [
    {
        "name": "data",
        "headers": ["id", "val", "flag"],
        "rows": [
            ["1", "9", "Y"],
            ["2", "9", "Y"],
            ["3", "10", "Y"],
            ["4", "10", "Y"],
            ["5", "", "N"],  # missing → 2/10 = 20%
            ["6", "10", "Y"],
            ["7", "10", "Y"],
            ["8", "", "N"],  # 2nd missing
            ["9", "11", "Y"],
            ["10", "1000", "Y"],  # 1000 = IQR outlier (upper fence ~14)
        ],
    }
]


def test_run_dq_produces_scored_bundle() -> None:
    bundle = run_dq(SHEETS, raw_bytes=b"id,val,flag\n", weight_profile="exploratory")
    assert bundle["meta"]["score_profile"] == "exploratory"
    assert "dataset_fingerprint" in bundle["meta"]
    assert 0.0 <= bundle["summary"]["overall_score"] <= 1.0
    # missing-rate finding for "val" (1/5 = 20% → soft) and an IQR outlier finding
    cats = {f["category"] for f in bundle["provenance"]}
    assert "missing" in cats
    assert "range" in cats
    assert bundle["check_plan"]["execution"]["total_registered"] >= 4
