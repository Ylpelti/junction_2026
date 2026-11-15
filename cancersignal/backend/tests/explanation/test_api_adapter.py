from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from app.contracts.common import ComponentProvenance
from app.explanation import ExplanationEngine
from app.explanation.service import ExplanationInputError
from app.schemas.analysis import AnalysisResponse

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def example():
    return json.loads((ROOT / "app/explanation/examples/api_response.json").read_text())


class MockPlanner:
    provenance = ComponentProvenance(name="api-adapter-test", version="1", method="llm", provider="mock", model="synthetic-plan")

    def __init__(self):
        self.calls = []

    def complete(self, messages, schema):
        self.calls.append(messages)
        payload = json.loads(messages[1]["content"])
        return json.dumps({"summary_kind": payload["summary_kind"], "style": "compact", "entries": [
            {"fact_key": row["key"], "observation_ids": row["observation_ids"], "quantities": row["quantities"]}
            for row in payload["facts"]]})


def test_current_api_response_can_be_explained_without_database_or_mutation(example):
    api = AnalysisResponse.model_validate(example["analysis_response"])
    before = api.model_dump_json()
    output = ExplanationEngine().explain_api(api, input_note=example["input_note"])
    assert output.mode == "fallback" and output.input_format == "api_v1"
    assert output.analysis_id == api.id and output.patient_id == api.patient_id
    assert "Physician review required" in output.summary_en
    assert output.findings[0].finding_ids == (api.findings[0].id,)
    assert output.rule_results[0].rule_reference.trigger_rule_id == api.trigger_results[0].trigger_rule_id
    assert output.rule_results[0].observation_ids == tuple(api.trigger_results[0].evidence_observation_ids)
    assert output.rule_results[0].finding_ids == ()  # API does not provide causal finding links.
    assert output.rule_results[0].feature_ids == ()
    assert output.rule_results[0].requires_clinician_review == api.trigger_results[0].requires_clinician_review
    assert {row.kind for row in output.mathematical_outputs} == {"measurement"}
    assert {"api_v1_model_outputs_not_exposed", "api_v1_trigger_links_limited", "api_v1_provenance_limited"}.issubset({row.code for row in output.limitations})
    assert api.model_dump_json() == before


def test_missing_uncited_input_note_is_an_explicit_limitation_not_fake_evidence(example):
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert "api_v1_input_note_not_loaded" in {row.code for row in output.limitations}
    input_id = example["input_note"]["id"]
    assert all(input_id not in {str(identifier) for identifier in row.observation_ids}
               for row in (*output.findings, *output.mathematical_outputs, *output.rule_results))
    hydrated = ExplanationEngine().explain_api(example["analysis_response"], input_note=example["input_note"])
    assert "api_v1_input_note_not_loaded" not in {row.code for row in hydrated.limitations}
    assert hydrated.input_digest != output.input_digest


@pytest.mark.parametrize("status,expected", [("current", "current"), ("historical", "historical"),
    ("resolved", "resolved"), ("negated", "explicitly absent"), ("uncertain", "timing unknown")])
def test_api_finding_states_are_conservatively_preserved(example, status, expected):
    example["analysis_response"]["findings"][0].update(status=status, uncertainty=None)
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert expected in output.findings[0].text_en
    if status == "uncertain":
        assert "uncertain_finding" in {row.code for row in output.limitations}


def test_provider_plan_uses_the_same_number_and_reference_guards_for_api_input(example):
    planner = MockPlanner()
    output = ExplanationEngine(planner).explain_api(example["analysis_response"])
    assert output.mode == "llm" and output.input_format == "api_v1"
    assert planner.calls
    assert "SYNTHETIC existing API explanation" not in json.dumps(planner.calls)
    api_numbers = {str(row["numeric_value"]) for row in example["analysis_response"]["source_observations"] if row["numeric_value"] is not None}
    assert {str(number.value) for row in output.mathematical_outputs for number in row.quantities} == api_numbers


def test_ambiguous_causal_relationships_are_not_inferred_from_shared_observations(example):
    duplicate = deepcopy(example["analysis_response"]["findings"][0])
    duplicate.update(id=str(uuid4()), status="negated")
    example["analysis_response"]["findings"].append(duplicate)
    output = ExplanationEngine(MockPlanner()).explain_api(example["analysis_response"])
    assert len(output.findings) == 2
    assert output.rule_results[0].finding_ids == ()
    assert "multiple_finding_states" in {row.code for row in output.limitations}


