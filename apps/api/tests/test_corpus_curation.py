"""Curation LLM (re-ranking par abstract) — helper de mapping pur + LLMCurator mocké.

Aucun réseau : le mapping est pur ; le LLMCurator est testé avec un client LLM factice
(même pattern que test_agents_dag.py)."""

from typing import Any

from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.modules.corpus.curation import (
    CuratedRef,
    CurationCandidate,
    LLMCurator,
    apply_curation,
)


def _msg(tool_input: dict[str, Any]) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name="curate_results", input=tool_input)
    ]
    return Message(
        id="msg_1",
        content=content,
        model="claude-haiku-4-5-20251001",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


class _FakeMessages:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = responses
        self.calls = 0
        self.last_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Message:
        self.calls += 1
        self.last_kwargs = kwargs
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, *responses: Message) -> None:
        self.messages = _FakeMessages(list(responses))


def test_apply_curation_reorders_and_drops() -> None:
    by_id = {"a": "RecA", "b": "RecB", "c": "RecC"}
    refs = [CuratedRef(id="c", rationale="plus pertinent"), CuratedRef(id="a", rationale="ok")]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecC", "plus pertinent"), ("RecA", "ok")]


def test_apply_curation_ignores_hallucinated_and_dupes() -> None:
    by_id = {"a": "RecA"}
    refs = [
        CuratedRef(id="zzz", rationale="inventé"),
        CuratedRef(id="a", rationale="1"),
        CuratedRef(id="a", rationale="2"),
    ]
    out = apply_curation(refs, by_id, max_results=10)
    assert out == [("RecA", "1")]


def test_apply_curation_caps_at_max_results() -> None:
    by_id = {"a": "A", "b": "B", "c": "C"}
    refs = [CuratedRef("a", ""), CuratedRef("b", ""), CuratedRef("c", "")]
    out = apply_curation(refs, by_id, max_results=2)
    assert [rec for rec, _ in out] == ["A", "B"]


def test_apply_curation_empty_when_nothing_matches() -> None:
    out = apply_curation([CuratedRef("zzz", "x")], {"a": "A"}, max_results=10)
    assert out == []


async def test_llm_curator_returns_ordered_refs() -> None:
    client = _FakeClient(
        _msg(
            {
                "selected": [
                    {"id": "2", "rationale": "RCT directement sur la question"},
                    {"id": "1", "rationale": "pertinent mais observationnel"},
                ]
            }
        )
    )
    curator = LLMCurator(client, "claude-haiku-4-5-20251001")  # type: ignore[arg-type]
    cands = [
        CurationCandidate("1", "Obs study", "abstract 1"),
        CurationCandidate("2", "RCT", "abstract 2"),
    ]
    refs = await curator.curate("hba1c", "pubmed", cands, max_results=5)
    assert [r.id for r in refs] == ["2", "1"]
    assert refs[0].rationale.startswith("RCT")


async def test_llm_curator_empty_candidates_skips_call() -> None:
    client = _FakeClient()
    curator = LLMCurator(client, "m")  # type: ignore[arg-type]
    assert await curator.curate("q", "pubmed", [], max_results=5) == []
    assert client.messages.calls == 0
