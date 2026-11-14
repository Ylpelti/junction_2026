from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue
from sqlalchemy.orm import Session

from app.rag.context import ExtractionResult, RetrievedContext
from app.schemas.analysis import StructuredFinding
from app.schemas.records import ObservationRead, Record, TriggerRuleRead


class FindingExtractor(Protocol):
    name: str

    def extract(self, context: RetrievedContext, note: ObservationRead) -> ExtractionResult: ...


class ContextRetriever(Protocol):
    def __call__(self, patient_id: UUID, query: str, db_session: Session, *, before: datetime) -> RetrievedContext: ...


class TriggerEvaluation(Record):
    trigger_rule_id: UUID
    triggered: bool
    explanation: str
    evidence_observation_ids: list[UUID] = Field(default_factory=list)


class ModelPrediction(Record):
    """Future output type, not accepted as an extracted fact; no model or persistence."""
    patient_id: UUID
    model_name: str
    model_version: str
    as_of: AwareDatetime
    prediction_type: str
    value: JsonValue
    evidence_observation_ids: list[UUID] = Field(default_factory=list)
    uncertainty: str | None = None


@dataclass(frozen=True)
class AnalysisPipeline:
    retrieve: ContextRetriever
    extractor: FindingExtractor
    evaluate: Callable[[UUID, list[StructuredFinding], list[TriggerRuleRead]], list[TriggerEvaluation]]
