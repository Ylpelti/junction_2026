from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.reviews import ReviewRequestCreate, ReviewRequestResponse
from app.services import review_service

router = APIRouter(tags=["physician review"])


@router.post("/patients/{patient_id}/review-requests", response_model=ReviewRequestResponse, status_code=201,
             responses={200: {"model": ReviewRequestResponse, "description": "Existing request; no duplicate created"}})
def submit_review_request(patient_id: UUID, payload: ReviewRequestCreate, response: Response,
                          session: Session = Depends(get_session)):
    result, created = review_service.create_review_request(session, patient_id, payload)
    response.status_code = 201 if created else 200
    response.headers["Location"] = f"/api/v1/review-requests/{result.id}"
    return result


@router.get("/review-requests", response_model=list[ReviewRequestResponse])
def review_queue(status: Literal["pending", "reviewed", "all"] = "pending", patient_id: UUID | None = None,
                 limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                 session: Session = Depends(get_session)):
    return review_service.list_review_requests(session, status=status, patient_id=patient_id, limit=limit, offset=offset)


@router.get("/review-requests/{request_id}", response_model=ReviewRequestResponse)
def review_request(request_id: UUID, session: Session = Depends(get_session)):
    return review_service.get_review_request(session, request_id)
