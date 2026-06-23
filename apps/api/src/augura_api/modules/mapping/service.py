"""Business logic for the mapping module: dataset columns → concepts (lexical)."""

from uuid import UUID

from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.mapping import schemas
from augura_api.modules.mapping.confidence import compute_confidence
from augura_api.modules.mapping.index import build_index
from augura_api.modules.mapping.matcher import match_column
from augura_api.modules.mapping.normalize import normalize
from augura_api.modules.mapping.repo import MappingRepo
from augura_api.modules.semantic.repo import SemanticRepo


class MappingService:
    def __init__(self, repo: MappingRepo, datasets: DatasetRepo, semantic: SemanticRepo) -> None:
        self.repo = repo
        self.datasets = datasets
        self.semantic = semantic

    async def map_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.MapResult:
        dataset = await self.datasets.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None:
            raise NotFoundError("dataset not found", dataset_id=str(dataset_id))
        columns = await self.datasets.list_columns(dataset_id)
        concepts = await self.semantic.list_concepts()
        synonyms = await self.semantic.list_synonyms()
        index = build_index(concepts, synonyms)  # type: ignore[arg-type]

        out: list[schemas.ColumnProposal] = []
        confidences: list[float] = []
        mapped = 0
        for col in columns:
            cands = match_column(normalize(col.name), index)
            conf = compute_confidence(cands)
            score = float(conf["score"])  # type: ignore[arg-type]
            best = cands[0] if cands and score > 0 else None
            if best is not None:
                mapped += 1
                confidences.append(score)
                await self.repo.update_proposal(
                    col.id,
                    proposed_canonical_id=best.concept_id,
                    proposed_role=best.dq_column_role,
                    confidence=score,
                )
            out.append(
                schemas.ColumnProposal(
                    column=col.name,
                    sheet=col.sheet,
                    proposed_canonical_id=best.concept_id if best else None,
                    proposed_role=best.dq_column_role if best else None,
                    layer=best.layer if best else None,
                    domain=best.domain if best else None,
                    confidence=score if best else None,
                    confidence_label=str(conf["label"]),
                )
            )
        avg = sum(confidences) / len(confidences) if confidences else None
        return schemas.MapResult(
            dataset_id=dataset_id,
            mapped_count=mapped,
            total_count=len(columns),
            avg_confidence=(round(avg, 3) if avg is not None else None),
            columns=out,
        )
