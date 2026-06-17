"""Logique métier du module dq."""

from uuid import UUID

from augura_api.core.config import Settings
from augura_api.core.errors import NotFoundError
from augura_api.core.storage import read_bytes
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.parsing import parse_upload
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.dq import schemas
from augura_api.modules.dq.engine import run_dq
from augura_api.modules.dq.repo import DqRepo


class DqService:
    def __init__(self, repo: DqRepo, datasets: DatasetRepo) -> None:
        self.repo = repo
        self.datasets = datasets

    async def run(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        dataset_id: UUID,
        *,
        weight_profile: str = "exploratory",
    ) -> schemas.DqRunResult:
        dataset = await self.datasets.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None or not dataset.storage_path:
            raise NotFoundError("dataset introuvable ou sans fichier", dataset_id=str(dataset_id))
        data = read_bytes(settings, dataset.storage_path)
        sheets = parse_upload(dataset.name, data)
        bundle = run_dq(
            [{"name": s.name, "headers": s.headers, "rows": s.rows} for s in sheets],
            raw_bytes=data,
            weight_profile=weight_profile,
        )
        row = await self.repo.create_bundle(
            tenant.tenant_id,
            dataset_id=dataset_id,
            score_profile=weight_profile,
            overall_score=bundle["summary"]["overall_score"],
            status=bundle["meta"]["status"],
            requires_resolution=bundle["summary"]["requires_resolution"],
            bundle=bundle,
        )
        return schemas.DqRunResult(
            bundle_id=row.id,
            status=row.status,
            overall_score=float(row.overall_score) if row.overall_score is not None else None,
        )

    async def latest(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.DqBundleOut:
        row = await self.repo.latest_for_dataset(tenant.tenant_id, dataset_id)
        if row is None:
            raise NotFoundError("aucun bundle DQ pour ce dataset", dataset_id=str(dataset_id))
        return schemas.DqBundleOut.model_validate(row)
