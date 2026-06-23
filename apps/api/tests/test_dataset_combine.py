"""Unit tests for the multi-file union/concat helper (no DB)."""

from augura_api.modules.datasets.combine import (
    combine_sheets,
    file_headers,
    file_warnings,
)
from augura_api.modules.datasets.parsing import parse_upload


def test_union_appends_new_columns_and_blank_fills() -> None:
    f1 = parse_upload("a.csv", b"id,age\n1,40\n2,50\n")
    f2 = parse_upload("b.csv", b"id,age,crp\n3,60,5\n")
    combined = combine_sheets([("a.csv", f1), ("b.csv", f2)])
    assert len(combined) == 1
    sheet = combined[0]
    assert sheet.headers == ["id", "age", "crp"]
    assert len(sheet.rows) == 3
    assert sheet.rows[0] == ["1", "40", ""]
    assert sheet.rows[2] == ["3", "60", "5"]


def test_file_headers_dedup_across_sheets() -> None:
    sheets = parse_upload("a.csv", b"id,age\n1,40\n")
    assert file_headers(sheets) == ["id", "age"]


def test_file_warnings_added_and_missing() -> None:
    assert file_warnings(["id", "age"], ["id", "age", "crp"], "b.csv") == [
        "b.csv added column(s): crp"
    ]
    assert file_warnings(["id", "age", "crp"], ["id", "age"], "c.csv") == [
        "c.csv missing column(s): crp — filled blank"
    ]
    assert file_warnings(["id", "age"], ["id", "age"], "d.csv") == []
