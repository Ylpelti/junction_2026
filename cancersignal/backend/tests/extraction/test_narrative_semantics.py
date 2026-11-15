"""Offline source-grounding regression; no external inference."""
import pytest
from tests.extraction.test_semantics import test_labeled_case as check_case

@pytest.mark.parametrize('text,kind,polarity,timing,old,keep', [
 ('Bowel habits vary, with occasional abdominal cramping.','abdominal_pain','present','current',False,True),
 ('Bowel habits vary, with occasional abdominal cramping.','change_in_bowel_habit','present','current',False,True),
 ('Intermittent lower abdominal pain and loose stools persist.','abdominal_pain','present','historical',True,True),
 ('Intermittent lower abdominal pain and loose stools persist.','change_in_bowel_habit','present','historical',True,True),
 ('Previous abdominal pain and visible blood in stool have resolved.','rectal_bleeding','absent','resolved',True,True),
 ('Colonoscopy completed to the caecum with good visibility.','investigation_completed','present','historical',True,True),
 ('Colonoscopy completed: good visibility, examination to the caecum.','investigation_completed','present','historical',True,True),
 ('Completion of the previous colonoscopy referral is uncertain.','investigation_status_unknown','uncertain','unknown',True,True),
 ('No unusual fatigue, abdominal pain or change in bowel habits.','abdominal_pain','absent','historical',True,True),
 ('No unusual fatigue, abdominal pain or change in bowel habits.','change_in_bowel_habit','absent','historical',True,True),
 ('Abdominal symptoms continue intermittently.','change_in_bowel_habit','present','current',False,False),
 ('No abdominal symptoms or bleeding.','change_in_bowel_habit','absent','current',False,False),
 ('Mother reports intermittent lower abdominal pain and loose stools persist.','abdominal_pain','present','current',False,False),
 ('If bowel habits vary, with occasional abdominal cramping, call.','abdominal_pain','present','current',False,False),
 ('No intermittent lower abdominal pain and loose stools persist.','abdominal_pain','present','current',False,False),
 ('Colonoscopy planned, not completed to the caecum with good visibility.','investigation_completed','present','current',False,False),
 ('Colonoscopy completed to the caecum with good visibility.','investigation_completed','present','current',True,False),
 ('Completion of the previous colonoscopy referral is uncertain.','investigation_completed','present','historical',True,False),
 ('Bowel habits vary, with occasional abdominal cramping. No abdominal pain.','abdominal_pain','present','current',False,False),
])
def test_narrative_grounding(text,kind,polarity,timing,old,keep):
 check_case(text,kind,polarity,timing,old,keep)


def test_invalid_wire_polarity_is_quarantined_without_repair():
 import json
 from pathlib import Path
 from app.contracts.clinical_context import RetrievedContext, SourceObservation
 from app.extraction.providers import FixtureProvider
 from app.extraction.compact import CompactProvider
 from app.extraction.service import ClinicalExtractor
 directory=Path(__file__).resolve().parents[3]/'docs/evaluation/live-narrative-english-4/heikkinen'
 snapshot=json.loads((directory/'input.json').read_text())
 envelope=json.loads((directory/'provider.raw.json').read_text())
 raw=envelope['choices'][0]['message']['content']
 assert json.loads(raw)['facts'][8]['polarity']=='resolved'
 result=ClinicalExtractor(CompactProvider(FixtureProvider(raw)))(RetrievedContext.model_validate(snapshot['context']),input_note=SourceObservation.model_validate(snapshot['note']))
 assert result.status=='partial'
 assert result.semantic_validation['coverage_status']=='incomplete'
 assert any(f.finding_type=='investigation_completed' for f in result.findings)
 assert not any(f.temporal_status=='resolved' for f in result.findings)
 assert sum(g.code=='compact_fact_rejected' for g in result.missing_information)==2
