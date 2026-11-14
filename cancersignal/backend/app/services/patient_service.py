from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter, Patient
from app.schemas.records import PatientCreate
from app.services.errors import ServiceError


def get_patient(session: Session, patient_id: UUID) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise ServiceError(404, "Patient not found.")
    return patient


def list_patients(session: Session, limit: int = 100, offset: int = 0):
    return session.scalars(select(Patient).order_by(Patient.id).limit(limit).offset(offset)).all()


def create_patient(session: Session, payload: PatientCreate):
    if not payload.synthetic_name.upper().startswith("SYNTHETIC "):
        raise ServiceError(422, "Use an explicitly synthetic name beginning with 'SYNTHETIC '.")
    patient = Patient(**payload.model_dump())
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient


def list_encounters(session: Session, patient_id: UUID, limit: int = 100, offset: int = 0):
    get_patient(session, patient_id)
    return session.scalars(select(Encounter).where(Encounter.patient_id == patient_id)
        .order_by(Encounter.occurred_at, Encounter.id).limit(limit).offset(offset)).all()
