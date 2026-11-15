"""Manually authored English scenario responses: contract tests, NOT LLM accuracy."""
from datetime import timedelta
import json
from uuid import uuid4

import httpx
import pytest

from app.contracts.clinical_context import RetrievedContext, RetrievedObservation, SourceObservation
from app.contracts.qcancer import QCancerPredictors
from app.db.demo import load_dataset, rows_for
from app.extraction.providers import ChatCompletionsProvider, ProviderSettings
from app.extraction.service import ClinicalExtractor

# Independent scenario expectations; only the mock provider sees these responses.
SCENARIOS = {
    'laine': [('laine/2026-11-12/note', 'change_in_bowel_habit', 'present', 'current'),
              ('laine/2026-08-19/note', 'abdominal_pain', 'present', 'historical')],
    'nieminen': [('nieminen/2025-02-18/colonoscopy', 'investigation_planned', 'present', 'historical'),
                 ('nieminen/2026-10-29/followup', 'investigation_status_unknown', 'uncertain', 'unknown'),
                 ('nieminen/2026-11-12/note', 'rectal_bleeding', 'absent', 'current')],
    'heikkinen': [('heikkinen/2022-04-07/note', 'rectal_bleeding', 'present', 'historical'),
                  ('heikkinen/2022-06-16/colonoscopy', 'investigation_completed', 'present', 'historical'),
                  ('heikkinen/2022-09-20/symptoms', 'abdominal_pain', 'present', 'resolved'),
                  ('heikkinen/2026-11-12/note', 'abdominal_pain', 'absent', 'current')],
    'korhonen': [('korhonen/2026-09-10/note', 'rectal_bleeding', 'absent', 'historical')],
}


def scenario(key):
    data = load_dataset()
    patient = next(p for p in data.patients if p.key == key)
    mapped = list(rows_for(data))[-1][1]
    sources = {r['id']: SourceObservation.model_validate(r) for r in mapped if r['patient_id'] == patient.id}
    keyed = {o.key: sources[o.id] for o in data.observations if o.patient_id == patient.id}
    note = max((s for s in sources.values() if s.observation_type == 'clinical_note'), key=lambda s: s.observed_at)
    history = [s for s in sources.values() if s.observed_at < note.observed_at and s.recorded_at < note.observed_at]
    context = RetrievedContext(patient_id=patient.id, as_of=note.observed_at, query=note.text,
        retrieved_observations=tuple(RetrievedObservation(source=s) for s in history),
        retrieval={'name': 'synthetic-complete', 'version': '1', 'method': 'structured'},
        coverage={'status': 'complete', 'eligible_count': len(history)})
    findings = [dict(finding_type=kind, description='Manually authored scenario interpretation',
        polarity=polarity, temporal_status=temporal,
        uncertainty='Completion uncertain' if polarity == 'uncertain' else None,
        missing_information=[], evidence=[{'observation_id': str(keyed[source].id),
            'source_excerpt': keyed[source].text, 'start_offset': None, 'end_offset': None}])
        for source, kind, polarity, temporal in SCENARIOS[key]]
    return context, note, {'findings': findings, 'missing_information': [],
        'qcancer_predictors': QCancerPredictors().model_dump(mode='json')}


def mocked(response, calls):
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(response)}}]})
    return ChatCompletionsProvider(ProviderSettings(provider='openai', model='synthetic-mock'),
                                   transport=httpx.MockTransport(handle))


