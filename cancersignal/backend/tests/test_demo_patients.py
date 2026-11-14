"""Source-preserving seed and full database analysis with fixed note extraction.

FixtureProvider replays the case's coded facts for today's note; this verifies
retrieval/derivation/rules/persistence, not live LLM extraction accuracy.
"""
import json
from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import select

from app.api.dependencies import get_analysis_pipeline
from app.db.seed import DEMO_CASES_FILE, demo_rows, seed, synthetic_id
from app.db.seed_rules import seed_rules
from app.extraction.providers import FixtureProvider
from app.extraction.service import ClinicalExtractor
from app.models import Observation, Patient
from app.rag.extraction import StructuredSourceExtractor
from app.schemas.analysis import AnalysisRequest
from app.services.analysis_service import create_analysis
from app.services.llm_extraction import LlmNoteExtractor

CASES = json.loads(DEMO_CASES_FILE.read_text(encoding="utf-8"))["cases"]


def test_demo_rows_preserve_source_records_and_stable_ids():
    patients, observations = demo_rows()
    assert (patients, observations) == demo_rows()
    assert len(patients) == 4 and len(observations) == 22
    assert len({r['id'] for r in observations}) == len(observations)
    by_id = {r['id']: r for r in observations}
    for case, patient in zip(CASES, patients):
        assert patient['synthetic_name'].startswith('SYNTHETIC ')
        assert str(patient['birth_date']) == case['patient']['birth_date']
        assert patient['sex'] == case['patient']['sex']
        for source in [*case['history'], case['note']]:
            row = by_id[synthetic_id(f"demo-eval/v1/{case['id']}/{source['ref']}")]
            assert row['patient_id'] == patient['id']
            for field in ('text', 'code', 'numeric_value', 'unit', 'status'):
                assert row[field] == source.get(field)
            assert row['observed_at'] == row['recorded_at'] == datetime.fromisoformat(source['observed_at'])


@pytest.mark.integration
def test_demo_seed_preserves_existing_rows(db_session):
    seed(db_session)
    ids = set(db_session.scalars(select(Observation.id)))
    patient_id = synthetic_id('demo-eval/v1/EVAL-001/patient')
    note_id = synthetic_id('demo-eval/v1/EVAL-001/NOTE-T')
    patient = db_session.get(Patient, patient_id)
    note = db_session.get(Observation, note_id)
    patient.synthetic_name = 'SYNTHETIC edited demo'
    note.text = 'SYNTHETIC existing note must be preserved'
    db_session.flush()
    seed(db_session)
    db_session.expire_all()
    assert set(db_session.scalars(select(Observation.id))) == ids
    assert db_session.get(Patient, patient_id).synthetic_name == 'SYNTHETIC edited demo'
    assert db_session.get(Observation, note_id).text == 'SYNTHETIC existing note must be preserved'


@pytest.mark.integration
@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_today_note_analysis_matches_variant_c(db_session, case):
    seed(db_session)
    seed_rules(db_session)
    patient_id = synthetic_id(f"demo-eval/v1/{case['id']}/patient")
    note_id = synthetic_id(f"demo-eval/v1/{case['id']}/NOTE-T")
    # Use original coded facts as a deterministic provider response, never expected rules.
    findings = [{
        'finding_type': f['code'], 'description': f['text'],
        'polarity': 'absent' if f['status'] == 'negated' else 'present',
        'temporal_status': 'current', 'uncertainty': None, 'missing_information': [],
        'evidence': [{'observation_id': str(note_id), 'source_excerpt': f['text'],
                      'start_offset': None, 'end_offset': None}],
    } for f in case['note']['coded']]
    extractor = LlmNoteExtractor(StructuredSourceExtractor(), clinical=ClinicalExtractor(
        FixtureProvider(json.dumps({'missing_information': [], 'findings': findings}))))
    pipeline = replace(get_analysis_pipeline(), extractor=extractor)
    result = create_analysis(db_session, patient_id, AnalysisRequest(note_observation_id=note_id), pipeline)
    assert result.status == 'completed', result
    triggered = [r for r in result.trigger_results if r.triggered]
    assert {r.rule_name.split(':')[0] for r in triggered} == set(case['expected']['rules'])
    level = 'urgent' if any(r.priority == 'urgent' for r in triggered) else 'review' if triggered else 'none'
    assert level == case['expected']['level']
    today = datetime.fromisoformat(case['note']['observed_at'])
    sources = {r.id: r for r in result.source_observations}
    assert all(r.patient_id == patient_id for r in sources.values())
    history = [db_session.get(Observation, i) for i in result.provenance.context_observation_ids]
    assert all(r.patient_id == patient_id and r.observed_at < today and r.recorded_at < today
               for r in history)
    assert note_id not in result.provenance.context_observation_ids
