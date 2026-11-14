from copy import deepcopy
import json
from pathlib import Path
import unittest
from cancersignal_sim.engine import simulate, review_priority, validate
from cancersignal_sim.inputs import Patient
from cancersignal_sim.study import kpis
ROOT=Path(__file__).resolve().parents[1]

class PriorityTests(unittest.TestCase):
    def test_urgent_review_ranks_first_without_label_access(self):
        self.assertLess(review_priority('review','urgent'),review_priority('review','review'))
        self.assertLess(review_priority('review','review'),review_priority('gp'))
        self.assertEqual(review_priority('gp','urgent'),0)
        self.assertEqual(review_priority('optimization_review','urgent'),0)
        self.assertEqual(review_priority('review_followup','urgent'),-2)

    def test_review_overtakes_waiting_visit_but_never_interrupts_active_visit(self):
        c=json.loads((ROOT/'config/demo.json').read_text())
        c.update(duration=100,warmup=0)
        c['capacities']['gp']=1
        c['service']['nurse']={'mean':0,'cv':0}
        c['service']['gp']={'mean':1,'cv':0}
        c['service']['review']={'mean':.5,'cv':0}
        c['signal'].update(tpr=1,fpr=1,review_probability=1,processing_delay=0,escalation_probability=1)
        c['routing'].update(initial_relevant=0,initial_other=1)
        patients=[Patient('a_alert',0,True,'test'),Patient('b_active',0,False,'test'),Patient('c_waiting',0,False,'test')]
        runs={}
        for policy in ['fifo','priority']:
            c['review_queue']=policy
            runs[policy]={p['patient_id']:p for p in simulate(c,patients,1,model='C')['patients']}
        p=runs['priority'];f=runs['fifo']
        self.assertEqual(p['b_active']['gp_start'],1)
        self.assertEqual(p['b_active']['gp_end'],2)
        self.assertEqual(p['a_alert']['review_start'],2)
        self.assertEqual(p['c_waiting']['gp_start'],2.5)
        self.assertEqual(f['a_alert']['review_start'],3)
        self.assertGreater(p['c_waiting']['gp_start'],f['c_waiting']['gp_start'])

    def test_unknown_queue_rejected(self):
        c=json.loads((ROOT/'config/demo.json').read_text());c['review_queue']='magic'
        with self.assertRaisesRegex(ValueError,'review_queue'):validate(c)

    def test_capped_p90_and_noncompletion_include_uninvestigated(self):
        c=json.loads((ROOT/'config/demo.json').read_text());c.update(duration=100,warmup=0)
        rows=[{'patient_id':str(i),'arrival':0,'relevant':True,'signal':None,'complete':False,'repeat_avoided':False,'selective_review_skipped':False,**({'diagnostic_end':7} if i<8 else {})} for i in range(10)]
        # Use a real run container so resource accounting has valid state data.
        run=simulate(c,[],1,model='A');run['patients']=rows
        m=kpis(run,c)
        self.assertEqual(m['cohort.relevant.completion_60_n'],8)
        self.assertEqual(m['cohort.relevant.completion_p90'],7)
        self.assertEqual(m['cohort.relevant.capped_completion_60_p90'],60)
        self.assertEqual(m['cohort.relevant.without_completion_30_rate'],.2)
