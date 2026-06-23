"""Orchestration of the causal module: B1 ontology → subgraph → LLM → graph.

Port of `dag-generator.js` (generateDAG). The LLM client is injected (Protocol);
tests run against a mocked LLM, without a key or Modal.
"""

from typing import Protocol

import structlog

from augura_api.core.config import Settings
from augura_api.core.llm.runtime import LLMClient, run_structured_agent
from augura_api.modules.causal import schemas
from augura_api.modules.causal.builder import assemble_dag
from augura_api.modules.causal.prompt import DAG_FILTER_TOOL, SYSTEM_PROMPT, build_user_prompt
from augura_api.modules.causal.subgraph import (
    ConceptMeta,
    Relation,
    build_relations,
    cap_candidates,
    causal_subgraph,
    concept_index,
)
from augura_api.modules.semantic.models import (
    OntologyRelation,
    OntologyRelationEvidence,
    OntologyRelationQualifier,
    TaxonomyConcept,
)

log = structlog.get_logger(__name__)


class _OntologyReader(Protocol):
    async def list_relations(self, *, active: bool = ...) -> list[OntologyRelation]: ...
    async def list_relation_evidence(self) -> list[OntologyRelationEvidence]: ...
    async def list_relation_qualifiers(self) -> list[OntologyRelationQualifier]: ...
    async def list_concepts(
        self, *, domain: str | None = ..., active: bool = ...
    ) -> list[TaxonomyConcept]: ...


class CausalService:
    def __init__(self, repo: _OntologyReader, client: LLMClient, settings: Settings) -> None:
        self.repo = repo
        self.client = client
        self.settings = settings

    async def generate(self, req: schemas.CausalDagRequest) -> schemas.CausalDagResponse:
        relations = build_relations(
            await self.repo.list_relations(),
            await self.repo.list_relation_evidence(),
            await self.repo.list_relation_qualifiers(),
        )
        meta_index = concept_index(await self.repo.list_concepts())
        mapped_ids = [m.concept_id for m in req.mapped_concepts]
        candidates = cap_candidates(causal_subgraph(relations, mapped_ids), mapped_ids)
        inferred = _inferred_concepts(candidates, set(mapped_ids), meta_index)

        log.info(
            "causal.dag.subgraph",
            mapped=len(mapped_ids),
            candidates=len(candidates),
            inferred=len(inferred),
        )
        result = await run_structured_agent(
            self.client,
            model=self.settings.agent_model_dag,
            system=SYSTEM_PROMPT,
            tool=DAG_FILTER_TOOL,
            messages=[
                {
                    "role": "user",
                    "content": build_user_prompt(
                        clinical_question=req.clinical_question,
                        picot=req.picot,
                        mapped=req.mapped_concepts,
                        candidates=candidates,
                        inferred=inferred,
                    ),
                }
            ],
            output_model=schemas.DagFilterResult,
            max_tokens=4000,
        )
        dag = assemble_dag(result.output, candidates, req.mapped_concepts, req.picot, meta_index)
        log.info(
            "causal.dag.assembled",
            nodes=len(dag.nodes),
            edges=len(dag.edges),
            quality=dag.quality.label,
        )
        return schemas.CausalDagResponse(
            clinical_question=req.clinical_question,
            graph=dag.graph,
            nodes=dag.nodes,
            edges=dag.edges,
            missing_variables=dag.missing_variables,
            warnings=dag.warnings,
            quality=dag.quality,
            llm_context=_llm_context(result.output, result.model, len(candidates), len(relations)),
            proposed_relations=result.output.proposed_relations,
        )


def _inferred_concepts(
    candidates: list[Relation], mapped_ids: set[str], meta_index: dict[str, ConceptMeta]
) -> list[tuple[str, ConceptMeta]]:
    ids = {cid for r in candidates for cid in (r.subject_concept_id, r.object_concept_id)}
    return [
        (cid, meta_index.get(cid, ConceptMeta(cid, "unknown", 0)))
        for cid in sorted(ids - mapped_ids)
    ]


def _llm_context(
    result: schemas.DagFilterResult, model: str, retrieved: int, total: int
) -> dict[str, object]:
    return {
        "reasoning": result.llm_reasoning,
        "model": model,
        "selected_count": len(result.selected_relations),
        "excluded_count": len(result.excluded_relations),
        "node_roles": {k: v.model_dump() for k, v in result.node_roles.items()},
        "candidate_relations_retrieved": retrieved,
        "total_ontology_relations": total,
        "proposed_concepts_count": len(result.proposed_concepts),
        "proposed_relations_count": len(result.proposed_relations),
    }