@pytest.mark.parametrize('key', SCENARIOS)
def test_english_scenarios_preserve_temporality_and_replay(key, tmp_path, caplog):
    context, note, response = scenario(key)
    calls = []
    provider = mocked(response, calls)
    extractor = ClinicalExtractor(provider, cache_dir=tmp_path)
    with caplog.at_level('INFO', logger='app.extraction.service'):
        first = extractor(context, input_note=note)
        provider.transport = None  # Even an accidental miss cannot call a paid API.
        second = extractor(context.model_copy(update={'generated_at': note.observed_at + timedelta(days=1)}), input_note=note)
    assert first.status != 'failed' and second.status == first.status
    assert len(calls) == 1
    assert 'extraction_cache miss' in caplog.text and 'extraction_cache hit' in caplog.text
    # Preserve the authored clinical scenarios above. The bounded validator is
    # intentionally unable to verify broad denials, and a referral is not a plan.
    # Assert the exact quarantine instead of silently treating omissions as absence.
    expected_rejections = {
        'nieminen': {0: 'investigation_state_not_supported', 2: 'outside_assertion_grammar'},
        'heikkinen': {3: 'outside_assertion_grammar'},
    }.get(key, {})
    assert second.semantic_validation['rejected'] == [
        {'path': f'findings[{index}]', 'reason': reason}
        for index, reason in expected_rejections.items()
    ]
    assert [(f.finding_type, f.polarity, f.temporal_status) for f in second.findings] == [
        tuple(row[1:]) for index, row in enumerate(SCENARIOS[key]) if index not in expected_rejections
    ]
    assert second.semantic_validation['coverage_status'] == 'incomplete'
    assert first.semantic_validation == second.semantic_validation
    assert not second.qcancer_predictors.binary_factors
    assert len(list(tmp_path.glob('*.json'))) == 1
    assert not (next(tmp_path.glob('*.json')).stat().st_mode & 0o077)


@pytest.mark.parametrize('change', ['text', 'time', 'note_id', 'model', 'prompt', 'history', 'coverage'])
def test_cache_invalidates_clinical_and_producer_changes(change, tmp_path):
    context, note, response = scenario('laine')
    provider = mocked(response, [])
    extractor = ClinicalExtractor(provider, cache_dir=tmp_path)
    assert extractor(context, input_note=note).status != 'failed'
    provider.transport = None
    if change == 'text': note = note.model_copy(update={'text': note.text + ' New information.'})
    elif change == 'time': note = note.model_copy(update={'recorded_at': note.recorded_at + timedelta(seconds=1)})
    elif change == 'note_id': note = note.model_copy(update={'id': uuid4()})
    elif change == 'model': provider.settings = provider.settings.model_copy(update={'model': 'another-model'})
    elif change == 'prompt':
        from unittest.mock import patch
        with patch('app.extraction.providers.PROMPT_VERSION', 'new-version'):
            assert extractor(context, input_note=note).status == 'failed'
        return
    elif change == 'history':
        hits = list(context.retrieved_observations)
        hits[0] = hits[0].model_copy(update={'source': hits[0].source.model_copy(update={'text': 'Changed historical content'})})
        context = context.model_copy(update={'retrieved_observations': tuple(hits)})
    elif change == 'coverage':
        context = context.model_copy(update={'coverage': {'status': 'unknown'}})
    assert extractor(context, input_note=note).issues[0].code == 'live_calls_disabled'


def test_qcancer_source_references_are_validated_before_cache(tmp_path):
    context, note, response = scenario('laine')
    response['qcancer_predictors']['binary_factors'] = [{'factor': 'new_abdopain', 'value': True,
        'evidence': [{'observation_id': str(note.id), 'source_excerpt': note.text}], 'uncertainty': None}]
    # Keep this test in sync with the existing QCancer schema, not provider defaults.
    QCancerPredictors.model_validate(response['qcancer_predictors'])
    provider = mocked(response, [])
    result = ClinicalExtractor(provider, cache_dir=tmp_path)(context, input_note=note)
    assert result.status != 'failed'
    response['qcancer_predictors']['binary_factors'][0]['evidence'][0]['observation_id'] = str(uuid4())
    result = ClinicalExtractor(mocked(response, []))(context, input_note=note)
    assert result.status == 'failed' and result.issues[0].code == 'missing_observation'
