"""Persistent handoff tests with synthetic records; no LLM or rule execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.seed import seed, synthetic_id
from app.db.session import get_session
from app.main import create_app
from app.models import AnalysisRun, ClinicalFinding, FindingEvidence, Observation, Patient, PhysicianReviewRequest, TriggerResult, TriggerResultEvidence, TriggerRule
from app.schemas.analysis import AnalysisProvenance
from app.schemas.reviews import ReviewRequestCreate
from app.services.analysis_service import rule_snapshot
from app.services.review_service import create_review_request

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"
PATIENT = synthetic_id("patient/0")
OTHER = synthetic_id("patient/1")


@pytest.fixture
def client(db_session):
    seed(db_session)
    db_session.commit()
    application = create_app()

    def session_override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    application.dependency_overrides[get_session] = session_override
    with TestClient(application) as result:
        yield result


@pytest.fixture
def analysis_factory(db_session):
    def make(*, patient_id=PATIENT, priority="review", triggered=True, status="completed"):
        index = 0 if patient_id == PATIENT else 1
        note = db_session.get(Observation, synthetic_id(f"note/{index}/3"))
        rule = TriggerRule(name=f"SYNTHETIC WORKFLOW {uuid4()}", version="fixture-v1", enabled=False,
            description="Synthetic workflow fixture, not clinical guidance.", recommended_action="Physician review",
            conditions={"lahde": "SYNTHETIC_WORKFLOW_TEST", "lahde_kohta": "fixture-v1", "priority": priority})
        db_session.add(rule)
        db_session.flush()
        metadata = AnalysisProvenance(input_observation_id=note.id, cutoff=note.observed_at,
            rule_snapshots={str(rule.id): rule_snapshot(rule)},
            missing_information=["SYNTHETIC fixture has incomplete symptom history."])
        run = AnalysisRun(patient_id=patient_id, status=status, model_name="synthetic-fixture", details=metadata.model_dump(mode="json"))
        db_session.add(run)
        db_session.flush()
        finding = ClinicalFinding(patient_id=patient_id, analysis_run_id=run.id, finding_type="synthetic_example",
            description="SYNTHETIC original observation for handoff.", status="current")
        result = TriggerResult(patient_id=patient_id, analysis_run_id=run.id, trigger_rule_id=rule.id,
            triggered=triggered, requires_clinician_review=triggered, explanation="SYNTHETIC stored rule outcome.")
        db_session.add_all([finding, result])
        db_session.flush()
        db_session.add_all([
            FindingEvidence(finding_id=finding.id, patient_id=patient_id, observation_id=note.id,
                            source_excerpt=note.text, start_offset=0, end_offset=len(note.text)),
            TriggerResultEvidence(trigger_result_id=result.id, patient_id=patient_id, observation_id=note.id),
        ])
        db_session.commit()
        return run

    return make


def submit(client, run, **payload):
    return client.post(f"{PREFIX}/patients/{run.patient_id}/review-requests", json={"analysis_id": str(run.id), **payload})


def test_successful_submission_and_original_evidence(client, db_session, analysis_factory):
    run = analysis_factory()
    original = client.get(f"{PREFIX}/analyses/{run.id}").json()
    response = submit(client, run, submitted_by="Nurse H. Virtanen")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["patient_id"] == str(PATIENT) and body["analysis_id"] == str(run.id)
    assert body["status"] == "pending" and body["priority"] == "review"
    assert body["submitted_by"] == "Nurse H. Virtanen"
    assert body["patient"]["id"] == str(PATIENT)
    assert body["analysis"] == original
    assert body["analysis"]["provenance"]["missing_information"]  # Warnings remain visible.
    assert response.headers["Location"] == f"{PREFIX}/review-requests/{body['id']}"
    assert client.get(response.headers["Location"]).json() == body
    assert client.get(f"{PREFIX}/review-requests").json() == [body]
    assert db_session.scalar(select(func.count()).select_from(PhysicianReviewRequest)) == 1
    sources = {row["id"]: row for row in body["analysis"]["source_observations"]}
    for finding in body["analysis"]["findings"]:
        for ref in finding["evidence"]:
            source = sources[ref["observation_id"]]
            assert source["patient_id"] == str(PATIENT)
            assert source["text"][ref["start_offset"]:ref["end_offset"]] == ref["source_excerpt"]
            assert client.get(f"{PREFIX}/observations/{source['id']}").json() == source
    # New session/application: persistence does not depend on an identity map/browser state.
    with Session(bind=db_session.connection(), join_transaction_mode="create_savepoint") as reopened:
        application = create_app()
        application.dependency_overrides[get_session] = lambda: reopened
        with TestClient(application) as other_client:
            assert other_client.get(f"{PREFIX}/review-requests").json() == [body]


def test_existing_analysis_endpoint_can_be_handed_off(client):
    analysis = client.post(f"{PREFIX}/patients/{PATIENT}/analyses",
                          json={"note_observation_id": str(synthetic_id("note/0/3"))}).json()
    assert analysis["status"] == "completed"
    response = client.post(f"{PREFIX}/patients/{PATIENT}/review-requests", json={"analysis_id": analysis["id"]})
    assert response.status_code == 201, response.text
    assert response.json()["analysis"] == analysis
    assert response.json()["priority"] == "normal"  # No enabled fixture rules; no invented urgency.


def test_duplicate_submission_returns_original_request(client, db_session, analysis_factory):
    run = analysis_factory()
    first = submit(client, run, submitted_by="SYNTHETIC Nurse One")
    retry = submit(client, run, submitted_by="SYNTHETIC Nurse Two")
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json() == first.json()
    assert retry.headers["Location"] == first.headers["Location"]
    assert db_session.scalar(select(func.count()).select_from(PhysicianReviewRequest)) == 1
    another = submit(client, analysis_factory())
    assert another.status_code == 201  # Separate analyses of one patient remain separate handoffs.
    assert another.json()["id"] != first.json()["id"]


@pytest.mark.parametrize("status", ["pending", "running", "failed"])
def test_incomplete_or_failed_analyses_cannot_be_submitted(client, db_session, analysis_factory, status):
    response = submit(client, analysis_factory(status=status))
    assert response.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PhysicianReviewRequest)) == 0
    assert client.get(f"{PREFIX}/review-requests").json() == []


@pytest.mark.parametrize("corruption", ["error", "input", "cutoff", "foreign_note", "missing_quote", "wrong_offsets", "missing_evidence", "missing_rule_evidence"])
def test_completed_label_does_not_bypass_provenance_and_evidence_checks(client, db_session, analysis_factory, corruption):
    run = analysis_factory()
    details = dict(run.details)
    if corruption == "error":
        details["error_code"] = "synthetic_pipeline_failure"
    elif corruption == "input":
        details["input_observation_id"] = None
    elif corruption == "cutoff":
        details["cutoff"] = None
    elif corruption == "foreign_note":
        details["input_observation_id"] = str(synthetic_id("note/1/3"))
    elif corruption in ("missing_quote", "wrong_offsets"):
        evidence = db_session.scalar(select(FindingEvidence).join(ClinicalFinding).where(ClinicalFinding.analysis_run_id == run.id))
        if corruption == "missing_quote":
            evidence.source_excerpt = "SYNTHETIC fabricated quote absent from original source"
        else:
            evidence.end_offset += 1
    elif corruption == "missing_evidence":
        finding = db_session.scalar(select(ClinicalFinding).where(ClinicalFinding.analysis_run_id == run.id))
        db_session.execute(delete(FindingEvidence).where(FindingEvidence.finding_id == finding.id))
    else:
        result = db_session.scalar(select(TriggerResult).where(TriggerResult.analysis_run_id == run.id))
        db_session.execute(delete(TriggerResultEvidence).where(TriggerResultEvidence.trigger_result_id == result.id))
    run.details = details
    db_session.commit()
    assert submit(client, run).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PhysicianReviewRequest)) == 0


def test_nonexistent_resources_and_cross_patient_submission(client, analysis_factory):
    run = analysis_factory()
    for patient_id, analysis_id in ((uuid4(), run.id), (PATIENT, uuid4()), (OTHER, run.id)):
        result = client.post(f"{PREFIX}/patients/{patient_id}/review-requests", json={"analysis_id": str(analysis_id)})
        assert result.status_code == 404
    assert client.get(f"{PREFIX}/review-requests/{uuid4()}").status_code == 404
    assert client.get(f"{PREFIX}/review-requests", params={"patient_id": str(uuid4())}).status_code == 404
    assert client.get(f"{PREFIX}/review-requests").json() == []


@pytest.mark.parametrize("extra", [{"priority": "urgent"}, {"status": "approved"}, {"patient_id": str(OTHER)},
                                   {"decision": "refer"}, {"submitted_by": "   "}, {"submitted_by": "x" * 121}])
def test_client_cannot_assign_priority_status_decisions_or_invalid_identity(client, analysis_factory, extra):
    assert submit(client, analysis_factory(), **extra).status_code == 422
    assert client.get(f"{PREFIX}/review-requests").json() == []


def test_rule_priority_snapshot_ignores_model_text_and_later_rule_edits(client, db_session, analysis_factory):
    run = analysis_factory(priority="urgent")
    first = submit(client, run).json()
    assert first["priority"] == "urgent"
    rule = db_session.scalar(select(TriggerRule).join(TriggerResult).where(TriggerResult.analysis_run_id == run.id))
    rule.conditions = dict(rule.conditions, priority="review")
    db_session.commit()
    assert client.get(f"{PREFIX}/review-requests/{first['id']}").json() == first
    no_match = analysis_factory(priority="urgent", triggered=False)
    finding = db_session.scalar(select(ClinicalFinding).where(ClinicalFinding.analysis_run_id == no_match.id))
    finding.description = "SYNTHETIC LLM text claiming URGENT, priority=urgent."
    db_session.commit()
    assert submit(client, no_match).json()["priority"] == "normal"


def test_queue_ordering_pagination_and_patient_filter(client, db_session, analysis_factory):
    choices = [("review", True, PATIENT), ("urgent", True, OTHER), ("urgent", True, PATIENT),
               ("urgent", True, PATIENT), ("urgent", False, OTHER)]
    rows = [submit(client, analysis_factory(priority=priority, triggered=triggered, patient_id=patient)).json()
            for priority, triggered, patient in choices]
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    # Old routine/review still follow urgent. Equal times use UUID ascending.
    for row, minutes in zip(rows, [0, 3, 1, 1, -10]):
        db_session.execute(update(PhysicianReviewRequest).where(PhysicianReviewRequest.id == UUID(row["id"]))
                           .values(created_at=base + timedelta(minutes=minutes)))
    db_session.commit()
    result = client.get(f"{PREFIX}/review-requests").json()
    tied = sorted([rows[2]["id"], rows[3]["id"]])
    assert [row["id"] for row in result] == [*tied, rows[1]["id"], rows[0]["id"], rows[4]["id"]]
    assert [row["priority"] for row in result] == ["urgent", "urgent", "urgent", "review", "normal"]
    assert client.get(f"{PREFIX}/review-requests", params={"limit": 2, "offset": 1}).json() == result[1:3]
    filtered = client.get(f"{PREFIX}/review-requests", params={"patient_id": str(PATIENT)}).json()
    assert filtered == [row for row in result if row["patient_id"] == str(PATIENT)]
    for params in ({"limit": 201}, {"offset": -1}, {"status": "approved"}, {"patient_id": "invalid"}):
        assert client.get(f"{PREFIX}/review-requests", params=params).status_code == 422


@pytest.mark.parametrize("corruption", ["failed", "running", "error", "incomplete"])
def test_queue_excludes_a_request_if_its_analysis_becomes_ineligible(client, db_session, analysis_factory, corruption):
    run = analysis_factory()
    review_id = submit(client, run).json()["id"]
    if corruption in ("failed", "running"):
        run.status = corruption
    else:
        run.details = dict(run.details, **({"error_code": "synthetic_failure"} if corruption == "error" else {"cutoff": None}))
    db_session.commit()
    assert client.get(f"{PREFIX}/review-requests").json() == []
    assert client.get(f"{PREFIX}/review-requests/{review_id}").status_code == 409


def test_database_rejects_duplicate_and_cross_patient_review_links(db_session, client, analysis_factory):
    run = analysis_factory()
    submit(client, run)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(PhysicianReviewRequest(patient_id=run.patient_id, analysis_id=run.id, priority="review"))
        db_session.flush()
    assert error.value.orig.sqlstate == "23505"
    other_run = analysis_factory()
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(PhysicianReviewRequest(patient_id=OTHER, analysis_id=other_run.id, priority="review"))
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"


def test_concurrent_submissions_create_one_persistent_request(database_engine):
    # Independent committed synthetic graph enables true separate-connection races.
    patient_id, analysis_id, note_id = uuid4(), uuid4(), uuid4()
    at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with Session(database_engine) as session:
        session.add(Patient(id=patient_id, synthetic_name="SYNTHETIC concurrency fixture", birth_date=date(1960, 1, 1), sex="unknown"))
        session.flush()
        session.add(Observation(id=note_id, patient_id=patient_id, observation_type="clinical_note",
                               text="SYNTHETIC workflow fixture.", observed_at=at, recorded_at=at))
        session.add(AnalysisRun(id=analysis_id, patient_id=patient_id, status="completed",
            details=AnalysisProvenance(input_observation_id=note_id, cutoff=at).model_dump(mode="json")))
        session.commit()

    def submit_in_separate_session(index):
        with Session(database_engine) as session:
            return create_review_request(session, patient_id,
                ReviewRequestCreate(analysis_id=analysis_id, submitted_by=f"SYNTHETIC Nurse {index}"))

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit_in_separate_session, range(4)))
        assert sum(created for _, created in results) == 1
        assert len({response.id for response, _ in results}) == 1
        assert len({response.submitted_by for response, _ in results}) == 1
        with Session(database_engine) as session:
            assert session.scalar(select(func.count()).select_from(PhysicianReviewRequest)
                                  .where(PhysicianReviewRequest.analysis_id == analysis_id)) == 1
    finally:
        with Session(database_engine) as session:
            session.execute(delete(PhysicianReviewRequest).where(PhysicianReviewRequest.analysis_id == analysis_id))
            session.execute(delete(AnalysisRun).where(AnalysisRun.id == analysis_id))
            session.execute(delete(Observation).where(Observation.id == note_id))
            session.execute(delete(Patient).where(Patient.id == patient_id))
            session.commit()
