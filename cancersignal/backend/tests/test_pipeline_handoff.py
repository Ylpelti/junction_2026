"""Real PostgreSQL/API orchestration, deterministic extraction and explanation."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_pipeline_settings
from app.db.seed import seed, synthetic_id
from app.db.session import get_session
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider_failure", [False, True])
def test_explanation_is_persisted_and_duplicate_handoff_is_idempotent(db_session, monkeypatch, provider_failure):
    monkeypatch.setenv("CANCERSIGNAL_EXTRACTION", "off")
    monkeypatch.setenv("CANCERSIGNAL_RETRIEVAL", "lexical")
    monkeypatch.setenv("CANCERSIGNAL_EXPLANATION", "llm" if provider_failure else "deterministic")
    monkeypatch.setenv("CANCERSIGNAL_EXPLANATION_ALLOW_LIVE", "false")
    monkeypatch.setenv("EXPLANATION_MODEL", "synthetic-no-network")
    get_pipeline_settings.cache_clear()
    seed(db_session)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    patient = str(synthetic_id("patient/0"))
    try:
        with TestClient(app) as client:
            result = client.post(f"/api/v1/patients/{patient}/analyses", json={
                "note_observation_id": str(synthetic_id("note/0/3"))}).json()
            assert result["status"] == "completed"
            explanation = result["clinical_explanation"]
            assert explanation is not None
            assert explanation["mode"] == "fallback"
            assert explanation["language"] == "fi"
            assert result["explanation"] == explanation["summary_fi"]
            if provider_failure:
                assert any(i["code"] == "live_calls_disabled" for i in explanation["issues"])
            sources = {s["id"] for s in result["source_observations"]}
            for statement in explanation["findings"] + explanation["mathematical_outputs"] + explanation["rule_results"]:
                assert set(statement["observation_ids"]) <= sources
            # Neither GET nor physician handoff is allowed to regenerate explanations.
            from app.explanation import ExplanationEngine
            monkeypatch.setattr(ExplanationEngine, "explain_api", lambda *a, **k: pytest.fail("Repeated explanation"))
            assert client.get(f"/api/v1/analyses/{result['id']}").json() == result
            payload = {"analysis_id": result["id"], "submitted_by": "Synthetic integration nurse"}
            first = client.post(f"/api/v1/patients/{patient}/review-requests", json=payload)
            second = client.post(f"/api/v1/patients/{patient}/review-requests", json=payload)
            assert (first.status_code, second.status_code) == (201, 200)
            assert first.json()["id"] == second.json()["id"]
        # New client simulates a refresh; the case comes from persisted database state.
        with TestClient(app) as client:
            saved = client.get(f"/api/v1/review-requests/{first.json()['id']}").json()
            assert saved["analysis"] == result
            assert any(r["id"] == saved["id"] for r in client.get("/api/v1/review-requests").json())
    finally:
        get_pipeline_settings.cache_clear()
