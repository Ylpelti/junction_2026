from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.records import EncounterRead
from app.services.patient_service import list_encounters

router = APIRouter(tags=["encounters"])


@router.get("/patients/{patient_id}/encounters", response_model=list[EncounterRead])
def encounters(patient_id: UUID, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
               session: Session = Depends(get_session)):
    return list_encounters(session, patient_id, limit, offset)
