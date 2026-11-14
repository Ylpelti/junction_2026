from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter, Observation
from app.models.enums import ObservationType
from app.schemas.analysis import TimelineEvent
from app.schemas.records import EncounterRead, ObservationCreate, ObservationRead
from app.services.errors import ServiceError
from app.services.patient_service import get_patient


def get_observation(session: Session, observation_id: UUID):
    record = session.get(Observation, observation_id)
    if record is None:
        raise ServiceError(404, "Observation not found.")
    return record


def create_observation(session: Session, patient_id: UUID, payload: ObservationCreate, *, commit=True):
    get_patient(session, patient_id)
    if payload.patient_id != patient_id:
        raise ServiceError(422, "Body patient_id must match the URL patient_id.")
    if payload.encounter_id is not None:
        encounter = session.get(Encounter, payload.encounter_id)
        if encounter is None or encounter.patient_id != patient_id:
            raise ServiceError(422, "Encounter must exist and belong to this patient.")
    record = Observation(**payload.model_dump())
    session.add(record)
    session.flush()
    if commit:
        session.commit()
        session.refresh(record)
    return record


def observation_query(patient_id: UUID, observation_type: ObservationType | None = None,
                      date_from: datetime | None = None, date_to: datetime | None = None,
                      code: str | None = None):
    if date_from is not None and date_to is not None and date_from >= date_to:
        raise ServiceError(422, "date_from must be earlier than date_to.")
    query = select(Observation).where(Observation.patient_id == patient_id)
    if observation_type is not None:
        query = query.where(Observation.observation_type == observation_type)
    if date_from is not None:
        query = query.where(Observation.observed_at >= date_from)
    if date_to is not None:
        query = query.where(Observation.observed_at < date_to)
    if code is not None:
        query = query.where(Observation.code == code)
    return query.order_by(Observation.observed_at, Observation.id)


def list_observations(session: Session, patient_id: UUID, *, limit=100, offset=0, **filters):
    get_patient(session, patient_id)
    return session.scalars(observation_query(patient_id, **filters).limit(limit).offset(offset)).all()


def timeline(session: Session, patient_id: UUID, *, limit=100, offset=0, **filters):
    get_patient(session, patient_id)
    # Synthetic prototype histories are small; paginate the unified event sequence.
    observations = session.scalars(observation_query(patient_id, **filters)).all()
    encounters_query = select(Encounter).where(Encounter.patient_id == patient_id)
    if filters.get("date_from") is not None:
        encounters_query = encounters_query.where(Encounter.occurred_at >= filters["date_from"])
    if filters.get("date_to") is not None:
        encounters_query = encounters_query.where(Encounter.occurred_at < filters["date_to"])
    events = [TimelineEvent(event_type="observation", occurred_at=row.observed_at,
                           observation=ObservationRead.model_validate(row)) for row in observations]
    events.extend(TimelineEvent(event_type="encounter", occurred_at=row.occurred_at,
                  encounter=EncounterRead.model_validate(row)) for row in session.scalars(encounters_query))
    events.sort(key=lambda event: (event.occurred_at, event.event_type,
                str(event.observation.id if event.observation else event.encounter.id)))
    return events[offset:offset + limit]
