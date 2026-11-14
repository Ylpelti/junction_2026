"""Persist review requests only; do not run extraction, rules or clinical actions."""
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.contracts.clinical_context import SourceObservation
from app.contracts.common import PatientScope
from app.contracts.validation import EvidenceValidationError, validate_evidence
from app.models import AnalysisRun, Observation, PhysicianReviewRequest
from app.models.enums import AnalysisStatus
from app.schemas.analysis import AnalysisResponse
from app.schemas.records import PatientRead
from app.schemas.reviews import ReviewRequestCreate, ReviewRequestRead, ReviewRequestResponse
from app.services.analysis_service import get_analysis
from app.services.errors import ServiceError
from app.services.patient_service import get_patient


def checked_analysis(session: Session, run: AnalysisRun) -> AnalysisResponse:
    if run.status != AnalysisStatus.COMPLETED:
        raise ServiceError(409, "Only completed analyses can be sent for physician review.")
    try:
        analysis = get_analysis(session, run.id)
        metadata = analysis.provenance
        if (analysis.status != AnalysisStatus.COMPLETED or metadata.error_code is not None
                or metadata.input_observation_id is None or metadata.cutoff is None):
            raise ValueError("Incomplete analysis provenance")
        note = session.get(Observation, metadata.input_observation_id)
        scope = PatientScope(patient_id=run.patient_id, as_of=metadata.cutoff)
        if note is None or not scope.permits(note, input_note_id=metadata.input_observation_id):
            raise ValueError("Invalid original input note")
        sources = tuple(SourceObservation.model_validate(row) for row in analysis.source_observations)
        if any(row.patient_id != run.patient_id for row in sources):
            raise ValueError("Invalid source patient")
        finding_source_ids = set()
        for finding in analysis.findings:
            if not finding.evidence or finding.patient_id != run.patient_id or finding.analysis_run_id != run.id:
                raise ValueError("Incomplete finding")
            validate_evidence(run.patient_id, finding.evidence, sources, scope=scope,
                              input_note_id=metadata.input_observation_id)
            finding_source_ids.update(ref.observation_id for ref in finding.evidence)
        for result in analysis.trigger_results:
            if (not set(result.evidence_observation_ids).issubset(finding_source_ids)
                    or (result.triggered and not result.evidence_observation_ids)):
                raise ValueError("Incomplete rule evidence")
    except (ValidationError, EvidenceValidationError, ValueError):
        raise ServiceError(409, "Analysis provenance or original evidence is incomplete or invalid.") from None
    return analysis


def response_for(session: Session, row: PhysicianReviewRequest, analysis: AnalysisResponse | None = None):
    return ReviewRequestResponse(**ReviewRequestRead.model_validate(row).model_dump(),
        patient=PatientRead.model_validate(row.patient),
        analysis=analysis if analysis is not None else checked_analysis(session, row.analysis_run))


def create_review_request(session: Session, patient_id: UUID, payload: ReviewRequestCreate):
    get_patient(session, patient_id)
    # Serialize submissions/status changes for this analysis. The unique key and
    # ON CONFLICT also enforce idempotency if another writer bypasses this lock.
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.id == payload.analysis_id,
        AnalysisRun.patient_id == patient_id).with_for_update())
    if run is None:
        raise ServiceError(404, "Analysis not found for this patient.")
    analysis = checked_analysis(session, run)
    triggered = [result for result in analysis.trigger_results if result.triggered]
    priority = ("urgent" if any(result.priority == "urgent" for result in triggered)
                else "review" if triggered else "normal")
    inserted_id = session.scalar(insert(PhysicianReviewRequest).values(
        patient_id=patient_id, analysis_id=run.id, priority=priority, submitted_by=payload.submitted_by,
    ).on_conflict_do_nothing(index_elements=[PhysicianReviewRequest.analysis_id]).returning(PhysicianReviewRequest.id))
    row = session.scalar(select(PhysicianReviewRequest).where(PhysicianReviewRequest.analysis_id == run.id))
    result = response_for(session, row, analysis)
    session.commit()
    return result, inserted_id is not None


def list_review_requests(session: Session, *, patient_id: UUID | None = None, limit=100, offset=0):
    if patient_id is not None:
        get_patient(session, patient_id)
    statement = select(PhysicianReviewRequest).join(PhysicianReviewRequest.analysis_run).where(
        PhysicianReviewRequest.status == "pending", AnalysisRun.status == AnalysisStatus.COMPLETED,
        AnalysisRun.details["error_code"].as_string().is_(None),
        AnalysisRun.details["input_observation_id"].as_string().is_not(None),
        AnalysisRun.details["cutoff"].as_string().is_not(None),
    ).options(selectinload(PhysicianReviewRequest.patient), selectinload(PhysicianReviewRequest.analysis_run))
    if patient_id is not None:
        statement = statement.where(PhysicianReviewRequest.patient_id == patient_id)
    # Server priority first, FIFO within each priority, UUID for deterministic ties.
    statement = statement.order_by(case({"urgent": 0, "review": 1, "normal": 2},
        value=PhysicianReviewRequest.priority, else_=3), PhysicianReviewRequest.created_at, PhysicianReviewRequest.id)
    return [response_for(session, row) for row in session.scalars(statement.limit(limit).offset(offset))]


def get_review_request(session: Session, request_id: UUID):
    row = session.get(PhysicianReviewRequest, request_id)
    if row is None:
        raise ServiceError(404, "Review request not found.")
    return response_for(session, row)
