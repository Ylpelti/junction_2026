from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import get_analysis_pipeline
from app.db.seed import seed, synthetic_id
from app.db.session import get_session
from app.main import app
from app.models import AnalysisRun, ClinicalFinding, Observation, TriggerRule
from app.rag.context import ExtractionResult
from app.schemas.analysis import EvidenceReference, StructuredFinding

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"
PATIENT = str(synthetic_id("patient/0"))
OTHER = str(synthetic_id("patient/1"))
NOTE = str(synthetic_id("note/0/3"))


@pytest.fixture
def client(db_session):
    seed(db_session)
    # Keep seeded parents in the outer test transaction across request rollbacks.
    db_session.commit()
    previous = dict(app.dependency_overrides)

    def session_override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def note_payload(**overrides):
    return dict(patient_id=PATIENT, observation_type="clinical_note", text="SYNTHETIC new source note.",
        observed_at="2026-05-01T12:00:00Z", recorded_at="2026-05-01T12:05:00Z") | overrides


def test_patient_create_list_get_and_duplicates(client):
    payload = {"id": str(uuid4()), "synthetic_name": "SYNTHETIC API Patient", "birth_date": "1960-01-01", "sex": "unknown"}
    created = client.post(f"{PREFIX}/patients", json=payload)
    assert created.status_code == 201
    assert created.json()["id"] == payload["id"]
    assert client.get(f"{PREFIX}/patients/{payload['id']}").json() == created.json()
    assert any(row["id"] == payload["id"] for row in client.get(f"{PREFIX}/patients").json())
    assert client.post(f"{PREFIX}/patients", json=payload).status_code == 409


def test_patient_requires_synthetic_label(client):
    assert client.post(f"{PREFIX}/patients", json={"synthetic_name": "Unmarked", "birth_date": "1960-01-01", "sex": "unknown"}).status_code == 422


def test_observation_roundtrip_preserves_original_record(client):
    identifier = str(uuid4())
    payload = note_payload(id=identifier, text="SYNTHETIC original\nDenies bleeding. Follow-up uncertain.")
    response = client.post(f"{PREFIX}/patients/{PATIENT}/observations", json=payload)
    assert response.status_code == 201
    assert response.json()["text"] == payload["text"]
    assert response.json()["id"] == identifier
    assert client.get(f"{PREFIX}/observations/{identifier}").json() == response.json()


def test_filtering_and_chronological_timeline(client):
    filters = {"observation_type": "laboratory", "code": "SYNTHETIC-HB", "date_from": "2022-01-01T00:00:00Z", "date_to": "2025-01-01T00:00:00Z"}
    records = client.get(f"{PREFIX}/patients/{PATIENT}/observations", params=filters).json()
    assert len(records) == 2
    assert all(row["patient_id"] == PATIENT and row["code"] == "SYNTHETIC-HB" for row in records)
    events = client.get(f"{PREFIX}/patients/{PATIENT}/timeline", params=filters).json()
    assert [event["occurred_at"] for event in events] == sorted(event["occurred_at"] for event in events)
    assert len([event for event in events if event["event_type"] == "observation"]) == 2
    assert len([event for event in events if event["event_type"] == "encounter"]) == 2
    encounters = client.get(f"{PREFIX}/patients/{PATIENT}/encounters").json()
    assert len(encounters) == 4


@pytest.mark.parametrize("payload", [note_payload(patient_id=OTHER), note_payload(encounter_id=str(synthetic_id("encounter/1/0"))),
                                   note_payload(encounter_id=str(uuid4()))])
def test_observation_ownership_validation(client, payload):
    assert client.post(f"{PREFIX}/patients/{PATIENT}/observations", json=payload).status_code == 422


@pytest.mark.parametrize("path", [f"/patients/{uuid4()}", f"/observations/{uuid4()}", f"/analyses/{uuid4()}",
                                  f"/patients/{uuid4()}/observations", f"/patients/{uuid4()}/analyses"])
def test_missing_resources(client, path):
    assert client.get(PREFIX + path).status_code == 404


