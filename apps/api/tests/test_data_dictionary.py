import csv
import io

import pytest

from augura_api.core.config import get_settings
from augura_api.core.errors import UnsupportedMediaTypeError
from augura_api.core.llm.runtime import AgentUpstreamError
from augura_api.modules.datasets.data_dictionary import parse_data_dictionary


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


async def test_structured_dictionary_csv_is_parsed_deterministically() -> None:
    data = _csv(
        [
            ["variable", "label", "type", "description", "allowed values"],
            ["hba1c", "HbA1c (%)", "numeric", "Glycated hemoglobin", ""],
            ["sex", "Sex", "categorical", "Patient sex", "M; F; Other"],
        ]
    )
    res = await parse_data_dictionary(get_settings(), "dict.csv", data)
    assert res.source_kind == "structured"
    assert [e.name for e in res.entries] == ["hba1c", "sex"]
    sex = res.entries[1]
    assert sex.label == "Sex"
    assert sex.value_type == "categorical"
    assert sex.allowed_values == ["M", "F", "Other"]


async def test_non_dictionary_csv_falls_back_to_llm_and_503_without_key() -> None:
    # A plain data table (no descriptive columns) is not dictionary-shaped → free-form path,
    # which needs an LLM key. The test env has none → AgentUpstreamError (503).
    data = _csv([["a", "b", "c"], ["1", "2", "3"]])
    with pytest.raises(AgentUpstreamError):
        await parse_data_dictionary(get_settings(), "data.csv", data)


async def test_unsupported_extension_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        await parse_data_dictionary(get_settings(), "dict.pdf", b"whatever")
