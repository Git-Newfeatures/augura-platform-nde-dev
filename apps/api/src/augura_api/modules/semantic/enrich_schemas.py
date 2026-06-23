"""Public contract of the enrichment routes (B4) — apply + propose."""

from pydantic import BaseModel


class DirectRelationIn(BaseModel):
    """Lightweight relation proposed by the DAG (no pre-assigned id)."""

    subject_concept_id: str
    object_concept_id: str
    predicate: str
    polarity: str = "neutral"
    default_strength: str = "moderate"
    mechanism_summary: str = ""
    relation_id: str | None = None  # provisional DAG id (reconciled on return)


class DeactivateRelationIn(BaseModel):
    relation_id: str


class AddQualifierIn(BaseModel):
    relation_id: str
    qualifier_type: str
    qualifier_value: str
    qualifier_effect: str
    is_hard_constraint: bool = False
    notes: str = ""


class EnrichApplyRequest(BaseModel):
    """Body of POST /semantic/enrich/apply — only one path provided at a time."""

    proposals: dict[str, object] | None = None
    selected_concept_ids: list[str] = []
    selected_relation_ids: list[str] = []
    direct_relations: list[DirectRelationIn] = []
    deactivate_relation: DeactivateRelationIn | None = None
    add_qualifier: AddQualifierIn | None = None


class EnrichApplyResponse(BaseModel):
    new_version: str
    previous_version: str
    concepts_added: int = 0
    relations_added: int = 0
    relation_id_map: dict[str, str] = {}
    detail: str = ""


class PicotQuestionIn(BaseModel):
    id: str
    therapeutic_area: str | None = None
    picot: dict[str, object] = {}  # {intervention?, comparator?, outcome?: list[str]}


class EnrichProposeRequest(BaseModel):
    questions: list[PicotQuestionIn] = []
    selected_concepts: list[dict[str, object]] = []


class EnrichProposeAccepted(BaseModel):
    job_id: str
