"""handle_enrich_propose: runs the (mocked) pipeline and persists the result IN THE DB."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from augura_api.core.config import Settings
from augura_api.core.ids import TenantId, UserId


@pytest.mark.asyncio
async def test_handle_enrich_propose_stores_result_in_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def fake_read_bundle(self: Any) -> dict[str, Any]:
        return {"taxonomy_concepts": [], "causal_predicates": []}

    async def fake_propose(**_kwargs: Any) -> dict[str, Any]:
        return {
            "proposals": {"taxonomy_concepts": [], "ontology_relations": []},
            "coverage_summary": {"pairs_covered_pct": 0},
            "summary": {"taxonomy_concepts": 0},
            "precheck_log": [],
        }

    async def fake_log_usage(*_a: Any, **_k: Any) -> None:
        return None

    captured: dict[str, Any] = {}

    async def fake_set_result_json(
        _session: Any, _tenant_id: Any, _job_id: Any, result_json: dict[str, Any]
    ) -> None:
        captured["result"] = result_json

    monkeypatch.setattr(
        "augura_api.modules.semantic.repo.SemanticRepo.read_bundle", fake_read_bundle
    )
    monkeypatch.setattr("augura_api.modules.semantic.enrich_propose.propose", fake_propose)
    monkeypatch.setattr("augura_api.modules.analytics.log_usage", fake_log_usage)
    # The result is stored IN THE DB (jobs.result_json), not on disk.
    monkeypatch.setattr("augura_api.modules.jobs.set_result_json", fake_set_result_json)

    from augura_api.jobs.handlers import handle_enrich_propose

    job = SimpleNamespace(
        id=uuid4(),
        type="enrich_propose",
        payload={"questions": [{"id": "q1", "picot": {}}], "selected_concepts": []},
    )
    ctx = SimpleNamespace(
        session=object(),
        settings=Settings(env="dev"),  # type: ignore[call-arg]
        tenant_id=TenantId(uuid4()),
        user_id=UserId(uuid4()),
        job=job,
    )

    ref = await handle_enrich_propose(ctx)  # type: ignore[arg-type]
    assert ref is None  # no more disk artifact: the result is in the DB

    data = captured["result"]
    assert "proposals" in data
    assert "coverage_summary" in data
    assert "generated_at" in data


def test_enrich_propose_registered() -> None:
    from augura_api.jobs.handlers import build_handlers

    assert "enrich_propose" in build_handlers()
