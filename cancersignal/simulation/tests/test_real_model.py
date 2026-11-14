"""Mechanics-only fixtures. These are NOT authentic predictions or model evaluation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from cancersignal_sim.real_cache import clinical_input,digest,CachedRealSignals,RealModelError,load_cohort,recommendation,validate_entry
from cancersignal_sim.engine import simulate
from cancersignal_sim.inputs import Patient
ROOT=Path(__file__).resolve().parents[1]


class RealInputTests(unittest.TestCase):
    def setUp(self):
        self.case=json.loads((ROOT/'data/real_model/cohort.json').read_text())[0]
        self.d=self.case['decisions'][0]

    def test_inference_payload_excludes_evaluation_fields(self):
        c=deepcopy(self.case);c.update(relevant=True,expected={'level':'urgent'},category='secret label')
        payload=clinical_input(c,c['decisions'][0])
        self.assertEqual(set(payload),{'patient','as_of','input_note_id','observations'})
        self.assertEqual(payload,clinical_input(self.case,self.d))
        self.assertNotIn('coded',json.dumps(payload))

    def test_labels_cannot_be_hidden_in_patient_or_record_fields(self):
        for obj in ('patient','record'):
            c=deepcopy(self.case)
            target=c['patient'] if obj=='patient' else c['decisions'][0]['observations'][0]
            target['relevant']=True
            with self.assertRaises(RealModelError):clinical_input(c,c['decisions'][0])

    def test_future_and_wrong_patient_rejected(self):
        for change in ({'observed_at':'2030-01-01T00:00:00Z'},{'recorded_at':'2030-01-01T00:00:00Z'},{'patient_id':'someone-else'}):
            c=deepcopy(self.case);c['decisions'][0]['observations'][0].update(change)
            with self.assertRaises(RealModelError):clinical_input(c,c['decisions'][0])

    def test_missing_cache_fails(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RealModelError,'No valid real-model'):CachedRealSignals([self.case],d)

    def test_changed_input_hash_rejected_before_any_prediction_use(self):
        manifest={'pipeline_sha256':'p','producer':{}}
        with self.assertRaisesRegex(RealModelError,'mismatched'):
            validate_entry({'patient_id':self.case['patient']['id'],'decision_id':'initial','input_sha256':'old'},self.case,self.d,manifest)

    def test_failed_response_not_negative(self):
        with self.assertRaises(RealModelError):recommendation({'status':'failed'})

    def test_offset_must_match_real_record_time(self):
        c=deepcopy(self.case);c['decisions'][0]['offset_days']=14
        with self.assertRaises(RealModelError):clinical_input(c,c['decisions'][0])


class MechanicsProvider:
    """Explicit UNIT TEST controlled provider, never exported as actual AI output."""
    mode='real_model'
    def signal(self,p,seed):return True
    def initial(self,p):return {'input_sha256':'unit-test','response_sha256':'unit-test','recommendation':{'review_signal':True,'urgency':'urgent'}}
    def later_decision(self,p,stage,elapsed):return self.initial(p) if stage=='followup' else None


class RealRoutingTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((ROOT/'config/real_model.json').read_text());self.c.update(duration=100,warmup=0,seeds=[1,2])
        self.c['signal'].update(review_probability=1,escalation_probability=1)
        self.c['routing'].update(initial_relevant=0,followup_relevant=0)
        self.p=[Patient('unit-test',0,True,'unit test only')]

    def test_random_fallback_is_forbidden(self):
        with self.assertRaisesRegex(ValueError,'fallback is forbidden'):simulate(self.c,self.p,1,model='C')

    def test_tpr_and_fpr_do_not_control_real_mode(self):
        runs=[]
        for rate in (0,1):
            c=deepcopy(self.c);c['signal'].update(tpr=rate,fpr=rate)
            runs.append(simulate(c,self.p,1,model='C',signals=MechanicsProvider()))
        self.assertEqual(runs[0]['events'],runs[1]['events'])
        self.assertTrue(runs[0]['patients'][0]['signal'])

    def test_real_mode_never_uses_hypothetical_duplicate_cancellation(self):
        self.c['routing']['initial_relevant']=1
        self.c['workflow'].update(repeat_probability=1,avoidable_repeat_rate=1,duplicate_flag_tpr=1,clinician_cancel_probability=1)
        p=simulate(self.c,self.p,1,model='D',signals=MechanicsProvider())['patients'][0]
        self.assertIn('diagnostic_repeat_end',p)
        self.assertFalse(p['repeat_avoided'])

    def test_later_actual_prediction_consumes_gp_review_capacity(self):
        class LaterOnly(MechanicsProvider):
            def signal(self,p,seed):return False
        self.c['workflow']['followup_probability']=1;self.c['workflow']['monitor_probability']=0
        p=simulate(self.c,self.p,1,model='C',signals=LaterOnly())['patients'][0]
        self.assertIn('review_followup_start',p)
        self.assertGreater(p['review_followup_end'],p['review_followup_start'])
        self.assertGreaterEqual(p['diagnostic_start'],p['review_followup_end'])
        self.assertEqual(len(p['real_predictions_used']),2)


class AuthenticCacheTests(unittest.TestCase):
    """Validate exported synthetic-case live outputs; never calls an inference provider."""
    def setUp(self):
        self.cohort=load_cohort(ROOT/'results/real_model/validated_cohort.json')
        self.provider=CachedRealSignals(self.cohort,ROOT/'results/real_model/cache')
        self.case=self.cohort[0]
        self.entry=self.provider.entries[self.case['patient']['id']+':initial']

    def test_all_authentic_exports_validate(self):
        self.assertEqual(len(self.provider.entries),33)

    def test_response_tampering_rejected(self):
        e=deepcopy(self.entry);e['response']['patient_id']='changed'
        with self.assertRaisesRegex(RealModelError,'integrity'):
            validate_entry(e,self.case,self.case['decisions'][0],self.provider.manifest)

    def test_stale_backend_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            Path(path,'app').mkdir();Path(path,'app','changed.py').write_text('# different backend')
            with self.assertRaisesRegex(RealModelError,'Backend changed'):
                CachedRealSignals(self.cohort,ROOT/'results/real_model/cache',backend=path)

    def test_authentic_followup_cannot_be_used_early(self):
        cases=load_cohort(ROOT/'data/real_model/followup_cohort.json')
        provider=CachedRealSignals(cases,ROOT/'results/real_model/followup_cache')
        p=Patient(cases[0]['patient']['id'],0,None,None)
        with self.assertRaisesRegex(RealModelError,'not yet available'):
            provider.later_decision(p,'followup',1)
        self.assertFalse(provider.initial(p)['recommendation']['review_signal'])
        self.assertTrue(provider.later_decision(p,'followup',38)['recommendation']['review_signal'])


class HistoricalPinTests(unittest.TestCase):
    def test_explicit_historical_pin_accepts_only_matching_cache(self):
        cohort=load_cohort(ROOT/'results/real_model/validated_cohort.json')
        cache=ROOT/'results/real_model/cache'
        pin=json.loads((cache/'manifest.json').read_text())['pipeline_sha256']
        provider=CachedRealSignals(cohort,cache,expected_pipeline_sha256=pin)
        self.assertEqual(provider.validation['mode'],'explicit_historical_pin')
        self.assertEqual(len(provider.entries),33)
        with self.assertRaisesRegex(RealModelError,'explicitly pinned'):
            CachedRealSignals(cohort,cache,expected_pipeline_sha256='0'*64)

    def test_invalid_historical_pin_is_rejected(self):
        cohort=load_cohort(ROOT/'results/real_model/validated_cohort.json')
        with self.assertRaisesRegex(RealModelError,'SHA-256'):
            CachedRealSignals(cohort,ROOT/'results/real_model/cache',expected_pipeline_sha256='latest')
