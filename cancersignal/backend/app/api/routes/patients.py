from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.records import PatientCreate, PatientRead
from app.services import patient_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientRead])
def list_patients(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                  session: Session = Depends(get_session)):
    return patient_service.list_patients(session, limit, offset)


@router.post("", response_model=PatientRead, status_code=201)
def create_patient(payload: PatientCreate, session: Session = Depends(get_session)):
    return patient_service.create_patient(session, payload)


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: UUID, session: Session = Depends(get_session)):
    return patient_service.get_patient(session, patient_id)
