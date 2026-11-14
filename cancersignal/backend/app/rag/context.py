from uuid import UUID

from pydantic import AwareDatetime, Field

from app.contracts.qcancer import QCancerPredictors
from app.contracts.clinical_context import RetrievedContext as SourceContext
from app.schemas.analysis import StructuredFinding
from app.schemas.records import ObservationRead, Record


class ContextObservation(Record):
    observation: ObservationRead
    source_excerpt: str | None


class RetrievedContext(Record):
    patient_id: UUID
    cutoff: AwareDatetime
    observations: list[ContextObservation]
    ranked_observation_ids: list[UUID]
    retrieval_method: str = "patient-history-lexical-v1"
    # Internal bridge only: retain the engine's coverage, scores and provenance.
    # Legacy/custom retrievers may continue returning the original fields alone.
    source_context: SourceContext | None = None


class ExtractionResult(Record):
    findings: list[StructuredFinding] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    qcancer_predictors: QCancerPredictors | None = None
