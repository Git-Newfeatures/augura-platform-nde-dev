"""LiteratureService : ingestion PubMed → corpus, dédup par URL, embedding optionnel.

Repo/PubMed/Embedder factices (pas de base, pas de réseau)."""

from typing import cast
from uuid import UUID, uuid4

from augura_api.core.ids import TenantId, UserId
from augura_api.core.llm.embeddings import Embedder
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus.models import Document
from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient
from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.corpus.service import LiteratureService

TENANT = CurrentTenant(
    tenant_id=TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44")),
    user_id=UserId(UUID("11111111-1111-4111-8111-111111111111")),
    role="member",
)

ARTICLES = [
    PubMedArticle(
        pmid="1", title="T1", abstract="A1", url="https://doi.org/10.1/a", evidence_type="rct"
    ),
    PubMedArticle(
        pmid="2",
        title="T2",
        abstract="",
        url="https://pubmed.ncbi.nlm.nih.gov/2/",
        evidence_type="review",
    ),
]


class FakePubMed:
    def __init__(self, articles: list[PubMedArticle]) -> None:
        self._articles = articles

    async def search(self, query: str, max_results: int) -> list[PubMedArticle]:
        return self._articles[:max_results]


class FakeEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [0.0] * 1536


class FakeRepo:
    def __init__(self) -> None:
        self.inserted: list[Document] = []
        self.chunks: list[tuple[object, list[float] | None]] = []

    async def find_document_by_url(self, tenant_id: TenantId, url: str) -> Document | None:
        return next((d for d in self.inserted if d.url == url), None)

    async def insert_document(self, tenant_id: TenantId, **kw: object) -> Document:
        doc = Document(id=uuid4(), org_id=tenant_id, **kw)  # type: ignore[arg-type]
        self.inserted.append(doc)
        return doc

    async def add_chunk(
        self,
        document_id: object,
        tenant_id: TenantId,
        *,
        content: str,
        embedding: list[float] | None,
        token_count: int | None = None,
    ) -> None:
        self.chunks.append((document_id, embedding))


def _service(repo: FakeRepo, embedder: Embedder | None = None) -> LiteratureService:
    return LiteratureService(
        cast(CorpusRepo, repo), cast(PubMedClient, FakePubMed(ARTICLES)), embedder=embedder
    )


async def test_ingests_then_dedupes_by_url() -> None:
    repo = FakeRepo()
    res = await _service(repo).search_and_ingest(TENANT, query="engagement", max_results=10)
    assert (res.found, res.ingested, res.embedded) == (2, 2, False)
    assert len(res.documents) == 2
    assert {d.source_id for d in res.documents} == {"pubmed"}

    # Re-run : mêmes URLs déjà présentes → 0 nouvelle ingestion.
    res2 = await _service(repo).search_and_ingest(TENANT, query="engagement", max_results=10)
    assert (res2.found, res2.ingested) == (2, 0)


async def test_embeds_chunks_when_embedder_present() -> None:
    repo = FakeRepo()
    res = await _service(repo, cast(Embedder, FakeEmbedder())).search_and_ingest(
        TENANT, query="engagement", max_results=10
    )
    assert res.embedded is True
    assert len(repo.chunks) == 2
    assert all(emb is not None for _doc, emb in repo.chunks)
