"""Regression of the real backend handoff with explicit unit-test-only content.

Run with backend dependencies and PYTHONPATH pointing at the intended backend.
This fixture is never used for live inference or benchmark metrics.
"""
from datetime import datetime,timezone
from uuid import uuid4
import unittest
from app.extraction.service import ClinicalExtractor
from app.extraction.providers import FixtureProvider
from app.extraction.schema import ExtractionOutput
from app.contracts.clinical_context import SourceObservation
from app.rag.context import RetrievedContext
from app.services.llm_extraction import to_contract_context
from app.schemas.records import ObservationRead


class BackendHandoffTest(unittest.TestCase):
    def test_qcancer_source_reference_validated_without_name_error(self):
        pid=uuid4();nid=uuid4();at=datetime(2026,11,14,9,tzinfo=timezone.utc)
        note=ObservationRead(id=nid,patient_id=pid,observation_type='clinical_note',text='Ei verta ulosteessa.',observed_at=at,recorded_at=at)
        output=ExtractionOutput.model_validate({'findings':[],'missing_information':[],'qcancer_predictors':{'binary_factors':[{'factor':'new_rectalbleed','value':False,'evidence':[{'observation_id':str(nid),'source_excerpt':'Ei verta ulosteessa.'}]}]}})
        extractor=ClinicalExtractor(FixtureProvider(output.model_dump_json()))
        context=to_contract_context(RetrievedContext(patient_id=pid,cutoff=at,observations=[],ranked_observation_ids=[]),note.text)
        result=extractor(context,input_note=SourceObservation.model_validate(note.model_dump()))
        self.assertNotEqual(result.status,'failed')
        self.assertFalse(result.qcancer_predictors.binary_factors[0].value)


if __name__=='__main__':unittest.main()
