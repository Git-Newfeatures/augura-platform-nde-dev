"""Tests du parseur de fichiers (CSV/XLSX)."""

import io

import pytest
from openpyxl import Workbook

from augura_api.core.errors import PayloadTooLargeError, UnsupportedMediaTypeError
from augura_api.modules.datasets.parsing import MAX_UPLOAD_BYTES, parse_upload


def test_parse_csv() -> None:
    data = b"id,age,sex\n1,40,M\n2,55,F\n"
    sheets = parse_upload("cohort.csv", data)
    assert len(sheets) == 1
    s = sheets[0]
    assert s.headers == ["id", "age", "sex"]
    assert s.rows == [["1", "40", "M"], ["2", "55", "F"]]


def test_parse_xlsx() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["id", "age"])
    ws.append([1, 40])
    ws.append([2, 55])
    buf = io.BytesIO()
    wb.save(buf)
    sheets = parse_upload("cohort.xlsx", buf.getvalue())
    assert sheets[0].headers == ["id", "age"]
    assert sheets[0].rows == [["1", "40"], ["2", "55"]]


def test_unsupported_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        parse_upload("data.xls", b"\x00\x01")


def test_oversize() -> None:
    with pytest.raises(PayloadTooLargeError):
        parse_upload("big.csv", b"x" * (MAX_UPLOAD_BYTES + 1))
