from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import Field
from sqlalchemy.orm import Session

from app.rag.context import ExtractionResult, RetrievedContext
from app.contracts.predictions import ModelPrediction
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


@dataclass(frozen=True)
class AnalysisPipeline:
    retrieve: ContextRetriever
    extractor: FindingExtractor
    evaluate: Callable[[UUID, list[StructuredFinding], list[TriggerRuleRead]], list[TriggerEvaluation]]
