"""Real PostgreSQL/FastAPI/rules; mocked Finnish provider, never clinical validation."""
import json

import httpx
import pytest

from app.core.config import get_pipeline_settings
from app.db.demo import seed_demo
from app.db.seed_rules import seed_rules
from app.extraction.providers import ProviderSettings
from scripts.verify_llm_demo import MeteredProvider, verify
from tests.extraction.test_demo_readiness import SCENARIOS, scenario


@pytest.mark.integration
def test_four_saved_notes_full_pipeline_and_offline_replay(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv('CANCERSIGNAL_EXPLANATION', 'deterministic')
    monkeypatch.setenv('CANCERSIGNAL_RETRIEVAL', 'auto')
    get_pipeline_settings.cache_clear()
    seed_demo(db_session)
    seed_rules(db_session)
    db_session.commit()
    responses = {str(scenario(key)[1].id): scenario(key)[2] for key in SCENARIOS}
    def respond(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][1]['content'])
        raw = responses[payload['current_note']['id']]
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(raw)}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    provider = MeteredProvider(ProviderSettings(provider='openai', model='synthetic-mock'),
                              allow_live=True, transport=httpx.MockTransport(respond))
    try:
        report = verify(db_session, provider, tmp_path)
        assert report['passed']
        assert len(provider.calls) == 4  # Mock calls, not external inference.
        assert [e['state'] for e in report['cache_events']] == ['miss', 'hit'] * 4
        for patient in report['patients']:
            for run in patient['runs']:
                analysis = run['analysis']
                assert analysis['clinical_explanation']['mode'] == 'fallback'
                assert analysis['predictions'][0]['value']['status'] == 'insufficient_data'
                assert analysis['predictions'][0]['value']['any_cancer_risk_percent'] is None
                sources = {row['id'] for row in analysis['source_observations']}
                assert all(ref['observation_id'] in sources for f in analysis['findings'] for ref in f['evidence'])
                if patient['patient'] in ('SYNTHETIC Heikkinen', 'SYNTHETIC Korhonen'):
                    assert not any(r['triggered'] for r in analysis['trigger_results'])
    finally:
        get_pipeline_settings.cache_clear()


def test_smoke_call_budget_and_offline_gate():
    from app.extraction.providers import ProviderError
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}],
        'usage': {'total_tokens': 2, 'untrusted_extra': 'must not enter report'}}))
    provider = MeteredProvider(ProviderSettings(provider='openai', model='mock'), transport=transport)
    with pytest.raises(ProviderError, match='Offline replay'):
        provider.complete([], {})
    assert not provider.calls
    provider.allow_live = True
    for _ in range(4):
        assert provider.complete([], {}) == '{}'
    with pytest.raises(ProviderError, match='budget exhausted'):
        provider.complete([], {})
    assert len(provider.calls) == 4
    assert all(c['usage'] == {'total_tokens': 2} for c in provider.calls)
