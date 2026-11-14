"""Optional real API/database handoff; standalone explanation tests stay offline."""
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_analysis_pipeline
from app.db.seed import seed, synthetic_id
from app.db.session import get_session
from app.explanation import ExplanationEngine
from app.main import create_app
from app.models import Observation
from app.rag.extraction import StructuredSourceExtractor
from app.rag.retrieval import retrieve_context
from app.reasoning.interfaces import AnalysisPipeline
from app.reasoning.trigger_engine import evaluate_triggers
from app.schemas.analysis import AnalysisResponse

pytestmark = pytest.mark.integration


def test_saved_api_analysis_can_be_explained_without_changing_routes_or_data(db_session):
    seed(db_session)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_analysis_pipeline] = lambda: AnalysisPipeline(
        retrieve=retrieve_context, extractor=StructuredSourceExtractor(), evaluate=evaluate_triggers)
    patient_id = synthetic_id("patient/0")
    with TestClient(app) as client:
        response = client.post(f"/api/v1/patients/{patient_id}/analyses",
                               json={"note_observation_id": str(synthetic_id("note/0/3"))})
        assert response.status_code == 201
        original = response.json()
        assert original["status"] == "completed"
        output = ExplanationEngine().explain_api(AnalysisResponse.model_validate(original),
            input_note=db_session.get(Observation, original["provenance"]["input_observation_id"]))
        assert output.input_format == "api_v1" and output.mode == "fallback"
        assert output.patient_id == patient_id and output.mathematical_outputs
        assert client.get(f"/api/v1/analyses/{original['id']}").json() == original
