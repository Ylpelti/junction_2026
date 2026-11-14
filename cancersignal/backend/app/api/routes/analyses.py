from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_analysis_pipeline
from app.db.session import get_session
from app.reasoning.interfaces import AnalysisPipeline
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services import analysis_service

router = APIRouter(tags=["analyses"])


@router.post("/patients/{patient_id}/analyses", response_model=AnalysisResponse, status_code=201)
def create_analysis(patient_id: UUID, payload: AnalysisRequest,
                    session: Session = Depends(get_session),
                    pipeline: AnalysisPipeline = Depends(get_analysis_pipeline)):
    return analysis_service.create_analysis(session, patient_id, payload, pipeline)


@router.get("/patients/{patient_id}/analyses", response_model=list[AnalysisResponse])
def list_analyses(patient_id: UUID, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                  session: Session = Depends(get_session)):
    return analysis_service.list_analyses(session, patient_id, limit, offset)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def analysis(analysis_id: UUID, session: Session = Depends(get_session)):
    return analysis_service.get_analysis(session, analysis_id)
