"""Four saved synthetic notes through FastAPI + PostgreSQL; paid calls opt-in only.

No seeding/reset, no new notes, no explanation provider calls. Live mode requires
an empty cache, makes at most four extraction calls, then verifies offline replay.
"""
import argparse
from dataclasses import replace
import json
import logging
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_analysis_pipeline
from app.core.config import get_pipeline_settings
from app.db.demo import load_dataset, rows_for
from app.db.session import get_engine, get_session
from app.extraction.providers import ChatCompletionsProvider, ProviderError, ProviderSettings
from app.extraction.service import ClinicalExtractor
from app.main import create_app
from app.models import Observation, TriggerRule
from app.rag.extraction import StructuredSourceExtractor
from app.services.llm_extraction import LlmNoteExtractor


class SmokePreflightError(ValueError):
    """Safe synthetic/configuration error, containing no credentials or records."""


class MeteredProvider(ChatCompletionsProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def complete(self, messages, schema):
        if not self.allow_live:
            raise ProviderError('live_calls_disabled', 'Offline replay cache miss; no provider call made.')
        if len(self.calls) >= 4:
            raise ProviderError('call_budget', 'Four-call smoke budget exhausted.')
        item = {'seconds': None, 'usage': None}
        self.calls.append(item)
        start = time.perf_counter()
        try:
            return super().complete(messages, schema)
        finally:
            item['seconds'] = round(time.perf_counter() - start, 3)

    def _content(self, raw):
        content = super()._content(raw)
        envelope = json.loads(raw)
        usage = envelope.get('usage', {})
        self.calls[-1]['usage'] = {key: value for key, value in usage.items()
            if key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
            and type(value) is int and value >= 0} if isinstance(usage, dict) else None
        return content


class CaptureExtractor(ClinicalExtractor):
    def __call__(self, *args, **kwargs):
        self.batch = super().__call__(*args, **kwargs)
        return self.batch


class CacheEvents(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        if record.msg.startswith('extraction_cache '):
            self.events.append({'state': record.args[0], 'key': record.args[1]})


def verify(session, provider, cache_dir):
    """Also used by disposable-DB tests with an explicitly mocked provider."""
    data = load_dataset()
    # Compare full snapshots, including record content, IDs, dates and lab mapping.
    for model, rows in rows_for(data):
        for expected in rows:
            actual = session.get(model, expected['id'])
            if actual is None or any(getattr(actual, k) != v for k, v in expected.items()):
                raise SmokePreflightError('Database does not match the canonical synthetic dataset')
    patient_ids = [p.id for p in data.patients]
    actual_ids = set(session.scalars(select(Observation.id).where(Observation.patient_id.in_(patient_ids))))
    if actual_ids != {o.id for o in data.observations}:
        raise SmokePreflightError('Additional or missing records make this an unapproved synthetic snapshot')
    if not session.scalar(select(TriggerRule.id).where(TriggerRule.enabled.is_(True)).limit(1)):
        raise SmokePreflightError('No enabled clinical rules')
    if get_pipeline_settings().explanation != 'deterministic':
        raise SmokePreflightError('Set CANCERSIGNAL_EXPLANATION=deterministic for the bounded test')
    clinical = CaptureExtractor(provider, cache_dir=cache_dir)
    pipeline = replace(get_analysis_pipeline(), extractor=LlmNoteExtractor(
        StructuredSourceExtractor(), clinical=clinical))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    events = CacheEvents()
    logger = logging.getLogger('app.extraction.service')
    level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(events)
    report = {'transport': 'in-process FastAPI TestClient; actual configured PostgreSQL',
              'patients': [], 'cache_events': events.events}
    try:
        with TestClient(app) as client:
            for patient in data.patients:
                note = max((o for o in data.observations if o.patient_id == patient.id
                    and o.observation_type == 'clinical_note'), key=lambda o: o.observed_at)
                item = {'patient': patient.synthetic_name, 'note_id': str(note.id), 'runs': []}
                report['patients'].append(item)
                live = provider.allow_live
                try:
                    for attempt in range(2):
                        if attempt:
                            provider.allow_live = False
                        start = time.perf_counter()
                        response = client.post(f'/api/v1/patients/{patient.id}/analyses',
                                               json={'note_observation_id': str(note.id)})
                        response.raise_for_status()
                        result = response.json()
                        saved = client.get(f'/api/v1/analyses/{result["id"]}')
                        saved.raise_for_status()
                        assert saved.json() == result, 'GET readback differs'
                        item['runs'].append({'seconds': round(time.perf_counter() - start, 3),
                            'status': result['status'], 'readback_equal': True,
                            'extraction': clinical.batch.model_dump(mode='json'),
                            'analysis': result})
                finally:
                    provider.allow_live = live
        report['passed'] = all(run['status'] == 'completed' for p in report['patients'] for run in p['runs'])
        # Independent labels enter only the report AFTER inference, never prompts.
        report['scenario_labels'] = json.loads((Path(__file__).resolve().parents[1] /
            'tests/fixtures/demo/labels.json').read_text())
        report['clinical_accuracy'] = 'not automatically assessed; review temporal interpretations, false alerts and missed findings against scenario labels'
        return report
    finally:
        logger.removeHandler(events)
        logger.setLevel(level)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-paid-live', action='store_true')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.allow_paid_live and args.cache_dir.exists() and any(args.cache_dir.iterdir()):
        parser.error('Live verification requires an empty cache directory to prove real calls')
    settings = ProviderSettings(_env_file=args.env_file)
    if args.allow_paid_live and not settings.api_key.get_secret_value():
        parser.error('Configure EXTRACTION_API_KEY securely before authorizing live calls')
    provider = MeteredProvider(settings, allow_live=args.allow_paid_live)
    report = {'mode': 'live_requested' if args.allow_paid_live else 'offline_replay',
              'provider': settings.provider, 'model': settings.model,
              'provenance': provider.provenance.model_dump(mode='json'),
              'max_calls': 4, 'max_output_tokens_per_call': settings.max_output_tokens,
              'cost': None, 'cost_note': 'No price table assumed; usage is provider-reported when available',
              'calls': provider.calls, 'passed': False, 'live_success': False}
    start = time.perf_counter()
    try:
        with Session(get_engine()) as session:
            report.update(verify(session, provider, args.cache_dir))
        report['live_success'] = bool(args.allow_paid_live and len(provider.calls) == 4 and report['passed'])
    except SmokePreflightError as exc:
        report['preflight_error'] = str(exc)
    except Exception as exc:
        # No raw exception text: database/provider exceptions may contain secrets.
        report['runner_error_type'] = type(exc).__name__
    finally:
        report['seconds'] = round(time.perf_counter() - start, 3)
        report['call_count'] = len(provider.calls)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"{'PASS' if report['passed'] else 'FAIL'}; {len(provider.calls)} provider attempts; report: {args.output}")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
