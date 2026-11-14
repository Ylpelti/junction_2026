"""Explicit human demo actions, serialized against their existing workflow parent."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AnalysisRun, PhysicianReviewRequest, AlertDismissal, PhysicianDecision
from app.schemas.workflow import DismissalCreate, DismissalRead, DecisionCreate, DecisionRead
from app.services.errors import ServiceError
from app.services.review_service import checked_analysis


def create_dismissal(session: Session, analysis_id: UUID, payload: DismissalCreate):
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.id == analysis_id,
        AnalysisRun.patient_id == payload.patient_id).with_for_update())
    if run is None:
        raise ServiceError(404, "Analysis not found for this patient.")
    if session.scalar(select(AlertDismissal.id).where(AlertDismissal.analysis_id == analysis_id)):
        raise ServiceError(409, "This analysis already has a dismissal; retrieve the saved action.")
    if session.scalar(select(PhysicianReviewRequest.id).where(PhysicianReviewRequest.analysis_id == analysis_id)):
        raise ServiceError(409, "An analysis sent for physician review cannot be dismissed.")
    checked_analysis(session, run)
    row = AlertDismissal(analysis_id=analysis_id, **payload.model_dump())
    session.add(row)
    session.flush()
    result = DismissalRead.model_validate(row)
    session.commit()
    return result


def get_dismissal(session: Session, analysis_id: UUID):
    row = session.scalar(select(AlertDismissal).where(AlertDismissal.analysis_id == analysis_id))
    if row is None:
        raise ServiceError(404, "Dismissal not found for this analysis.")
    return DismissalRead.model_validate(row)


def create_decision(session: Session, request_id: UUID, payload: DecisionCreate):
    request = session.scalar(select(PhysicianReviewRequest).where(
        PhysicianReviewRequest.id == request_id).with_for_update().execution_options(populate_existing=True))
    if request is None:
        raise ServiceError(404, "Review request not found.")
    if request.status != "pending":
        raise ServiceError(409, "Review is already completed; decisions cannot be replaced.")
    if (payload.action == "acknowledged") != (request.priority == "normal"):
        raise ServiceError(409, "Acknowledge is for routine requests; alerts require FIT, referral or no action.")
    checked_analysis(session, request.analysis_run)
    row = PhysicianDecision(review_request_id=request_id, **payload.model_dump())
    session.add(row)
    request.status = "reviewed"
    session.flush()
    result = DecisionRead.model_validate(row)
    session.commit()
    return result


def get_decision(session: Session, request_id: UUID):
    row = session.scalar(select(PhysicianDecision).where(PhysicianDecision.review_request_id == request_id))
    if row is None:
        raise ServiceError(404, "Decision not found for this review request.")
    return DecisionRead.model_validate(row)
