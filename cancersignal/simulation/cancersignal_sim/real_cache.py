"""Strict, backend-independent cache validation and replay. No classifier fallback."""
from datetime import datetime
import hashlib
import json
from pathlib import Path


class RealModelError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def timestamp(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None: raise RealModelError('Decision timestamps must be timezone aware')
    return t


def clinical_input(case, decision):
    # Strict allowlists prevent labels, category, coded answers, arrival times and
    # simulation plans entering the actual backend/LLM input or input hash.
    patient=case['patient']
    if set(patient)-{'id','synthetic_name','birth_date','sex'}:
        raise RealModelError('Unexpected field in clinical patient record')
    if not patient['synthetic_name'].startswith('SYNTHETIC '):
        raise RealModelError('Only explicitly synthetic records are accepted')
    at=timestamp(decision['as_of']);initial=timestamp(case['decisions'][0]['as_of'])
    if abs((at-initial).total_seconds()/86400-decision['offset_days'])>1e-8:
        raise RealModelError('Decision offset does not match clinical timeline')
    observations=decision['observations'];seen=set();found=False
    allowed={'id','patient_id','encounter_id','observation_type','code','text','numeric_value','unit','status','observed_at','recorded_at'}
    for row in observations:
        if set(row)-allowed: raise RealModelError('Unexpected field in clinical observation')
        if row['patient_id']!=patient['id'] or row['id'] in seen:
            raise RealModelError('Cross-patient or duplicate clinical record')
        seen.add(row['id'])
        observed,recorded=timestamp(row['observed_at']),timestamp(row['recorded_at'])
        if row['id']==decision['input_note_id']:
            found=True
            if row['observation_type']!='clinical_note' or observed!=at or recorded>at:
                raise RealModelError('Current note outside decision-time scope')
        elif observed>=at or recorded>=at:
            raise RealModelError('Future or contemporaneous history cannot enter inference')
    if not found: raise RealModelError('Missing explicit input note')
    return {'patient':patient,'as_of':decision['as_of'],'input_note_id':decision['input_note_id'],
            'observations':sorted(observations,key=lambda r:r['id'])}


def load_cohort(path):
    cohort=json.loads(Path(path).read_text())
    ids=set()
    for case in cohort:
        pid=case['patient']['id']
        if pid in ids: raise RealModelError('Duplicate cohort patient')
        ids.add(pid)
        if not case['decisions'] or case['decisions'][0]['decision_id']!='initial':
            raise RealModelError('An initial decision is required')
        seen=set();last=-1
        for d in case['decisions']:
            if d['decision_id'] in seen or d['offset_days']<last:
                raise RealModelError('Duplicate or unsorted decision points')
            seen.add(d['decision_id']);last=d['offset_days'];clinical_input(case,d)
    return cohort


def backend_fingerprint(backend):
    base=Path(backend)
    paths=sorted((base/'app').rglob('*.py'))
    if not paths: raise RealModelError('CancerSignal backend source not found')
    return digest({str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def recommendation(response):
    if response.get('status')!='completed' or response.get('provenance',{}).get('error_code'):
        raise RealModelError('Incomplete/failed CancerSignal analysis cannot be replayed')
    triggers=response.get('trigger_results')
    if not isinstance(triggers,list) or not triggers:
        raise RealModelError('Missing actual rule evaluations')
    for t in triggers:
        if type(t.get('triggered')) is not bool or type(t.get('requires_clinician_review')) is not bool:
            raise RealModelError('Invalid clinical review contract')
        if t['triggered'] and (not t.get('evidence_observation_ids') or not t['requires_clinician_review']):
            raise RealModelError('Triggered rule has missing evidence or review flag')
    matched=[t for t in triggers if t['triggered'] and t['requires_clinician_review']]
    return {'review_signal':bool(matched),'urgency':'urgent' if any(t['priority']=='urgent' for t in matched) else 'review' if matched else 'none',
            'recommended_actions':[t['recommended_action'] for t in matched if t.get('recommended_action')],
            'matched_rule_ids':[t['trigger_rule_id'] for t in matched],
            'model_predictions':response.get('predictions',[]),
            'missing_information':response['provenance'].get('missing_information',[])}


def validate_entry(entry,case,decision,manifest):
    clinical=clinical_input(case,decision)
    for key,expected in [('patient_id',case['patient']['id']),('decision_id',decision['decision_id']),
                         ('input_sha256',digest(clinical)),('pipeline_sha256',manifest['pipeline_sha256']),
                         ('producer',manifest['producer'])]:
        if entry.get(key)!=expected: raise RealModelError(f'Stale or mismatched prediction: {key}')
    if entry.get('clinical_input')!=clinical: raise RealModelError('Cached clinical input differs')
    if digest(entry.get('response'))!=entry.get('response_sha256'):
        raise RealModelError('Prediction response integrity mismatch')
    if entry.get('producer',{}).get('kind')!='cancersignal.create_analysis' or entry['producer'].get('extraction',{}).get('method')!='llm':
        raise RealModelError('real_model requires an actual LLM-backed CancerSignal pipeline export')
    producer=entry['producer']['extraction']
    if producer.get('provider') not in ('verda','openai') or not all(producer.get(k) for k in ('model','prompt_version','configuration_digest')):
        raise RealModelError('Unrecognized or incomplete live-provider provenance')
    response=entry['response'];provenance=response['provenance']
    if '+clinical-extraction-' not in (provenance.get('extraction_method') or ''):
        raise RealModelError('Structured-only or fixture extraction is not real_model inference')
    if response.get('patient_id')!=case['patient']['id'] or timestamp(provenance['cutoff'])!=timestamp(decision['as_of']) or provenance['input_observation_id']!=decision['input_note_id']:
        raise RealModelError('Analysis patient/note/cutoff mismatch')
    sources={r['id']:r for r in clinical['observations']}
    if set(provenance.get('context_observation_ids',[])) != set(sources)-{decision['input_note_id']}:
        raise RealModelError('Retrieval snapshot differs from complete eligible input history')
    for source in response.get('source_observations',[]):
        original=sources.get(source['id'])
        if original is None or source['patient_id']!=case['patient']['id']:
            raise RealModelError('Prediction evidence outside original snapshot')
        for key in ['observation_type','text','code','unit','status']:
            if source.get(key)!=original.get(key): raise RealModelError('Changed prediction source')
        for key in ['observed_at','recorded_at']:
            if timestamp(source[key])!=timestamp(original[key]):raise RealModelError('Changed source timestamp')
        if str(source.get('numeric_value'))!=str(original.get('numeric_value')):
            from decimal import Decimal
            if source.get('numeric_value') is None or original.get('numeric_value') is None or Decimal(str(source['numeric_value']))!=Decimal(str(original['numeric_value'])):
                raise RealModelError('Changed source measurement')
    for finding in response.get('findings',[]):
        if finding['patient_id']!=case['patient']['id']:raise RealModelError('Cross-patient finding')
        for ref in finding['evidence']:
            source=sources.get(ref['observation_id'])
            if source is None:raise RealModelError('Missing evidence')
            quote=ref.get('source_excerpt')
            if quote is not None and quote not in (source.get('text') or ''):raise RealModelError('Ungrounded quote')
            start,end=ref.get('start_offset'),ref.get('end_offset')
            if (start is None)!=(end is None):raise RealModelError('Incomplete quote offsets')
            if start is not None and (type(start) is not int or type(end) is not int or start<0 or end<=start or (source.get('text') or '')[start:end]!=quote):
                raise RealModelError('Invalid quote offsets')
    for trigger in response.get('trigger_results',[]):
        if not set(trigger['evidence_observation_ids']).issubset(sources):raise RealModelError('Missing trigger evidence')
    for prediction in response.get('predictions',[]):
        if prediction['patient_id']!=case['patient']['id'] or timestamp(prediction['as_of'])>timestamp(decision['as_of']) or not set(prediction['evidence_observation_ids']).issubset(sources):
            raise RealModelError('Invalid numerical model scope')
    mapped=recommendation(response)
    if entry.get('recommendation')!=mapped: raise RealModelError('Cached recommendation differs from actual rules')
    return mapped


class CachedRealSignals:
    mode='real_model'

    def __init__(self,cohort,cache,*,backend=None,expected_pipeline_sha256=None):
        self.cohort={c['patient']['id']:c for c in cohort}
        root=Path(cache)
        try:self.manifest=json.loads((root/'manifest.json').read_text())
        except (OSError,ValueError):raise RealModelError('No valid real-model manifest; run authentic inference first') from None
        if expected_pipeline_sha256 is not None:
            if len(expected_pipeline_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_pipeline_sha256):
                raise RealModelError('Expected pipeline fingerprint must be a lowercase SHA-256')
            if expected_pipeline_sha256 != self.manifest.get('pipeline_sha256'):
                raise RealModelError('Cache differs from explicitly pinned historical pipeline')
        self.validation = {'mode': 'backend_source' if backend is not None else 'explicit_historical_pin' if expected_pipeline_sha256 is not None else 'cache_contract_only',
                           'pipeline_sha256': self.manifest['pipeline_sha256']}
        if backend is not None and backend_fingerprint(backend)!=self.manifest['pipeline_sha256']:
            raise RealModelError('Backend changed since inference; regenerate or explicitly pin the original backend')
        self.entries={};self.decisions={}
        for case in cohort:
            pid=case['patient']['id'];self.decisions[pid]=case['decisions']
            for decision in case['decisions']:
                key=pid+':'+decision['decision_id']
                name=self.manifest.get('entries',{}).get(key)
                if not name or Path(name).name!=name:raise RealModelError('Missing real prediction for '+key)
                try:entry=json.loads((root/name).read_text())
                except (OSError,ValueError):raise RealModelError('Unreadable real prediction for '+key) from None
                validate_entry(entry,case,decision,self.manifest)
                self.entries[key]=entry

    def initial(self,p):
        key=p.patient_id+':initial'
        if key not in self.entries:raise RealModelError('No real prediction for patient')
        return self.entries[key]

    def signal(self,p,seed):
        return self.initial(p)['recommendation']['review_signal']

    def later_decision(self,p,stage,elapsed):
        candidates=[d for d in self.decisions[p.patient_id] if d['decision_id']==stage]
        if not candidates:return None  # No new clinical record, not a random replacement.
        d=candidates[0]
        if elapsed+1e-9<d['offset_days']:
            raise RealModelError('Follow-up prediction is not yet available at this simulated time')
        return self.entries[p.patient_id+':'+stage]
