"""Check a deployed API; --patient-id explicitly writes a synthetic analysis.

A successful LLM adapter response does not prove a fresh provider call: use a
fresh cache (or unset cache directory) on the backend for live verification.
Never prints response bodies, patient records, credentials or provider errors.
"""
import argparse
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--frontend-origin', required=True)
    parser.add_argument('--patient-id', type=UUID)
    parser.add_argument('--require-llm', action='store_true')
    args = parser.parse_args()
    if args.require_llm and not args.patient_id:
        parser.error('--require-llm needs --patient-id')
    report = {}
    try:
        with httpx.Client(base_url=args.api_url.rstrip('/'), timeout=180) as client:
            for route in ('/health', '/ready', '/api/v1/patients'):
                response = client.get(route)
                response.raise_for_status()
                report[route] = response.status_code
            response = client.options('/api/v1/patients', headers={
                'Origin': args.frontend_origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type',
            })
            response.raise_for_status()
            assert response.headers.get('access-control-allow-origin') == args.frontend_origin, 'cors'
            report['cors'] = 'passed'
            response = client.get('/api/v1/patients/not-a-uuid')
            assert response.status_code == 422, 'validation'
            report['invalid_input'] = '422'
            if args.patient_id:
                pid = str(args.patient_id)
                patient = client.get(f'/api/v1/patients/{pid}')
                patient.raise_for_status()
                assert patient.json()['synthetic_name'].startswith('SYNTHETIC'), 'synthetic_patient_required'
                now = datetime.now(timezone.utc).isoformat()
                response = client.post(f'/api/v1/patients/{pid}/analyses', json={'note': {
                    'patient_id': pid, 'observation_type': 'clinical_note',
                    'text': f'SYNTHETIC deployment check {uuid4()}. Patient reports visible blood in stool for three weeks. No weight loss.',
                    'observed_at': now, 'recorded_at': now,
                }})
                response.raise_for_status()
                result = response.json()
                report['analysis_status'] = result['status']
                report['pipeline_error_code'] = result.get('provenance', {}).get('error_code')
                assert result['status'] == 'completed', 'analysis_failed'
                assert result['patient_id'] == pid, 'patient_mismatch'
                method = result['provenance']['extraction_method'] or ''
                if args.require_llm:
                    assert 'clinical-extraction' in method, 'llm_not_enabled'
                saved = client.get(f"/api/v1/analyses/{result['id']}")
                saved.raise_for_status()
                assert saved.json() == result, 'persistence_mismatch'
                report.update(analysis='completed', persistence='passed', extraction_method=method,
                              retrieval_method=result['provenance']['retrieval_method'])
    except (httpx.HTTPError, AssertionError, KeyError, ValueError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        if isinstance(error, AssertionError):
            report['failed_check'] = str(error)
        print(json.dumps(report, indent=2))
        raise SystemExit(1) from None
    report['status'] = 'passed'
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
