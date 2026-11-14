import pytest
from sqlalchemy import select, func

from app.models import Observation
from app.rag.benchmark import run_benchmark

pytestmark = pytest.mark.integration


def test_benchmark_reports_explicit_missing_modes_and_keeps_labels_out_of_sources(db_session):
    before = db_session.scalar(select(func.count()).select_from(Observation))
    with db_session.begin_nested() as transaction:
        report = run_benchmark(db_session)
        assert report['synthetic_only'] and not report['clinically_validated']
        assert len(report['results']) == 20
        assert all(row['status']=='not_run' for row in report['results'] if row['mode'] in ('dense','hybrid'))
        assert all(row['patient_isolation_violations']==0 for row in report['results'] if row['status']=='ok')
        assert all('required' not in (text or '') for text in db_session.scalars(select(Observation.text)))
        transaction.rollback()
    assert db_session.scalar(select(func.count()).select_from(Observation)) == before
