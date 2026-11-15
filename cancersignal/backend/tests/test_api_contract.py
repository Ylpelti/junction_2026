from fastapi.testclient import TestClient

from app.main import app


def test_docs_and_openapi_expose_public_routes_only():
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths) == {"/health", "/ready", "/api/v1/patients", "/api/v1/patients/{patient_id}",
        "/api/v1/patients/{patient_id}/encounters", "/api/v1/patients/{patient_id}/observations",
        "/api/v1/observations/{observation_id}", "/api/v1/patients/{patient_id}/timeline",
        "/api/v1/patients/{patient_id}/analyses", "/api/v1/analyses/{analysis_id}",
        "/api/v1/patients/{patient_id}/review-requests", "/api/v1/review-requests",
        "/api/v1/review-requests/{request_id}", "/api/v1/analyses/{analysis_id}/dismissal",
        "/api/v1/review-requests/{request_id}/decision"}
    assert "post" in paths["/api/v1/patients/{patient_id}/analyses"]
    assert "post" in paths["/api/v1/patients"]
    assert "AnalysisResponse" in schema["components"]["schemas"]

    for path in ("/api/v1/analyses/{analysis_id}/dismissal", "/api/v1/review-requests/{request_id}/decision"):
        assert set(paths[path]) == {"get", "post"}
