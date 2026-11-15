"""Manually labeled assertion cases, not an LLM accuracy benchmark."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from app.contracts.clinical_context import SourceObservation
from app.contracts.common import ComponentProvenance
from app.contracts.findings import ClinicalFinding
from app.contracts.qcancer import QCancerPredictors
from app.extraction.semantics import validate_semantics

CASES = [
 ('Patient reports rectal bleeding.','rectal_bleeding','present','current',False,True),
 ('Patient denies rectal bleeding.','rectal_bleeding','present','current',False,False),
 ('Patient denies rectal bleeding.','rectal_bleeding','absent','current',False,True),
 ('No blood in stool.','rectal_bleeding','absent','current',True,False),
 ('No blood in stool.','rectal_bleeding','absent','historical',True,True),
 ('Patient reports rectal bleeding.','rectal_bleeding','present','current',True,False),
 ('Patient reports rectal bleeding.','rectal_bleeding','present','historical',True,True),
 ('Rectal bleeding has resolved.','rectal_bleeding','present','current',False,False),
 ('Rectal bleeding has resolved.','rectal_bleeding','present','resolved',False,True),
 ('Possible rectal bleeding.','rectal_bleeding','present','current',False,False),
 ('Possible rectal bleeding.','rectal_bleeding','uncertain','unknown',False,True),
 ('Mother reports rectal bleeding.','rectal_bleeding','present','current',False,False),
 ('If rectal bleeding occurs, call.','rectal_bleeding','present','current',False,False),
 ('Patient reports abdominal pain.','abdominal_pain','present','current',False,True),
 ('No abdominal pain.','abdominal_pain','absent','current',False,True),
 ('Patient reports weight loss.','weight_loss','present','current',False,True),
 ('Patient denies weight loss.','weight_loss','present','current',False,False),
 ('Patient has abdominal mass.','abdominal_mass','present','current',False,True),
 ('Patient has rectal mass.','rectal_mass','present','current',False,True),
 ('Patient reports change in bowel habit.','change_in_bowel_habit','present','current',False,True),
 ('Colonoscopy completed.','investigation_planned','present','current',False,False),
 ('Colonoscopy completed.','investigation_completed','present','current',False,True),
 ('Colonoscopy planned.','investigation_completed','present','current',False,False),
 ('Colonoscopy referred.','investigation_referred','present','current',False,True),
 ('Colonoscopy scheduled.','investigation_scheduled','present','current',False,True),
 ('Colonoscopy cancelled.','investigation_cancelled','present','current',False,True),
 ('No colonoscopy result available.','investigation_cancelled','present','current',False,False),
 ('Patient reports rectal bleeding. Patient denies rectal bleeding.','rectal_bleeding','present','current',False,False),
]

def source(text):
 return SourceObservation(id=uuid4(),patient_id=uuid4(),encounter_id=None,observation_type='clinical_note',
  code=None,text=text,numeric_value=None,unit=None,status=None,
  observed_at=datetime(2026,11,12,tzinfo=timezone.utc),recorded_at=datetime(2026,11,12,tzinfo=timezone.utc))

@pytest.mark.parametrize('text,kind,polarity,timing,old,keep',CASES)
def test_labeled_case(text,kind,polarity,timing,old,keep):
 s=source(text)
 f=ClinicalFinding(patient_id=s.patient_id,finding_type=kind,description='Unchecked prose',polarity=polarity,
  temporal_status=timing,uncertainty='Uncertain' if polarity=='uncertain' else None,
  evidence=({'observation_id':s.id,'source_excerpt':text},),provenance=ComponentProvenance(name='test',version='1',method='manual'))
 retained,_,issues,diagnostics=validate_semantics((f,),QCancerPredictors(),(s,),uuid4() if old else s.id)
 assert bool(retained)==keep
 assert any(issue.code == 'semantic_rejection' for issue in issues) != keep
 assert diagnostics['coverage_status'] == 'incomplete'
 assert diagnostics['retained_findings']==int(keep)

@pytest.mark.parametrize('text,status,old,keep',[
 ('Patient does not smoke.','current',False,False),
 ('Patient does not currently smoke.','never',False,False),
 ('Patient has never smoked.','never',False,True),
 ('Patient is a former smoker.','former',False,True),
 ('Patient currently smokes.','current',False,True),
 ('Patient currently smokes.','current',True,False),
])
def test_smoking(text,status,old,keep):
 s=source(text)
 p=QCancerPredictors(smoking={'status':status,'evidence':[{'observation_id':s.id,'source_excerpt':text}]})
 _,result,_,_=validate_semantics((),p,(s,),uuid4() if old else s.id)
 assert (result.smoking.status is not None)==keep


def test_quote_cannot_drop_negation():
 s=source('Patient denies rectal bleeding.')
 f=ClinicalFinding(patient_id=s.patient_id,finding_type='rectal_bleeding',description='x',polarity='present',temporal_status='current',
  evidence=({'observation_id':s.id,'source_excerpt':'rectal bleeding'},),provenance=ComponentProvenance(name='test',version='1',method='manual'))
 assert not validate_semantics((f,),QCancerPredictors(),(s,),s.id)[0]

@pytest.mark.parametrize('text',[
 'Patient currently smokes. Patient does not currently smoke.',
 'Patient currently smokes. Patient is a former smoker.',
])
def test_conflicting_smoking_cannot_cherry_pick(text):
 s=source(text)
 p=QCancerPredictors(smoking={'status':'current','evidence':[{'observation_id':s.id,'source_excerpt':'Patient currently smokes.'}]})
 assert validate_semantics((),p,(s,),s.id)[1].smoking.status is None


def test_exact_current_numeric_value_retained():
 s=source('Weight 72 kg.')
 p=QCancerPredictors(weight_kg={'value':72,'evidence':[{'observation_id':s.id,'source_excerpt':s.text}]})
 assert validate_semantics((),p,(s,),s.id)[1].weight_kg.value==72
 assert validate_semantics((),p,(s,),uuid4())[1].weight_kg.value is None


def test_compact_adapter_constructs_evidence_and_rejects_unknown_source():
 import json
 from app.extraction.compact import CompactProvider
 from app.extraction.providers import FixtureProvider, ProviderError
 s=source('Patient reports rectal bleeding.')
 payload={'historical_observations':[],'current_note':s.model_dump(mode='json'),'as_of':s.observed_at.isoformat(),'history_coverage':{'status':'complete'}}
 raw={'facts':[{'kind':'rectal_bleeding','polarity':'present','timing':'current',
   'evidence':[{'source':'S1','quote':s.text}],'uncertainty':None}],'missing_information':[]}
 adapter=CompactProvider(FixtureProvider(json.dumps(raw)))
 result=json.loads(adapter.complete([{'content':json.dumps(payload)}],{}))
 ref=result['findings'][0]['evidence'][0]
 assert ref['observation_id']==str(s.id)
 assert (ref['start_offset'],ref['end_offset'])==(0,len(s.text))
 assert result['qcancer_predictors']['smoking']['status'] is None
 raw['facts'][0]['evidence'][0]['source']='S99'
 rejected=json.loads(CompactProvider(FixtureProvider(json.dumps(raw))).complete([{'content':json.dumps(payload)}],{}))
 assert not rejected['findings']
 assert rejected['missing_information'][0]['code']=='compact_evidence_rejected'


def test_compact_partial_invalid_quote_preserves_valid_fact():
 import json
 from app.extraction.compact import CompactProvider
 from app.extraction.providers import FixtureProvider
 s=source('Patient reports rectal bleeding.')
 payload={'historical_observations':[],'current_note':s.model_dump(mode='json'),'as_of':s.observed_at.isoformat(),'history_coverage':{'status':'complete'}}
 def fact(quote):return {'kind':'rectal_bleeding','polarity':'present','timing':'current','evidence':[{'source':'S1','quote':quote}],'uncertainty':None}
 raw={'facts':[fact(s.text),fact('Invented source text')],'missing_information':[]}
 result=json.loads(CompactProvider(FixtureProvider(json.dumps(raw))).complete([{'content':json.dumps(payload)}],{}))
 assert len(result['findings'])==1
 assert result['missing_information'][0]['code']=='compact_evidence_rejected'


def test_compact_multiple_quotes_preserve_original_source():
 import json
 from app.extraction.compact import CompactProvider
 from app.extraction.providers import FixtureProvider
 s=source('Patient reports rectal bleeding. Patient denies rectal bleeding.')
 payload={'historical_observations':[],'current_note':s.model_dump(mode='json'),'as_of':s.observed_at.isoformat(),'history_coverage':{'status':'complete'}}
 raw={'facts':[{'kind':'rectal_bleeding','polarity':'uncertain','timing':'current',
   'evidence':[{'source':'S1','quote':'Patient reports rectal bleeding.'},{'source':'S1','quote':'Patient denies rectal bleeding.'}],
   'uncertainty':'Conflicting assertions'}],'missing_information':[]}
 result=json.loads(CompactProvider(FixtureProvider(json.dumps(raw))).complete([{'content':json.dumps(payload)}],{}))
 assert len(result['findings'][0]['evidence'])==1
 assert result['findings'][0]['evidence'][0]['source_excerpt']==s.text

@pytest.mark.parametrize('polarity', ['present', 'absent'])
def test_resolved_bleeding_keeps_equivalent_polarities_without_current_escalation(polarity):
 from app.extraction.compatibility import legacy_findings
 from app.contracts.stages import FindingBatch
 s=source('Rectal bleeding has resolved.')
 provenance=ComponentProvenance(name='test',version='1',method='manual')
 f=ClinicalFinding(patient_id=s.patient_id,finding_type='rectal_bleeding',description='Resolved',polarity=polarity,
  temporal_status='resolved',evidence=({'observation_id':s.id,'source_excerpt':s.text},),provenance=provenance)
 kept,_,issues,diagnostics=validate_semantics((f,),QCancerPredictors(),(s,),s.id)
 assert len(kept)==1 and kept[0].polarity==polarity
 batch=FindingBatch(patient_id=s.patient_id,as_of=s.observed_at,status='partial',provenance=provenance,
  findings=kept,issues=issues,semantic_validation=diagnostics)
 assert legacy_findings(batch)[0].status in ('resolved','uncertain')


def test_missing_result_supports_uncertainty_but_not_noncompletion():
 s=source('No colonoscopy result available.')
 provenance=ComponentProvenance(name='test',version='1',method='manual')
 base=dict(patient_id=s.patient_id,description='Unknown',evidence=({'observation_id':s.id,'source_excerpt':s.text},),provenance=provenance)
 unknown=ClinicalFinding(**base,finding_type='investigation_status_unknown',polarity='uncertain',temporal_status='unknown',uncertainty='Result absent')
 cancelled=ClinicalFinding(**base,finding_type='investigation_cancelled',polarity='present',temporal_status='current')
 kept,_,_,_=validate_semantics((unknown,cancelled),QCancerPredictors(),(s,),s.id)
 assert [f.finding_type for f in kept]==['investigation_status_unknown']
