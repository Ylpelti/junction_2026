"""Mocked extraction, real rules/explanations and isolated PostgreSQL persistence."""
from dataclasses import replace
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.api.dependencies import get_analysis_pipeline
from app.db.seed import seed, synthetic_id
from app.db.seed_rules import seed_rules
from app.db.session import get_session
from app.main import create_app
from app.models import Observation
from app.extraction.providers import FixtureProvider
from app.extraction.service import ClinicalExtractor
from app.rag.extraction import StructuredSourceExtractor
from app.services.llm_extraction import LlmNoteExtractor

pytestmark = pytest.mark.integration

@pytest.mark.parametrize('omit_finding', [False, True])
def test_omissions_never_become_negative_and_valid_findings_reach_explanations(db_session, omit_finding):
    seed(db_session)
    seed_rules(db_session)
    patient_id = str(synthetic_id('patient/0'))
    db_session.execute(delete(Observation).where(Observation.patient_id == patient_id,
        Observation.observation_type == 'laboratory'))
    db_session.commit()
    note_id = str(uuid4())
    text = 'Patient reports rectal bleeding.'
    finding = {'finding_type':'rectal_bleeding', 'description':'Reported rectal bleeding',
        'polarity':'present', 'temporal_status':'current', 'uncertainty':None,
        'missing_information':[], 'evidence':[{'observation_id':note_id, 'source_excerpt':text}]}
    raw = json.dumps({'findings':[] if omit_finding else [finding], 'missing_information':[]})
    extractor = LlmNoteExtractor(StructuredSourceExtractor(), clinical=ClinicalExtractor(FixtureProvider(raw)))
    pipeline = replace(get_analysis_pipeline(), extractor=extractor)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post(f'/api/v1/patients/{patient_id}/analyses', json={'note':{
            'id':note_id, 'patient_id':patient_id, 'observation_type':'clinical_note', 'text':text,
            'observed_at':'2026-11-15T09:00:00Z', 'recorded_at':'2026-11-15T09:00:00Z'}})
        assert response.status_code == 201
        result = response.json()
        assert result['status'] == 'completed'
        assert result['provenance']['semantic_validation']['coverage_status'] == 'incomplete'
        assert not result['provenance']['semantic_validation']['rejected']
        assert any('Omitted or rejected findings are unknown' in gap for gap in result['provenance']['missing_information'])
        triggered = [r for r in result['trigger_results'] if r['triggered']]
        if omit_finding:
            assert not triggered
            assert 'No negative screening conclusion' in result['explanation']
            assert 'No signals identified' not in result['clinical_explanation']['summary_en']
        else:
            assert any(r['rule_name'].startswith('SUO-06') for r in triggered)
            assert any(note_id in row['observation_ids'] for row in result['clinical_explanation']['findings'])
            assert 'review' in result['clinical_explanation']['summary_en'].lower()
        assert client.get(f'/api/v1/analyses/{result["id"]}').json() == result
