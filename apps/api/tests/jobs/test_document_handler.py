"""handle_document : génère le dossier et persiste les octets EN BASE (jamais sur disque).

Sur Modal le worker `run_job` et le conteneur ASGI sont des conteneurs distincts au
système de fichiers éphémère : un dossier écrit sur disque par le worker est introuvable
côté ASGI au moment du download (404). Le contenu doit donc vivre dans
generated_documents.content, pas via core.storage.save_bytes.
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
        return "<html><body>dossier</body></html>"

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
    # Filet : tout écrit sur disque doit faire échouer le test (régression du bug Modal).
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

    assert disk_writes == []  # rien sur le disque éphémère
    assert captured["status"] == "ready"
    assert captured["content"] == b"<html><body>dossier</body></html>"
    # storage_path reste un identifiant logique stable (provenance), pas un fichier disque.
    assert str(document_id) in captured["storage_path"]
    assert captured["storage_ref"] == captured["storage_path"]


def test_document_handlers_registered() -> None:
    from augura_api.jobs.handlers import build_handlers

    handlers = build_handlers()
    assert "generate_protocol" in handlers
    assert "generate_report" in handlers
