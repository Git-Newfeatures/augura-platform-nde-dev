"""Tests des checks DQ A3b (file/column/table data-only)."""

from augura_api.modules.dq.engine import run_dq
from augura_api.modules.dq.profiler import profile_column


def _ctx_col(values: list[str]):
    return {"table": "t", "column": "c", "profile": profile_column("c", values), "values": values}


def test_sentinel_check_flags_minus999() -> None:
    from augura_api.modules.dq.checks import sentinel_values

    out = sentinel_values(_ctx_col(["1", "2", "-999", "3"]))
    assert out and out[0]["check_id"] == "DQ_MISS_002"


def test_mixed_date_formats() -> None:
    from augura_api.modules.dq.checks import mixed_date_formats

    out = mixed_date_formats(_ctx_col(["2024-01-01", "01/02/2024", "2024-03-03", "04/05/2024"]))
    assert out and out[0]["check_id"] == "DQ_TYPE_002"


def test_non_ascii() -> None:
    from augura_api.modules.dq.checks import non_ascii_encoding

    out = non_ascii_encoding({"raw_bytes": "café\n".encode()})
    assert out and out[0]["check_id"] == "DQ_FILE_003"


def test_co_missingness_table_scope() -> None:
    # two numeric columns missing on the same rows → high correlation
    sheets = [
        {
            "name": "data",
            "headers": ["a", "b"],
            "rows": [["1", "10"], ["", ""], ["3", "30"], ["", ""], ["5", "50"]],
        }
    ]
    bundle = run_dq(sheets, raw_bytes=b"a,b\n", weight_profile="exploratory")
    ids = {f["check_id"] for f in bundle["provenance"]}
    assert "DQ_MISS_004" in ids


def test_engine_runs_table_scope() -> None:
    bundle = run_dq(
        [{"name": "data", "headers": ["x"], "rows": [["1"], ["2"]]}],
        raw_bytes=b"x\n",
        weight_profile="exploratory",
    )
    assert "table" in bundle["check_plan"]["by_scope"]
