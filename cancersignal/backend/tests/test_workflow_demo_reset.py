"""Reset deletes only registered demo patients' workflow actions."""
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.demo import demo_id, reset_demo, seed_demo
from app.db.seed import seed, synthetic_id
from app.models import AlertDismissal, AnalysisRun, PhysicianDecision, PhysicianReviewRequest

pytestmark = pytest.mark.integration


def test_reset_removes_demo_workflow_actions_and_preserves_other_patients(db_session):
    seed(db_session)
    seed_demo(db_session)
    artifacts = []
    for patient_id in (demo_id('patient', 'laine'), synthetic_id('patient/0')):
        dismissed_run = AnalysisRun(id=uuid4(), patient_id=patient_id, status='completed')
        reviewed_run = AnalysisRun(id=uuid4(), patient_id=patient_id, status='completed')
        db_session.add_all([dismissed_run, reviewed_run])
        db_session.flush()
        dismissal = AlertDismissal(id=uuid4(), analysis_id=dismissed_run.id, patient_id=patient_id,
            reason_code='other', actor='SYNTHETIC Nurse')
        review = PhysicianReviewRequest(id=uuid4(), analysis_id=reviewed_run.id, patient_id=patient_id,
            priority='normal', status='reviewed')
        db_session.add_all([dismissal, review])
        db_session.flush()
        decision = PhysicianDecision(id=uuid4(), review_request_id=review.id, action='acknowledged',
            actor='SYNTHETIC Physician')
        db_session.add(decision)
        db_session.flush()
        artifacts.append((dismissal.id, review.id, decision.id, dismissed_run.id, reviewed_run.id))
    database = db_session.scalar(text('SELECT current_database()'))
    for _ in range(2):
        reset_demo(db_session, confirm_database=database, environment='demo')
        db_session.flush()
    models = (AlertDismissal, PhysicianReviewRequest, PhysicianDecision, AnalysisRun, AnalysisRun)
    for model, identifier in zip(models, artifacts[0]):
        assert db_session.get(model, identifier) is None
    for model, identifier in zip(models, artifacts[1]):
        assert db_session.get(model, identifier) is not None
    assert db_session.scalar(select(PhysicianDecision.actor).where(PhysicianDecision.id == artifacts[1][2])) == 'SYNTHETIC Physician'
