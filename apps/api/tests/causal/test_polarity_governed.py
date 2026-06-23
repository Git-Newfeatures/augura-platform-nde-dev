"""The DAG tool schema shares the governed polarity enum (no more mixed/unknown)."""

from typing import Any, cast

from augura_api.modules.causal.prompt import DAG_FILTER_TOOL
from augura_api.modules.semantic import vocab


def test_dag_tool_polarity_enum_matches_governed_vocab() -> None:
    props = cast(dict[str, Any], DAG_FILTER_TOOL["input_schema"])["properties"]
    rel_props = props["proposed_relations"]["items"]["properties"]
    assert rel_props["polarity"]["enum"] == vocab.POLARITY
