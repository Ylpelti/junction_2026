"""Verify seeded demo sources through actual HTTP/current pipeline and configured DB.

Writes one persisted analysis per patient. Does not seed, reset, submit reviews,
change rules, download weights or enable external inference. Run from backend.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.core.config import get_settings, get_pipeline_settings
from app.db.demo import load_dataset, rows_for
from app.db.session import get_engine
from app.models import Observation, Patient, TriggerRule
from app.reasoning.derived_findings import HB_CODES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval', choices=['auto', 'lexical', 'hybrid'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    settings, pipeline = get_settings(), get_pipeline_settings()
    if pipeline.extraction_allow_live or pipeline.explanation_allow_live:
        parser.error('Disable external live inference before this verification')
    data = load_dataset()
    report = {'database': {'host': settings.postgres_host, 'port': settings.postgres_port,
                          'name': settings.postgres_db},
              'extraction': pipeline.extraction,
              'requested_retrieval': args.retrieval or pipeline.retrieval, 'patients': []}
    with Session(get_engine()) as session:
        assert session.scalar(text('SELECT current_database()')) == settings.postgres_db
        # Compare every canonical source field against persisted PostgreSQL data.
        for model, rows in rows_for(data):
            for expected in rows:
                actual = session.get(model, expected['id'])
                assert actual is not None, f'Missing seeded record: {expected["id"]}'
                assert all(getattr(actual, k) == v for k, v in expected.items()), expected['id']
        report['enabled_rules'] = session.scalar(select(text('count(*)')).select_from(TriggerRule).where(TriggerRule.enabled.is_(True)))
        assert report['enabled_rules'] > 0, 'No enabled rules; configure baseline rules first'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    if args.retrieval:
        env['CANCERSIGNAL_RETRIEVAL'] = args.retrieval
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1', '--port', str(port)], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=180) as client:
            for _ in range(100):
                try:
                    if client.get('/health').is_success:
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('Uvicorn exited before readiness')
                time.sleep(.1)
            else:
                raise RuntimeError('Uvicorn readiness timed out')
            for patient in data.patients:
                pid = str(patient.id)
                response = client.get(f'/api/v1/patients/{pid}')
                response.raise_for_status()
                assert response.json()['synthetic_name'] == patient.synthetic_name
                observations = []
                while True:
                    response = client.get(f'/api/v1/patients/{pid}/observations', params={'limit': 200, 'offset': len(observations)})
                    response.raise_for_status()
                    page = response.json()
                    observations.extend(page)
                    if len(page) < 200:
                        break
                assert all(o['patient_id'] == pid for o in observations)
                note = max((o for o in data.observations if o.patient_id == patient.id and o.observation_type == 'clinical_note'), key=lambda o: o.observed_at)
                labs = [o for o in observations if o['observation_type'] == 'laboratory'
                        and datetime.fromisoformat(o['observed_at']) < note.observed_at
                        and datetime.fromisoformat(o['recorded_at']) < note.observed_at]
                assert labs and all(o['code'].upper() in HB_CODES and o['unit'] == 'g/L' for o in labs)
                response = client.post(f'/api/v1/patients/{pid}/analyses', json={'note_observation_id': str(note.id)})
                response.raise_for_status()
                result = response.json()
                assert result['status'] == 'completed', result['provenance']
                method = result['provenance']['retrieval_method']
                if report['requested_retrieval'] in ('lexical', 'hybrid'):
                    assert ':' + report['requested_retrieval'] in method, method
                sources = {o['id']: o for o in result['source_observations']}
                # Response sources contain cited evidence only; provenance tracks full context.
                context_ids = set(result['provenance']['context_observation_ids'])
                assert {o['id'] for o in labs} <= context_ids
                by_id = {o['id']: o for o in observations}
                assert context_ids <= by_id.keys()
                for identifier in context_ids:
                    assert datetime.fromisoformat(by_id[identifier]['observed_at']) < note.observed_at
                    assert datetime.fromisoformat(by_id[identifier]['recorded_at']) < note.observed_at
                assert all(o['patient_id'] == pid for o in sources.values())
                for source in sources.values():
                    if source['id'] != str(note.id):
                        assert datetime.fromisoformat(source['observed_at']) < note.observed_at
                        assert datetime.fromisoformat(source['recorded_at']) < note.observed_at
                for lab in labs:
                    if lab['id'] in sources:
                        assert sources[lab['id']] == lab
                latest_lab = max(labs, key=lambda o: (o['observed_at'], o['recorded_at'], o['id']))
                assert latest_lab['id'] in sources
                for finding in result['findings']:
                    assert {ref['observation_id'] for ref in finding['evidence']} <= sources.keys()
                for prediction in result['predictions']:
                    assert set(prediction['evidence_observation_ids']) <= sources.keys()
                assert str(note.id) not in result['provenance']['context_observation_ids']
                saved = client.get(f'/api/v1/analyses/{result["id"]}')
                saved.raise_for_status()
                assert saved.json() == result
                assert result['clinical_explanation'] is not None
                item = {'patient': patient.synthetic_name, 'patient_id': pid,
                    'observation_count': len(observations), 'analysis_id': result['id'],
                    'status': result['status'], 'retrieval': method,
                    'context_observation_ids': sorted(context_ids),
                    'cited_observation_ids': sorted(sources),
                    'hemoglobin': [{'date': o['observed_at'], 'code': o['code'], 'value': o['numeric_value'], 'unit': o['unit']} for o in labs],
                    'finding_types': [f['finding_type'] for f in result['findings']],
                    'triggered_rules': [r['rule_name'] for r in result['trigger_results'] if r['triggered']],
                    'predictions': result['predictions'],
                    'missing_information': result['provenance']['missing_information'],
                    'explanation_mode': result['clinical_explanation']['mode']}
                report['patients'].append(item)
                print(f'PASS {patient.synthetic_name}: {len(observations)} observations, {len(labs)} Hb, {method}', flush=True)
    finally:
        process.terminate()
        process.wait(timeout=10)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