def test_invalid_query_and_resources(client):
    assert client.get(f"{PREFIX}/patients/not-a-uuid").status_code == 422
    assert client.get(f"{PREFIX}/patients/{PATIENT}/observations", params={"date_from": "2026-01-01T00:00:00"}).status_code == 422
    assert client.get(f"{PREFIX}/patients/{PATIENT}/observations", params={"date_from": "2026-01-01T00:00:00Z", "date_to": "2020-01-01T00:00:00Z"}).status_code == 422
    assert client.get(f"{PREFIX}/patients", params={"limit": 201}).status_code == 422


def test_analysis_creation_retrieval_and_evidence(client, db_session):
    # Toy presence rule only, not a clinical threshold or assessment.
    rule = TriggerRule(name="DEMONSTRATION: structured laboratory fixture present", description="SYNTHETIC test only",
        version="demo-v1", enabled=True, recommended_action="Physician review of demonstration output",
        conditions={"demonstration": True, "lahde": "SYNTHETIC_TEST_NOT_CLINICAL_GUIDANCE", "lahde_kohta": "test fixture",
            "expression": {"kind": "group", "operator": "ALL", "conditions": [
                {"kind": "finding", "finding_type": "SYNTHETIC-HB", "statuses": ["historical"]}]}})
    db_session.add(rule)
    db_session.flush()
    response = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": NOTE})
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "completed", result
    assert result["findings"] and result["trigger_results"][0]["triggered"]
    assert result["trigger_results"][0]["requires_clinician_review"]
    assert result["trigger_results"][0]["demonstration_only"]
    assert result["provenance"]["missing_information"]
    sources = {row["id"]: row for row in result["source_observations"]}
    assert all(row["patient_id"] == PATIENT for row in sources.values())
    for finding in result["findings"]:
        for reference in finding["evidence"]:
            source = sources[reference["observation_id"]]
            assert reference["source_excerpt"] in source["text"]
            assert client.get(f"{PREFIX}/observations/{source['id']}").json() == source
    assert client.get(f"{PREFIX}/analyses/{result['id']}").json() == result
    assert client.get(f"{PREFIX}/patients/{PATIENT}/analyses").json() == [result]
    assert client.get(f"{PREFIX}/patients/{OTHER}/analyses").json() == []
    # Stored rule provenance survives later edits to a definition.
    rule.name = "Changed later"
    rule.version = "demo-v2"
    db_session.commit()
    assert client.get(f"{PREFIX}/analyses/{result['id']}").json() == result


def test_new_note_analysis_and_no_rules_are_explicit(client):
    response = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note": note_payload()})
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "completed"
    assert not result["trigger_results"]
    assert "No enabled demonstration rules are configured." in result["provenance"]["missing_information"]
    assert result["provenance"]["input_observation_id"] not in result["provenance"]["context_observation_ids"]
    assert client.get(f"{PREFIX}/observations/{result['provenance']['input_observation_id']}").json()["text"] == note_payload()["text"]


@pytest.mark.parametrize("payload, expected", [({}, 422), ({"note_observation_id": NOTE, "note": note_payload()}, 422),
    ({"note_observation_id": str(uuid4())}, 404), ({"note_observation_id": str(synthetic_id("note/1/0"))}, 404),
    ({"note_observation_id": str(synthetic_id("lab/0/0"))}, 422)])
def test_invalid_analysis_inputs(client, payload, expected):
    assert client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json=payload).status_code == expected


@pytest.mark.parametrize("source_id", [str(synthetic_id("note/1/0")), str(uuid4()), str(synthetic_id("note/0/3"))])
def test_extractor_cannot_cite_foreign_missing_or_same_time_history(client, source_id):
    class BadExtractor:
        name = "invalid-evidence-test"

        def extract(self, context, note):
            return ExtractionResult(findings=[StructuredFinding(finding_type="demo", status="current", description="SYNTHETIC",
                evidence=[EvidenceReference(observation_id=source_id, source_excerpt="SYNTHETIC")])])

    # Analyze an older note: the 2026 note cannot be historical context.
    pipeline = replace(get_analysis_pipeline(), extractor=BadExtractor())
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    result = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": str(synthetic_id("note/0/1"))}).json()
    assert result["status"] == "failed", result
    assert result["provenance"]["error_code"] == "invalid_finding_evidence"
    assert not result["findings"] and not result["trigger_results"]


