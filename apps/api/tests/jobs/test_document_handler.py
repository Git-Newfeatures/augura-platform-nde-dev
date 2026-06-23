"""handle_document: generates the document and persists the bytes IN THE DB (never on disk).

On Modal the `run_job` worker and the ASGI container are separate containers with an
ephemeral filesystem: a document written to disk by the worker is not found on the
ASGI side at download time (404). The content must therefore live in
generated_documents.content, not via core.storage.save_bytes.
"""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from augura_api.core.config import Settings
from augura_api.core.ids import TenantId, UserId


@pytest.mark.asyncio
async def test_handle_document_persists_content_in_db_not_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()

    async def fake_list_results(self: Any, *_a: Any, **_k: Any) -> list[Any]:
        return []

    async def fake_source_counts(self: Any) -> list[Any]:
        return []

    def fake_render(**_kwargs: Any) -> str:
        return "<html><body>document</body></html>"

    captured: dict[str, Any] = {}

    async def fake_set_status(self: Any, _tenant_id: Any, _document_id: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    async def fake_create_artifact(*_a: Any, **kwargs: Any) -> None:
        captured["storage_ref"] = kwargs.get("storage_ref")

    async def fake_log_usage(*_a: Any, **_k: Any) -> None:
        return None

    disk_writes: list[Any] = []

    def fake_save_bytes(*_a: Any, **_k: Any) -> str:
        disk_writes.append(_k)
        return "should-not-be-called"

    monkeypatch.setattr(
        "augura_api.modules.simulation.repo.SimulationRepo.list_results", fake_list_results
    )
    monkeypatch.setattr(
        "augura_api.modules.corpus.repo.CorpusRepo.source_counts", fake_source_counts
    )
    monkeypatch.setattr("augura_api.jobs.handlers.render_document_html", fake_render)
    monkeypatch.setattr(
        "augura_api.modules.documents.repo.DocumentRepo.set_status", fake_set_status
    )
    monkeypatch.setattr("augura_api.modules.analytics.create_artifact", fake_create_artifact)
    monkeypatch.setattr("augura_api.modules.analytics.log_usage", fake_log_usage)
    # Safety net: any disk write must fail the test (Modal bug regression).
    monkeypatch.setattr("augura_api.core.storage.save_bytes", fake_save_bytes)

    from augura_api.jobs.handlers import handle_document

    job = SimpleNamespace(
        id=uuid4(),
        type="generate_report",
        payload={"document_id": str(document_id), "study_id": None},
    )
    ctx = SimpleNamespace(
        session=object(),
        settings=Settings(env="dev"),  # type: ignore[call-arg]
        tenant_id=TenantId(uuid4()),
        user_id=UserId(uuid4()),
        job=job,
    )

    await handle_document(ctx)  # type: ignore[arg-type]

    assert disk_writes == []  # nothing on the ephemeral disk
    assert captured["status"] == "ready"
    assert captured["content"] == b"<html><body>document</body></html>"
    # storage_path stays a stable logical identifier (provenance), not a disk file.
    assert str(document_id) in captured["storage_path"]
    assert captured["storage_ref"] == captured["storage_path"]


def test_document_handlers_registered() -> None:
    from augura_api.jobs.handlers import build_handlers

    handlers = build_handlers()
    assert "generate_protocol" in handlers
    assert "generate_report" in handlers
