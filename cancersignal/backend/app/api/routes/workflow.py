from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.schemas.workflow import DismissalCreate, DismissalRead, DecisionCreate, DecisionRead
from app.services import workflow_service

router = APIRouter(tags=["demo workflow"])


@router.post("/analyses/{analysis_id}/dismissal", response_model=DismissalRead, status_code=201)
def dismiss(analysis_id: UUID, payload: DismissalCreate, session: Session = Depends(get_session)):
    return workflow_service.create_dismissal(session, analysis_id, payload)


@router.get("/analyses/{analysis_id}/dismissal", response_model=DismissalRead)
def dismissal(analysis_id: UUID, session: Session = Depends(get_session)):
    return workflow_service.get_dismissal(session, analysis_id)


@router.post("/review-requests/{request_id}/decision", response_model=DecisionRead, status_code=201)
def decide(request_id: UUID, payload: DecisionCreate, session: Session = Depends(get_session)):
    return workflow_service.create_decision(session, request_id, payload)


@router.get("/review-requests/{request_id}/decision", response_model=DecisionRead)
def decision(request_id: UUID, session: Session = Depends(get_session)):
    return workflow_service.get_decision(session, request_id)
