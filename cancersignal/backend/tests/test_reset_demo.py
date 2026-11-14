"""Demo reset: deletes demo-created rows, keeps and restores seed data, refuses non-local hosts."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_analysis_pipeline
from app.db import reset_demo
from app.db.reset_demo import NotLocalDatabase, count_deletions, require_local_host, reset, seed_ids
from app.db.seed import seed, synthetic_id
from app.models import AnalysisRun, Encounter, Observation, Patient, TriggerRule
from app.models.enums import ObservationStatus, ObservationType
from app.models.review import PhysicianReviewRequest
from app.schemas.analysis import AnalysisRequest
from app.schemas.records import ObservationCreate
from app.schemas.reviews import ReviewRequestCreate
from app.services.analysis_service import create_analysis
from app.services.review_service import create_review_request

PATIENT = synthetic_id("patient/0")
NOTE_TIME = datetime(2026, 11, 14, 9, tzinfo=timezone.utc)


# ---- No database needed ----------------------------------------------------------

@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "[::1]", "LOCALHOST"])
def test_local_hosts_are_allowed(host):
    require_local_host(host)


@pytest.mark.parametrize("host", ["db.example.com", "10.0.0.5", "192.168.1.20", "postgres", ""])
def test_non_local_host_stops_before_any_connection(monkeypatch, host):
    monkeypatch.setattr(reset_demo, "get_settings", lambda: SimpleNamespace(postgres_host=host, postgres_db="x"))

    def must_not_connect():
        raise AssertionError("A session was opened for a non-local host.")

    with pytest.raises(NotLocalDatabase):
        reset_demo.main(["--yes"], session_factory=must_not_connect)


def test_seed_ids_come_from_the_seed_functions():
    ids = seed_ids()
    assert PATIENT in ids["patients"]
    assert synthetic_id("note/0/3") in ids["observations"]
    assert synthetic_id("encounter/0/0") in ids["encounters"]
    assert len(ids["trigger_rules"]) >= 10


# ---- Disposable PostgreSQL test database (RUN_DATABASE_TESTS=1) -------------------

def seeded(db_session):
    from app.db.seed_rules import seed_rules
    seed(db_session)
    seed_rules(db_session)
    db_session.commit()


def demo_activity(db_session):
    """What a demo leaves behind: a saved note with analysis, a review request, an extra encounter and lab."""
    note_id = uuid4()
    note = ObservationCreate(id=note_id, patient_id=PATIENT, observation_type="clinical_note",
                             text="SYNTHETIC demo note saved by the nurse.", observed_at=NOTE_TIME, recorded_at=NOTE_TIME)
    analysis = create_analysis(db_session, PATIENT, AnalysisRequest(note=note), get_analysis_pipeline())
    assert analysis.status == "completed", analysis.provenance.error_code
    review, created = create_review_request(db_session, PATIENT,
                                            ReviewRequestCreate(analysis_id=analysis.id, submitted_by="Nurse H. Virtanen"))
    assert created
    encounter = Encounter(id=uuid4(), patient_id=PATIENT, occurred_at=NOTE_TIME, encounter_type="demo_visit")
    db_session.add(encounter)
    db_session.flush()
    lab = Observation(id=uuid4(), patient_id=PATIENT, encounter_id=encounter.id,
                      observation_type=ObservationType.LABORATORY, code="B-HB", text="SYNTHETIC demo lab.",
                      numeric_value=99, unit="g/l", status=ObservationStatus.COMPLETED,
                      observed_at=NOTE_TIME, recorded_at=NOTE_TIME)
    db_session.add(lab)
    db_session.commit()
    return analysis.id, note_id, review.id, encounter.id, lab.id


def count(db_session, model, *where):
    query = select(func.count()).select_from(model)
    return db_session.scalar(query.where(*where) if where else query)


@pytest.mark.integration
def test_reset_removes_demo_rows_and_keeps_seed_data(db_session):
    seeded(db_session)
    ids = seed_ids()
    analysis_id, note_id, review_id, encounter_id, lab_id = demo_activity(db_session)

    counts = reset(db_session)
    db_session.commit()

    assert counts["analysis_runs"] >= 1 and counts["physician_review_requests"] == 1
    assert counts["observations"] >= 2 and counts["encounters"] == 1
    assert count(db_session, AnalysisRun, AnalysisRun.id == analysis_id) == 0
    assert count(db_session, PhysicianReviewRequest, PhysicianReviewRequest.id == review_id) == 0
    assert count(db_session, Observation, Observation.id.in_([note_id, lab_id])) == 0
    assert count(db_session, Encounter, Encounter.id == encounter_id) == 0
    # Seed data is intact.
    assert set(db_session.scalars(select(Observation.id))) == ids["observations"]
    assert set(db_session.scalars(select(Encounter.id))) == ids["encounters"]
    assert ids["patients"] <= set(db_session.scalars(select(Patient.id)))
    assert ids["trigger_rules"] <= set(db_session.scalars(select(TriggerRule.id)))


@pytest.mark.integration
def test_reset_restores_missing_seed_rows(db_session):
    seeded(db_session)
    seed_lab = synthetic_id("lab/0/0")  # no embedding or evidence points at it
    db_session.query(Observation).filter(Observation.id == seed_lab).delete(synchronize_session=False)
    db_session.commit()
    reset(db_session)
    db_session.commit()
    assert count(db_session, Observation, Observation.id == seed_lab) == 1


@pytest.mark.integration
def test_reset_twice_in_a_row(db_session):
    seeded(db_session)
    demo_activity(db_session)
    reset(db_session)
    db_session.commit()
    second = reset(db_session)
    db_session.commit()
    assert all(number == 0 for number in second.values()), second


@pytest.mark.integration
def test_without_yes_nothing_is_deleted(db_session, monkeypatch, capsys):
    seeded(db_session)
    analysis_id, note_id, review_id, _, _ = demo_activity(db_session)
    expected = count_deletions(db_session)
    assert expected["analysis_runs"] >= 1

    def deletion_called(*args, **kwargs):
        raise AssertionError("reset() must not run without --yes")

    monkeypatch.setattr(reset_demo, "reset", deletion_called)
    factory = lambda: Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")  # noqa: E731
    assert reset_demo.main([], session_factory=factory) == 1
    assert "nothing deleted" in capsys.readouterr().out
    assert count(db_session, AnalysisRun, AnalysisRun.id == analysis_id) == 1
    assert count(db_session, PhysicianReviewRequest, PhysicianReviewRequest.id == review_id) == 1
    assert count(db_session, Observation, Observation.id == note_id) == 1


@pytest.mark.integration
def test_main_with_yes_resets(db_session, capsys):
    seeded(db_session)
    analysis_id, *_ = demo_activity(db_session)
    factory = lambda: Session(bind=db_session.connection(), join_transaction_mode="create_savepoint")  # noqa: E731
    assert reset_demo.main(["--yes"], session_factory=factory) == 0
    assert "Reload the browser" in capsys.readouterr().out
    assert count(db_session, AnalysisRun, AnalysisRun.id == analysis_id) == 0
