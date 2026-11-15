"""English migration invariants; no external model calls."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.db.demo import DATA, load_dataset
from app.extraction.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from app.explanation.schemas import ExplanationResult


def test_versioned_dataset_preserves_clinical_values_and_timeline():
    original = json.loads(DATA.with_name('patients.json').read_text())
    english = json.loads(DATA.read_text())
    mapping = json.loads(DATA.with_name('en-v2-id-map.json').read_text())
    assert english['version'] == 2
    assert set(mapping).isdisjoint(mapping.values())
    assert len(load_dataset().observations) == len(original['observations']) == 41
    for group in ('patients', 'encounters', 'observations'):
        assert len(original[group]) == len(english[group])
        for old, new in zip(original[group], english[group]):
            for key, value in old.items():
                if key in ('text', 'organization', 'encounter_type', 'synthetic_name'):
                    continue
                expected = mapping.get(value, value) if isinstance(value, str) else value
                assert new[key] == expected
    notes = [o.text for o in load_dataset().observations if o.observation_type == 'clinical_note']
    assert sum('Does not currently smoke' in t for t in notes) == 3
    assert not any('never smoked' in t.lower() for t in notes)
    assert all('SYNTHETIC' in t for t in notes)


def test_english_contract_and_prompt_are_explicit():
    schema = ExplanationResult.model_json_schema()
    assert schema['properties']['contract_version']['const'] == '2.0'
    assert schema['properties']['language']['const'] == 'en'
    assert 'summary_en' in schema['required']
    assert 'summary_fi' not in schema['properties']
    assert PROMPT_VERSION == 'clinical-extraction-en-3'
    assert 'does not establish never smoking' in SYSTEM_PROMPT


@pytest.mark.integration
def test_legacy_explanation_read_adapter_preserves_storage(db_session, monkeypatch):
    from app.core.config import get_pipeline_settings
    from app.db.seed import seed, synthetic_id
    from app.db.session import get_session
    from app.main import create_app
    from app.models import AnalysisRun
    from uuid import UUID
    monkeypatch.setenv('CANCERSIGNAL_EXTRACTION', 'off')
    monkeypatch.setenv('CANCERSIGNAL_EXPLANATION', 'deterministic')
    get_pipeline_settings.cache_clear()
    seed(db_session)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            created = client.post(f'/api/v1/patients/{synthetic_id("patient/0")}/analyses',
                json={'note_observation_id': str(synthetic_id('note/0/3'))}).json()
            run = db_session.get(AnalysisRun, UUID(created['id']))
            original = deepcopy(run.details)
            original['clinical_explanation'] = {'contract_version': '1.0', 'language': 'fi',
                                               'summary_fi': 'LEGACY SYNTHETIC TEXT'}
            run.details = deepcopy(original)
            db_session.commit()
            result = client.get(f'/api/v1/analyses/{run.id}').json()
            assert result['clinical_explanation']['contract_version'] == '2.0'
            assert result['clinical_explanation']['language'] == 'en'
            assert result['clinical_explanation']['legacy_adapter']['mode'] == 'read_only_deterministic_render'
            assert result['source_observations'] == created['source_observations']
            assert result['findings'] == created['findings']
            db_session.refresh(run)
            assert run.details == original
    finally:
        get_pipeline_settings.cache_clear()