@pytest.mark.parametrize("corruption", ["finding_patient", "finding_analysis", "source_patient", "source_missing", "quote", "offsets",
    "future_source", "missing_cutoff", "duplicate_finding", "duplicate_source", "duplicate_rule", "trigger_source",
    "snapshot_version", "snapshot_priority", "blank_rule_source", "completed_error"])
def test_invalid_or_conflicting_api_data_is_rejected_before_provider(example, corruption):
    api = example["analysis_response"]
    finding = api["findings"][0]
    rule = api["trigger_results"][0]
    if corruption == "finding_patient":
        finding["patient_id"] = str(uuid4())
    elif corruption == "finding_analysis":
        finding["analysis_run_id"] = str(uuid4())
    elif corruption == "source_patient":
        api["source_observations"][0]["patient_id"] = str(uuid4())
    elif corruption == "source_missing":
        finding["evidence"][0]["observation_id"] = str(uuid4())
    elif corruption == "quote":
        finding["evidence"][0]["source_excerpt"] = "SYNTHETIC fabricated quote"
    elif corruption == "offsets":
        finding["evidence"][0].update(start_offset=0, end_offset=999999)
    elif corruption == "future_source":
        api["source_observations"][0]["recorded_at"] = "2099-01-01T00:00:00Z"
    elif corruption == "missing_cutoff":
        api["provenance"]["cutoff"] = None
    elif corruption == "duplicate_finding":
        api["findings"].append(deepcopy(finding))
    elif corruption == "duplicate_source":
        api["source_observations"].append(deepcopy(api["source_observations"][0]))
    elif corruption == "duplicate_rule":
        api["trigger_results"].append(deepcopy(rule))
    elif corruption == "trigger_source":
        rule["evidence_observation_ids"] = [str(uuid4())]
    elif corruption in ("snapshot_version", "snapshot_priority"):
        api["provenance"]["rule_snapshots"] = {rule["trigger_rule_id"]: {
            "name": rule["rule_name"], "version": "different-version" if corruption == "snapshot_version" else rule["rule_version"],
            "source": rule["rule_source"], "source_section": rule["rule_source_section"],
            "recommended_action": "SYNTHETIC existing action", "demonstration_only": True,
            "priority": "urgent" if corruption == "snapshot_priority" else rule["priority"]}}
    elif corruption == "blank_rule_source":
        rule["rule_source"] = ""
    else:
        api["provenance"]["error_code"] = "SYNTHETIC upstream failure"
    planner = MockPlanner()
    with pytest.raises(ExplanationInputError):
        ExplanationEngine(planner).explain_api(api)
    assert not planner.calls


@pytest.mark.parametrize("field,value", [("id", str(uuid4())), ("patient_id", str(uuid4())),
    ("observed_at", "2099-01-01T00:00:00Z"), ("observation_type", "laboratory")])
def test_hydrated_note_must_match_original_analysis(example, field, value):
    example["input_note"][field] = value
    with pytest.raises(ExplanationInputError):
        ExplanationEngine().explain_api(example["analysis_response"], input_note=example["input_note"])


@pytest.mark.parametrize("status", ["pending", "running", "failed"])
def test_noncompleted_api_runs_do_not_call_provider_or_publish_findings(example, status):
    example["analysis_response"]["status"] = status
    if status == "failed":
        example["analysis_response"]["provenance"]["error_code"] = "synthetic_failure"
    planner = MockPlanner()
    output = ExplanationEngine(planner).explain_api(example["analysis_response"])
    assert output.mode == "unavailable" and not output.findings and not output.rule_results
    assert not planner.calls


def test_api_does_not_gain_invented_model_outputs_from_descriptions(example):
    example["analysis_response"]["findings"][0]["description"] = "SYNTHETIC invented risk score 999999, risk=0.95."
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert "999999" not in output.model_dump_json()
    assert not any(row.kind in {"feature", "prediction"} for row in output.mathematical_outputs)


@pytest.mark.parametrize("code,label", [("anaemia", "Anaemia finding"),
    ("iron_deficiency_anaemia", "Iron-deficiency anaemia finding"), ("fit_result", "FIT result")])
def test_existing_backend_lab_finding_labels_are_readable_in_english(example, code, label):
    example["analysis_response"]["findings"][0]["finding_type"] = code
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert label in output.findings[0].text_en
    assert "unmapped_finding" not in {row.code for row in output.limitations}


def test_api_fixture_cli_runs_offline():
    result = subprocess.run([sys.executable, "-m", "app.explanation", "--api-v1", "--example",
                             "app/explanation/examples/api_response.json"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["input_format"] == "api_v1"
