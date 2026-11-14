from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from cancersignal_sim.engine import simulate, validate
from cancersignal_sim.inputs import Patient, generate
from cancersignal_sim.study import kpis, patient_comparison, estimate, aggregate
ROOT=Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((ROOT/'config/workflows.json').read_text())
        self.c.update(duration=100,warmup=0,arrival_rate=1,seeds=[1,2])
        self.c['service']['nurse']={'mean':0,'cv':0}
        self.c['signal'].update(tpr=1,fpr=1,review_probability=1,escalation_probability=1,gp_time_saved=0)
        self.c['workflow'].update(repeat_probability=0,selective_review_probability=1)
        self.p=[Patient('p',0,True,'test')]

    def run_model(self,model): return simulate(self.c,self.p,1,model=model)

    def test_initial_investigation_not_blocked(self):
        self.c['routing']['initial_relevant']=1
        a,b,c,d=[self.run_model(m)['patients'][0] for m in 'ABCD']
        self.assertGreater(b['diagnostic_start'],a['diagnostic_start'])
        for row in (c,d):
            self.assertNotIn('review_start',row)
            self.assertEqual(row['diagnostic_start'],a['diagnostic_start'])
            self.assertEqual(row['first_indication'],a['first_indication'])

    def test_reviews_charge_shared_gp(self):
        self.c['routing']['initial_relevant']=0
        self.c['service']['review']={'mean':2,'cv':0}
        for model in 'BCD':
            run=self.run_model(model); p=run['patients'][0]
            self.assertAlmostEqual(p['review_end']-p['review_start'],2)
            self.assertTrue(any(s['resource']=='gp' and s['busy'] for s in run['resource_states'] if s['time']==p['review_start']))

    def test_monitor_discharge_and_change(self):
        self.c['routing']['initial_relevant']=0
        self.c['workflow'].update(followup_probability=0,monitor_probability=1,change_probability_relevant=0)
        p=self.run_model('A')['patients'][0]
        self.assertEqual(p['actual_plan'],'monitor')
        self.assertNotIn('gp_followup_start',p)
        self.assertNotIn('diagnostic_start',p)
        self.c['workflow'].update(monitor_probability=0,change_probability_relevant=1,change_investigation_relevant=1)
        p=self.run_model('A')['patients'][0]
        self.assertEqual(p['actual_plan'],'discharge')
        self.assertIn('gp_change_start',p)
        self.assertGreaterEqual(p['diagnostic_start'],p['gp_change_end'])

    def test_retain_or_request_followup(self):
        self.c['routing']['initial_relevant']=0
        self.c['signal']['escalation_probability']=0
        self.c['workflow'].update(followup_probability=0,monitor_probability=1,review_followup_probability=1)
        p=self.run_model('C')['patients'][0]
        self.assertEqual(p['review_action'],'followup')
        self.assertIn('gp_followup_start',p)

    def test_duplicate_suppression_is_clinician_work_and_first_test_preserved(self):
        self.c['routing']['initial_relevant']=1
        self.c['workflow'].update(repeat_probability=1,avoidable_repeat_rate=1,duplicate_flag_tpr=1,clinician_cancel_probability=1)
        self.c['service']['optimization_review']={'mean':.5,'cv':0}
        a=self.run_model('A');d=self.run_model('D');p=d['patients'][0]
        self.assertEqual(p['diagnostic_start'],a['patients'][0]['diagnostic_start'])
        self.assertIn('diagnostic_repeat_end',a['patients'][0])
        self.assertNotIn('diagnostic_repeat_start',p)
        self.assertTrue(p['repeat_avoided'])
        self.assertAlmostEqual(p['optimization_review_end']-p['optimization_review_start'],.5)
        self.assertEqual(kpis(d,self.c)['cohort.correctly_avoided_repeat_n'],1)

    def test_unsafe_repeat_cancellation_counted(self):
        self.c['routing']['initial_relevant']=1
        self.c['workflow'].update(repeat_probability=1,avoidable_repeat_rate=0,duplicate_flag_fpr=1,clinician_cancel_probability=1)
        m=kpis(self.run_model('D'),self.c)
        self.assertEqual(m['cohort.relevant_necessary_repeat_cancelled_n'],1)
        self.assertEqual(m['cohort.correctly_avoided_repeat_n'],0)

    def test_no_repeat_cancel_without_observable_flag(self):
        self.c['routing']['initial_relevant']=1
        self.c['workflow'].update(repeat_probability=1,duplicate_flag_fpr=0,duplicate_flag_tpr=0)
        p=self.run_model('D')['patients'][0]
        self.assertIn('diagnostic_repeat_end',p)
        self.assertNotIn('optimization_review_start',p)

    def test_low_signal_cannot_cancel_indicated_first_test(self):
        self.c['signal']['tpr']=0
        self.c['routing']['initial_relevant']=1
        p=self.run_model('D')['patients'][0]
        self.assertIn('diagnostic_end',p)

    def test_reference_plans_paired_and_no_duplicate_service(self):
        pp=generate(self.c,1)
        runs=[simulate(self.c,pp,1,model=m) for m in 'ABCD']
        keys=['baseline_initial_investigation','baseline_followup_investigation','baseline_plan','repeat_planned','repeat_duplicate_evidence']
        for run in runs:
            self.assertEqual(run['capacities'],runs[0]['capacities'])
            self.assertEqual([[p[k] for k in keys] for p in run['patients']],[[p[k] for k in keys] for p in runs[0]['patients']])
            starts=[(e['patient_id'],e['stage']) for e in run['events'] if e['event']=='service_start']
            self.assertEqual(len(starts),len(set(starts)))

    def test_cohort_window_completion_and_capping(self):
        self.c['service']['diagnostic']={'mean':70,'cv':0}
        self.c['routing']['initial_relevant']=1
        self.p.append(Patient('late',50,True,'test'))
        run=self.run_model('A');m=kpis(run,self.c)
        self.assertEqual(m['cohort.n'],1)
        self.assertEqual(m['cohort.relevant.completion_60_rate'],0)
        self.assertEqual(m['cohort.relevant.capped_completion_60_days'],60)
        self.assertEqual(m['cohort.relevant.investigation_observed_n'],1)

    def test_pair_ci_and_zero_baseline_relative(self):
        e=estimate([1,2,3])
        self.assertEqual(e['mean'],2)
        self.assertAlmostEqual(e['ci95_high'],2+4.3027/(3**.5),places=5)
        records=[{'model':m,'seed':s,'metrics':{'x':0 if m=='A' else 1}} for m in 'ABCD' for s in (1,2,3)]
        b=next(x for x in aggregate(records) if x['model']=='B')
        self.assertEqual(b['difference_mean'],1)
        self.assertIsNone(b['relative_percent_mean'])

    def test_invalid_followup_probabilities(self):
        self.c['workflow'].update(followup_probability=.8,monitor_probability=.5)
        with self.assertRaisesRegex(ValueError,'must not exceed'): validate(self.c)

    def test_relevance_not_used_by_review_policy(self):
        # Hold synthetic observable decisions and signal fixed; changing the
        # reference label must not change the intervention routing decisions.
        self.c['routing'].update(initial_relevant=0,initial_other=0,followup_relevant=0,followup_other=0)
        self.c['workflow'].update(change_probability_relevant=0,change_probability_other=0)
        class FixedSignal:
            def signal(self,p,seed): return True
        rows=[]
        for relevant in (True,False):
            p=Patient('same',0,relevant,'test')
            rows.append(simulate(self.c,[p],1,model='D',signals=FixedSignal())['patients'][0])
        for key in ('review_start','review_end','escalated','diagnostic_start'):
            self.assertEqual(rows[0][key],rows[1][key])

    def test_original_config_event_trace_regression(self):
        c=json.loads((ROOT/'config/demo_fifo_original.json').read_text())
        fixture=json.loads((ROOT/'tests/legacy_traces.json').read_text())
        pp=generate(c,fixture['seed'])
        for model,scenario in [('A','baseline'),('B','assisted')]:
            run=simulate(c,pp,fixture['seed'],model=model)
            digest=hashlib.sha256(json.dumps(run['events'],sort_keys=True).encode()).hexdigest()
            self.assertEqual(digest,fixture['event_hashes'][scenario])

    def test_all_resource_service_time_is_accounted(self):
        from cancersignal_sim.study import spent, GP_STAGES
        self.c['workflow'].update(repeat_probability=1,duplicate_flag_tpr=1,duplicate_flag_fpr=1)
        pp=generate(self.c,1)
        for model in 'ABCD':
            run=simulate(self.c,pp,1,model=model)
            for resource,stages in [('gp',GP_STAGES),('nurse',('nurse',)),('diagnostic',('diagnostic','diagnostic_repeat')),('specialist',('specialist',))]:
                states=[s for s in run['resource_states'] if s['resource']==resource]
                area=sum(a['busy']*(b['time']-a['time']) for a,b in zip(states,states[1:]))
                work=sum(spent(p,stage,self.c['duration']) for p in run['patients'] for stage in stages)
                self.assertAlmostEqual(area,work,places=8)

    def test_signal_metrics_do_not_use_future_information(self):
        self.c['service']['gp']={'mean':70,'cv':0}
        self.c['signal']['tpr']=0
        run=self.run_model('C')
        self.assertGreater(run['patients'][0]['signal_time'],60)
        m=kpis(run,self.c)
        self.assertEqual(m['cohort.false_negative_n'],0)
        self.assertEqual(m['cohort.signal_unavailable_n'],1)

    def test_additional_review_can_still_delay_other_indicated_patients(self):
        # Nonblocking removes the focal patient's approval gate, not shared-capacity spillover.
        self.c['capacities']['gp']=1
        self.c['service']['gp']={'mean':1,'cv':0}
        self.c['service']['review']={'mean':5,'cv':0}
        self.c['routing'].update(initial_relevant=1,initial_other=0)
        self.c['signal']['processing_delay']=0
        self.p=[Patient('other',0,False,'test'),Patient('indicated',2,True,'test')]
        a=self.run_model('A')['patients'][1];c=self.run_model('C')['patients'][1]
        self.assertNotIn('review_start',c)
        self.assertGreater(c['gp_start'],a['gp_start'])
        self.assertAlmostEqual(c['diagnostic_start']-c['gp_end'],a['diagnostic_start']-a['gp_end'])