def test_pipeline_exception_is_explicit_and_does_not_fabricate_results(client, db_session):
    class FailingExtractor:
        name = "unavailable-test"

        def extract(self, context, note):
            raise RuntimeError("Do not expose provider secrets or clinical source text")

    pipeline = replace(get_analysis_pipeline(), extractor=FailingExtractor())
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    response = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": NOTE})
    result = response.json()
    assert result["status"] == "failed"
    assert result["provenance"]["error_code"] == "pipeline_execution_failed"
    assert "provider secrets" not in response.text
    assert db_session.scalar(select(ClinicalFinding).where(ClinicalFinding.analysis_run_id == result["id"])) is None


@pytest.mark.parametrize("corruption", ["quote", "offsets", "numeric"])
def test_adapters_cannot_fabricate_quotes_offsets_or_numeric_values(client, corruption):
    class InvalidSourceExtractor:
        name = "invalid-source-test"

        def extract(self, context, note):
            ref = EvidenceReference(observation_id=note.id, source_excerpt=note.text)
            extra = {}
            if corruption == "quote":
                ref.source_excerpt = "This text never appeared in the original note."
            elif corruption == "offsets":
                ref.start_offset, ref.end_offset = 0, len(note.text) + 1
            else:
                extra = {"numeric_value": "999", "unit": "fabricated_units"}
            return ExtractionResult(findings=[StructuredFinding(finding_type="demo", status="current",
                description="SYNTHETIC", evidence=[ref], **extra)])

    pipeline = replace(get_analysis_pipeline(), extractor=InvalidSourceExtractor())
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    result = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": NOTE}).json()
    assert result["status"] == "failed"
    assert result["findings"] == []
    assert result["provenance"]["error_code"] == {
        "quote": "invalid_source_quote", "offsets": "invalid_source_offsets", "numeric": "invalid_numeric_evidence"
    }[corruption]


def test_invalid_evaluator_rule_references_are_rejected(client):
    def invalid_evaluator(patient_id, findings, rules):
        return [{"trigger_rule_id": str(uuid4()), "triggered": False, "explanation": "SYNTHETIC"}]

    pipeline = replace(get_analysis_pipeline(), evaluate=invalid_evaluator)
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    result = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": NOTE}).json()
    assert result["status"] == "failed"
    assert result["provenance"]["error_code"] == "invalid_trigger_rule_references"
    assert not result["trigger_results"] and not result["findings"]


def test_llm_note_extraction_triggers_a_sourced_rule(client, db_session):
    """End-to-end with a hand-authored fixture response (no network): note text -> finding -> SUO-06."""
    import json
    from app.db.seed_rules import seed_rules
    from app.extraction.providers import FixtureProvider
    from app.extraction.service import ClinicalExtractor
    from app.rag.extraction import StructuredSourceExtractor
    from app.services.llm_extraction import LlmNoteExtractor

    seed_rules(db_session)
    db_session.flush()
    note_id = str(uuid4())
    text = "SYNTHETIC — Patient reports rectal bleeding."
    fixture = json.dumps({"missing_information": [], "findings": [{
        "finding_type": "rectal_bleeding", "description": "SYNTHETIC rectal bleeding reported.",
        "polarity": "present", "temporal_status": "current", "uncertainty": None, "missing_information": [],
        "evidence": [{"observation_id": note_id, "source_excerpt": "Patient reports rectal bleeding", "start_offset": None, "end_offset": None}],
    }]})
    extractor = LlmNoteExtractor(StructuredSourceExtractor(), clinical=ClinicalExtractor(FixtureProvider(fixture)))
    pipeline = replace(get_analysis_pipeline(), extractor=extractor)
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    result = client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note": note_payload(id=note_id, text=text)}).json()
    assert result["status"] == "completed", result
    assert result["provenance"]["patient_facts"]["age_years"] >= 50
    triggered = {row["rule_name"].split(":")[0]: row for row in result["trigger_results"] if row["triggered"]}
    assert "SUO-06" in triggered
    assert note_id in triggered["SUO-06"]["evidence_observation_ids"]
    assert triggered["SUO-06"]["priority"] == "review"
    assert any(row["id"] == note_id for row in result["source_observations"])
