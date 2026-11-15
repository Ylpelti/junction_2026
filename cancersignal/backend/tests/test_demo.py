"""Synthetic source fixtures and PostgreSQL lifecycle, without model predictions."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.contracts.common import PatientScope
from app.db.demo import DATA, Dataset, demo_id, load_dataset, reset_demo, rows_for, seed_demo
from app.db.seed import seed, synthetic_id
from app.db.seed_rules import seed_rules
from app.db.session import get_session
from app.main import app
from app.models import (AnalysisRun, ClinicalFinding, Encounter, FindingEvidence,
    Observation, ObservationEmbedding, Patient, PhysicianReviewRequest,
    TriggerResult, TriggerResultEvidence, TriggerRule)
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository
from app.rag.storage import EmbeddingChunk
from app.reasoning.derived_findings import HB_CODES, derive_lab_findings
from app.risk_models.adapter import _haemoglobin_factor
from app.schemas.records import ObservationRead
from tests.rag.fakes import FakeEmbedder


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def reset(session, **kwargs):
    return reset_demo(session, environment='demo',
                      confirm_database=session.scalar(text('SELECT current_database()')), **kwargs)


def test_fixture_mapping_values_chronology_and_labels():
    data = load_dataset()
    assert (len(data.patients), len(data.encounters), len(data.observations)) == (4, 21, 41)
    labs = [o for o in data.observations if o.observation_type == 'laboratory']
    assert len(labs) == 15
    assert {o.unit for o in labs} == {'g/L'}
    assert [int(o.numeric_value) for o in labs if o.key.startswith('laine/')] == [142, 134, 124, 113]
    for patient in data.patients:
        times = [o.observed_at for o in data.observations if o.patient_id == patient.id]
        assert times == sorted(times)
    mapped = list(rows_for(data))[-1][1]
    assert {r['code'].upper() for r in mapped if r['observation_type'] == 'laboratory'} <= HB_CODES
    laine = [ObservationRead.model_validate(r) for r in mapped if r['patient_id'] == demo_id('patient', 'laine')]
    assert _haemoglobin_factor(laine, 'female')[0] is True
    findings, missing = derive_lab_findings(laine, sex='female')
    assert any('ferritin' in m.lower() for m in missing)
    assert not any(f.finding_type == 'iron_deficiency_anaemia' for f in findings)
    labels = json.loads((Path(__file__).parent / 'fixtures/demo/labels.en-v2.json').read_text())
    keys = {o.key for o in data.observations}
    for case in labels['cases']:
        assert set(case['sources']) <= keys
        assert case['expectation'] not in DATA.read_text()


@pytest.mark.parametrize('corruption', ['duplicate','id','owner','encounter','time','unit','code','system','nan','label','extra'])
def test_reject_invalid_fixture(corruption):
    raw = json.loads(DATA.read_text())
    lab = next(o for o in raw['observations'] if o['observation_type'] == 'laboratory')
    if corruption == 'duplicate': raw['observations'].append(raw['observations'][0])
    elif corruption == 'id': lab['id'] = str(uuid4())
    elif corruption == 'owner': lab['patient_id'] = raw['patients'][1]['id']
    elif corruption == 'encounter': lab['encounter_id'] = raw['encounters'][-1]['id']
    elif corruption == 'time': lab['recorded_at'] = '2010-01-01T00:00:00Z'
    elif corruption == 'unit': lab['unit'] = 'g/dL'
    elif corruption == 'code': lab['code'] = 'invented'
    elif corruption == 'system': lab['code_system'] = 'invented'
    elif corruption == 'nan': lab['numeric_value'] = 'NaN'
    elif corruption == 'label': lab['text'] = 'Unmarked'
    else: lab['prediction'] = 'cancer'
    with pytest.raises(ValidationError): Dataset.model_validate(raw)


def test_reset_requires_explicit_demo_environment(monkeypatch):
    monkeypatch.delenv('CANCERSIGNAL_DEMO_ENV', raising=False)
    with pytest.raises(ValueError, match='DEMO_ENV'):
        reset_demo(None, confirm_database='anything')


@pytest.mark.integration
def test_initial_repeat_update_and_api(db_session):
    assert seed_demo(db_session) == {'inserted': 66, 'updated': 0, 'unchanged': 0}
    assert seed_demo(db_session) == {'inserted': 0, 'updated': 0, 'unchanged': 66}
    row = db_session.get(Observation, demo_id('observation','laine/2020-09-14/hb'))
    row.numeric_value = 999
    db_session.flush()
    with pytest.raises(ValueError, match='new dataset version'):
        seed_demo(db_session)
    assert row.numeric_value == 999
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            assert len(client.get('/api/v1/patients').json()) == 4
            for p in load_dataset().patients:
                response = client.get(f'/api/v1/patients/{p.id}')
                assert response.status_code == 200
                assert response.json()['synthetic_name'] == p.synthetic_name
                records = client.get(f'/api/v1/patients/{p.id}/observations').json()
                assert records and all(o['patient_id'] == str(p.id) for o in records)
                assert len(records) == len([o for o in load_dataset().observations if o.patient_id == p.id])
                times = [o['observed_at'] for o in records]
                assert times == sorted(times)
                assert client.get(f'/api/v1/patients/{p.id}/encounters').status_code == 200
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.integration
def test_rag_repeat_changed_source_and_retrieval(db_session):
    seed_demo(db_session)
    encoder = FakeEmbedder()
    for p in load_dataset().patients:
        first = index_patient(db_session, p.id, encoder)
        n = count(db_session, EmbeddingChunk)
        assert index_patient(db_session, p.id, encoder)['indexed_observations'] == 0
        assert count(db_session, EmbeddingChunk) == n
        assert first['indexed_observations'] > 0
        scope = PatientScope(patient_id=p.id, as_of='2026-11-13T00:00:00Z')
        for mode in ('complete','lexical','hybrid'):
            output = RetrievalEngine(PatientRepository(db_session), embedder=encoder,
                options=RetrievalOptions(mode=mode)).search(scope=scope, query='abdominal haemoglobin investigation')
            assert output.context.retrieved_observations
            assert all(hit.source.patient_id == p.id for hit in output.context.retrieved_observations)
        structured = PatientRepository(db_session).structured(scope=scope)
        assert all(o.code == 'B-Hb' and o.unit == 'g/L' for o in structured.observations)
    source_id = demo_id('observation','laine/2020-09-14/hb')
    db_session.get(Observation, source_id).numeric_value = 999
    db_session.flush()
    # Existing evidence and its cache must not be silently rewritten by seed.
    index_patient(db_session, demo_id('patient','laine'), encoder)
    with pytest.raises(ValueError, match='new dataset version'):
        seed_demo(db_session)
    assert db_session.get(Observation, source_id).numeric_value == 999
    assert index_patient(db_session, demo_id('patient','laine'), encoder)['indexed_observations'] == 0


@pytest.mark.integration
def test_reset_removes_derived_records_preserves_baseline_and_is_repeatable(db_session):
    seed(db_session)
    seed_demo(db_session)
    seed_rules(db_session)
    rule_id = db_session.scalar(select(TriggerRule.id))
    artifact_ids = []
    for patient_id in (demo_id('patient','laine'), synthetic_id('patient/0')):
        source = db_session.scalar(select(Observation).where(Observation.patient_id == patient_id))
        note = Observation(id=uuid4(), patient_id=patient_id, observation_type='clinical_note',
                           text='SYNTHETIC added during demonstration', observed_at=source.observed_at,
                           recorded_at=source.recorded_at)
        run = AnalysisRun(id=uuid4(), patient_id=patient_id, status='completed')
        db_session.add_all([note, run]); db_session.flush()
        finding = ClinicalFinding(id=uuid4(), patient_id=patient_id, analysis_run_id=run.id,
                                  finding_type='test', description='SYNTHETIC test finding', status='current')
        trigger = TriggerResult(id=uuid4(), patient_id=patient_id, analysis_run_id=run.id,
                                trigger_rule_id=rule_id, triggered=False, requires_clinician_review=False)
        db_session.add_all([finding, trigger]); db_session.flush()
        review = PhysicianReviewRequest(id=uuid4(), patient_id=patient_id, analysis_id=run.id, priority='normal')
        db_session.add_all([review,
            FindingEvidence(finding_id=finding.id, observation_id=note.id, patient_id=patient_id),
            TriggerResultEvidence(trigger_result_id=trigger.id, observation_id=note.id, patient_id=patient_id),
            ObservationEmbedding(observation_id=note.id, embedding_model='test-pending')])
        db_session.flush()
        index_patient(db_session, patient_id, FakeEmbedder())
        artifact_ids.append((note.id, run.id, review.id))
    before_other = db_session.scalars(select(EmbeddingChunk.id).join(Observation).where(Observation.patient_id == synthetic_id('patient/0'))).all()
    reset(db_session)
    reset(db_session)
    for model, identifier in zip((Observation,AnalysisRun,PhysicianReviewRequest),artifact_ids[0]):
        assert db_session.get(model,identifier) is None
    for model, identifier in zip((Observation,AnalysisRun,PhysicianReviewRequest),artifact_ids[1]):
        assert db_session.get(model,identifier) is not None
    assert count(db_session, Patient) == 12
    assert count(db_session, Observation) == 99 + 41  # baseline 98 + unrelated added note
    assert db_session.scalars(select(EmbeddingChunk.id).join(Observation).where(Observation.patient_id == synthetic_id('patient/0'))).all() == before_other
    assert seed_demo(db_session)['unchanged'] == 66


@pytest.mark.integration
def test_identity_guards_and_database_confirmation(db_session):
    seed_demo(db_session)
    with pytest.raises(ValueError, match='confirm-database'):
        reset_demo(db_session, environment='demo', confirm_database='wrong_database')
    p = db_session.get(Patient,demo_id('patient','laine'))
    p.synthetic_name = 'SYNTHETIC unrelated collision'
    db_session.flush()
    with pytest.raises(ValueError, match='identity marker'):
        seed_demo(db_session)
    with pytest.raises(ValueError, match='identity marker'):
        reset(db_session)
    assert count(db_session, Observation) == 41


@pytest.mark.integration
def test_referential_integrity_and_transaction_rollback(db_session):
    seed_demo(db_session)
    source = db_session.get(Observation,demo_id('observation','laine/2020-09-14/hb'))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        source.patient_id = demo_id('patient','korhonen')
        db_session.flush()
    assert source.patient_id == demo_id('patient','laine')
    with pytest.raises(RuntimeError), db_session.begin_nested():
        reset(db_session)
        raise RuntimeError('simulate outer transaction failure')
    assert seed_demo(db_session)['unchanged'] == 66
