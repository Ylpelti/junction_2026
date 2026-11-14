"""Protocols only: component implementations own storage/provider dependencies."""
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from app.contracts.analysis import TriggerEvaluation
from app.contracts.clinical_context import RetrievedContext, SourceObservation, StructuredPatientContext
from app.contracts.common import PatientScope
from app.contracts.features import ComputedFeature
from app.contracts.findings import ClinicalFinding
from app.contracts.stages import FeatureBatch, FindingBatch
from app.schemas.records import TriggerRuleRead


class ObservationResolver(Protocol):
    def __call__(self, patient_id: UUID, observation_ids: tuple[UUID, ...]) -> Iterable[SourceObservation]: ...


class ContextRetriever(Protocol):
    def __call__(self, *, scope: PatientScope, query: str) -> RetrievedContext: ...


class StructuredDataAccess(Protocol):
    def __call__(self, *, scope: PatientScope, codes: tuple[str, ...] | None = None) -> StructuredPatientContext: ...


class FindingExtractor(Protocol):
    def __call__(self, context: RetrievedContext, *, input_note: SourceObservation | None = None) -> FindingBatch: ...


class FeatureComputer(Protocol):
    def __call__(self, context: StructuredPatientContext) -> FeatureBatch: ...


class TriggerEvaluator(Protocol):
    def __call__(self, *, scope: PatientScope, findings: tuple[ClinicalFinding, ...],
                 features: tuple[ComputedFeature, ...], rules: tuple[TriggerRuleRead, ...]) -> tuple[TriggerEvaluation, ...]: ...
