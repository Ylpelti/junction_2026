"""Offline paired fixture replay, NOT a live-model accuracy evaluation.

Expected clinical states are the original manually authored scenario labels.
Metrics include missing predictions as errors; schema validity alone is not accuracy.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.contracts.clinical_context import RetrievedContext, SourceObservation
from app.contracts.validation import validate_evidence
from app.extraction.providers import FixtureProvider
from app.extraction.schema import ExtractionOutput
from app.extraction.service import ClinicalExtractor


def evaluate(path):
    data = json.loads(path.read_text())
    context = RetrievedContext.model_validate(data['context'])
    note = SourceObservation.model_validate(data['input_note'])
    expected = data['synthetic_response']['findings']
    output = ExtractionOutput.model_validate(data['synthetic_response'])
    sources = tuple(h.source for h in context.retrieved_observations) + (note,)
    # Validate archived offsets without silently repairing original source evidence.
    grounded = 0
    for finding in output.findings:
        try:
            validate_evidence(context.patient_id, finding.evidence, sources)
            grounded += 1
        except ValueError:
            pass
    batch = ClinicalExtractor(FixtureProvider(json.dumps(data['synthetic_response'])))(context, input_note=note)
    def state(f):
        return (f.finding_type, f.polarity, f.temporal_status)
    actual = {state(f) for f in batch.findings}
    targets = {(f['finding_type'], f['polarity'], f['temporal_status']) for f in expected}
    negated = {s for s in targets if s[1] == 'absent'}
    temporal = {s for s in targets if s[2] in ('historical', 'resolved', 'unknown')}
    return {
        'scenario_findings': len(expected), 'schema_valid': True,
        'evidence_valid_findings': grounded,
        'retained_findings': len(batch.findings),
        'factual_state_recall': len(actual & targets) / len(targets),
        'factual_state_precision': len(actual & targets) / len(actual) if actual else None,
        'negation_recall': len(actual & negated) / len(negated),
        'temporal_state_recall': len(actual & temporal) / len(temporal),
        'missing_smoking_status_preserved': batch.qcancer_predictors.smoking.status is None,
        'issues': [i.code for i in batch.issues],
        'semantic_validation': getattr(batch, "semantic_validation", None),
    }


if __name__ == '__main__':
    report = {'method': 'Manually authored fixture response replay through current validation; no model inference.',
              'clinical_validation': 'not_assessed', 'live_calls': 0,
              'original_fi_v1': evaluate(ROOT / 'examples/extraction/legacy/synthetic.fi-v1.json'),
              'english_v2': evaluate(ROOT / 'examples/extraction/synthetic.json')}
    print(json.dumps(report, indent=2))
