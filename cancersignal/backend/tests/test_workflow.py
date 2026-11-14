"""Real PostgreSQL workflow tests, using synthetic handoff fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.models import AnalysisRun, Patient, Observation, PhysicianReviewRequest, AlertDismissal, PhysicianDecision
from app.schemas.analysis import AnalysisProvenance
from app.schemas.workflow import DismissalCreate, DecisionCreate
from app.schemas.reviews import ReviewRequestCreate
from app.services.workflow_service import create_dismissal, create_decision
from app.services.review_service import create_review_request
from app.services.errors import ServiceError
from test_reviews import client, analysis_factory, submit, PATIENT, OTHER, PREFIX

pytestmark = pytest.mark.integration


def dismiss(client, run, **overrides):
    return client.post(f'{PREFIX}/analyses/{run.id}/dismissal', json={
        'patient_id': str(run.patient_id), 'reason_code': 'already_aware',
        'actor': 'SYNTHETIC Nurse', **overrides})


def decide(client, review, **overrides):
    return client.post(f"{PREFIX}/review-requests/{review['id']}/decision", json={
        'action': 'fit_ordered', 'actor': 'SYNTHETIC Physician', **overrides})


@pytest.mark.parametrize('reason', ['already_aware', 'another_diagnosis', 'patient_declined', 'other'])
def test_dismissal_persistence_and_original_history(client, db_session, analysis_factory, reason):
    run = analysis_factory()
    original = client.get(f'{PREFIX}/analyses/{run.id}').json()
    history = client.get(f'{PREFIX}/patients/{PATIENT}/analyses').json()
    result = dismiss(client, run, reason_code=reason, comment='SYNTHETIC explanation')
    assert result.status_code == 201, result.text
    body = result.json()
    assert body['reason_code'] == reason and body['actor'] == 'SYNTHETIC Nurse'
    assert body['created_at'] and body['analysis_id'] == str(run.id)
    assert dismiss(client, run).status_code == 409
    assert dismiss(client, run, reason_code='other').status_code == 409
    assert submit(client, run).status_code == 409
    assert client.get(f'{PREFIX}/analyses/{run.id}').json() == original
    assert client.get(f'{PREFIX}/patients/{PATIENT}/analyses').json() == history
    newer = analysis_factory()
    assert client.get(f'{PREFIX}/analyses/{newer.id}/dismissal').status_code == 404
    with Session(bind=db_session.connection(), join_transaction_mode='create_savepoint') as reopened:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: reopened
        with TestClient(app) as refreshed:
            assert refreshed.get(f'{PREFIX}/analyses/{run.id}/dismissal').json() == body


@pytest.mark.parametrize('overrides', [{'reason_code': 'invalid'}, {'actor': '  '}, {'actor': 'x'*121},
    {'comment': ''}, {'comment': 'x'*4001}, {'created_at': '2026-11-14T12:00:00Z'}])
def test_invalid_dismissal(client, analysis_factory, overrides):
    assert dismiss(client, analysis_factory(), **overrides).status_code == 422


def test_cross_patient_and_missing(client, analysis_factory):
    run = analysis_factory()
    assert dismiss(client, run, patient_id=str(OTHER)).status_code == 404
    assert client.get(f'{PREFIX}/analyses/{uuid4()}/dismissal').status_code == 404
    assert decide(client, {'id': str(uuid4())}).status_code == 404
    assert client.get(f'{PREFIX}/review-requests/{uuid4()}/decision').status_code == 404


@pytest.mark.parametrize('status', ['pending', 'running', 'failed'])
def test_invalid_analysis_transition(client, db_session, analysis_factory, status):
    assert dismiss(client, analysis_factory(status=status)).status_code == 409
    run = analysis_factory()
    review = submit(client, run).json()
    run.status = status
    db_session.commit()
    assert decide(client, review).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PhysicianDecision)) == 0


@pytest.mark.parametrize('action', ['fit_ordered', 'referral_made', 'no_action', 'acknowledged'])
def test_decision_queue_history_refresh(client, db_session, analysis_factory, action):
    run = analysis_factory(triggered=action != 'acknowledged')
    review = submit(client, run).json()
    original = review['analysis']
    assert dismiss(client, run).status_code == 409
    result = decide(client, review, action=action, comment='SYNTHETIC decision comment')
    assert result.status_code == 201, result.text
    body = result.json()
    assert body['status'] == 'reviewed' and body['action'] == action and body['created_at']
    assert decide(client, review, action=action).status_code == 409
    assert decide(client, review, action='no_action' if action != 'no_action' else 'fit_ordered').status_code == 409
    assert client.get(f'{PREFIX}/review-requests').json() == []
    reviewed = client.get(f'{PREFIX}/review-requests', params={'status': 'reviewed'}).json()
    assert reviewed[0]['status'] == 'reviewed' and reviewed[0]['analysis'] == original
    assert client.get(f'{PREFIX}/review-requests', params={'status': 'all'}).json() == reviewed
    assert submit(client, run).status_code == 200  # Original handoff retry remains idempotent.
    assert submit(client, run).json() == reviewed[0]
    pending = submit(client, analysis_factory()).json()
    assert client.get(f'{PREFIX}/review-requests').json() == [pending]
    with Session(bind=db_session.connection(), join_transaction_mode='create_savepoint') as reopened:
        app = create_app()
        app.dependency_overrides[get_session] = lambda: reopened
        with TestClient(app) as refreshed:
            assert refreshed.get(f"{PREFIX}/review-requests/{review['id']}/decision").json() == body
            assert refreshed.get(f"{PREFIX}/review-requests/{review['id']}").json() == reviewed[0]


def test_inapplicable_decisions_and_invalid_contract(client, analysis_factory):
    routine = submit(client, analysis_factory(triggered=False)).json()
    alert = submit(client, analysis_factory()).json()
    assert decide(client, routine).status_code == 409
    assert decide(client, alert, action='acknowledged').status_code == 409
    for fields in ({'action': 'prescribe'}, {'actor': ''}, {'status': 'pending'}):
        assert decide(client, alert, **fields).status_code == 422


def test_database_constraints_and_metadata(client, db_session, analysis_factory):
    run = analysis_factory()
    dismiss(client, run)
    for patient, expected in [(PATIENT, '23505'), (OTHER, '23503')]:
        target = run if patient == PATIENT else analysis_factory()
        with pytest.raises(IntegrityError) as error, db_session.begin_nested():
            db_session.add(AlertDismissal(analysis_id=target.id, patient_id=patient, reason_code='other', actor='SYNTHETIC'))
            db_session.flush()
        assert error.value.orig.sqlstate == expected
    review = submit(client, analysis_factory()).json()
    from uuid import UUID
    decide(client, review)
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(PhysicianDecision(review_request_id=UUID(review['id']), action='no_action', actor='SYNTHETIC'))
        db_session.flush()
    assert error.value.orig.sqlstate == '23505'
    context = MigrationContext.configure(db_session.connection(), opts={'include_object':
        lambda obj, name, type_, reflected, compare_to: not(type_ == 'table' and reflected and compare_to is None)})
    assert compare_metadata(context, Base.metadata) == []


@pytest.mark.parametrize('mode', ['dismiss', 'decision', 'handoff_race'])
def test_concurrent_actions(database_engine, mode):
    patient_id, analysis_id, note_id = uuid4(), uuid4(), uuid4()
    at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with Session(database_engine) as session:
        session.add(Patient(id=patient_id, synthetic_name='SYNTHETIC action race', birth_date=date(1960, 1, 1), sex='unknown'))
        session.flush()
        session.add(Observation(id=note_id, patient_id=patient_id, observation_type='clinical_note',
            text='SYNTHETIC workflow fixture.', observed_at=at, recorded_at=at))
        session.add(AnalysisRun(id=analysis_id, patient_id=patient_id, status='completed',
            details=AnalysisProvenance(input_observation_id=note_id, cutoff=at).model_dump(mode='json')))
        session.commit()
        if mode == 'decision':
            review, _ = create_review_request(session, patient_id, ReviewRequestCreate(analysis_id=analysis_id))
            request_id = review.id

    def act(index):
        with Session(database_engine) as session:
            try:
                if mode == 'decision':
                    return create_decision(session, request_id, DecisionCreate(action='acknowledged', actor=f'SYNTHETIC {index}'))
                if mode == 'handoff_race' and index % 2:
                    return create_review_request(session, patient_id, ReviewRequestCreate(analysis_id=analysis_id))
                return create_dismissal(session, analysis_id, DismissalCreate(patient_id=patient_id,
                    reason_code='other', actor=f'SYNTHETIC {index}'))
            except ServiceError as error:
                assert error.status_code == 409
                return None
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(act, range(4)))
        with Session(database_engine) as session:
            dismissals = session.scalar(select(func.count()).select_from(AlertDismissal).where(AlertDismissal.analysis_id == analysis_id))
            reviews = session.scalar(select(func.count()).select_from(PhysicianReviewRequest).where(PhysicianReviewRequest.analysis_id == analysis_id))
            if mode == 'decision':
                assert sum(r is not None for r in results) == 1
                assert session.get(PhysicianReviewRequest, request_id).status == 'reviewed'
                assert session.scalar(select(func.count()).select_from(PhysicianDecision).where(PhysicianDecision.review_request_id == request_id)) == 1
            else:
                assert dismissals + reviews == 1
                if mode == 'dismiss':
                    assert sum(r is not None for r in results) == 1
    finally:
        with Session(database_engine) as session:
            ids = select(PhysicianReviewRequest.id).where(PhysicianReviewRequest.analysis_id == analysis_id)
            session.execute(delete(PhysicianDecision).where(PhysicianDecision.review_request_id.in_(ids)))
            session.execute(delete(AlertDismissal).where(AlertDismissal.analysis_id == analysis_id))
            session.execute(delete(PhysicianReviewRequest).where(PhysicianReviewRequest.analysis_id == analysis_id))
            session.execute(delete(AnalysisRun).where(AnalysisRun.id == analysis_id))
            session.execute(delete(Observation).where(Observation.id == note_id))
            session.execute(delete(Patient).where(Patient.id == patient_id))
            session.commit()
