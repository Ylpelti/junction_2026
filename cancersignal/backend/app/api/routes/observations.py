from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import observation_filters
from app.db.session import get_session
from app.schemas.analysis import TimelineEvent
from app.schemas.records import ObservationCreate, ObservationRead
from app.services import observation_service

router = APIRouter(tags=["clinical records"])


@router.get("/patients/{patient_id}/observations", response_model=list[ObservationRead])
def observations(patient_id: UUID, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                 filters: dict = Depends(observation_filters), session: Session = Depends(get_session)):
    return observation_service.list_observations(session, patient_id, limit=limit, offset=offset, **filters)


@router.post("/patients/{patient_id}/observations", response_model=ObservationRead, status_code=201)
def create_observation(patient_id: UUID, payload: ObservationCreate, session: Session = Depends(get_session)):
    return observation_service.create_observation(session, patient_id, payload)


@router.get("/observations/{observation_id}", response_model=ObservationRead)
def observation(observation_id: UUID, session: Session = Depends(get_session)):
    return observation_service.get_observation(session, observation_id)


@router.get("/patients/{patient_id}/timeline", response_model=list[TimelineEvent])
def timeline(patient_id: UUID, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
             filters: dict = Depends(observation_filters), session: Session = Depends(get_session)):
    return observation_service.timeline(session, patient_id, limit=limit, offset=offset, **filters)
