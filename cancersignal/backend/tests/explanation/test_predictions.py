from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import Field

from app.contracts.analysis import AnalysisResult
from app.contracts.predictions import ModelPrediction
from app.explanation import ExplanationEngine
from app.explanation.service import ExplanationInputError
from app.schemas.analysis import AnalysisProvenance, AnalysisResponse

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def example():
    return json.loads((ROOT / "app/explanation/examples/qcancer_api_response.json").read_text())


def prediction_statement(output):
    return next(row for row in output.mathematical_outputs if row.kind == "prediction")


def test_published_qcancer_percentage_fields_are_copied_without_conversion(example):
    output = ExplanationEngine().explain_api(example["analysis_response"])
    statement = prediction_statement(output)
    assert {row.slot: (row.value, row.unit) for row in statement.quantities} == {
        "colorectal_cancer_risk_percent": (Decimal("2.25"), "%"),
        "any_cancer_risk_percent": (Decimal("7.5"), "%"), "horizon_years": (Decimal("2"), "years")}
    assert "2.25 %" in statement.text_en and "7.5 %" in statement.text_en
    assert "not an established disease" in statement.text_en
    assert "qcancer_finland_limitation" in {row.code for row in output.limitations}
    assert "api_v1_model_outputs_not_exposed" not in {row.code for row in output.limitations}
    assert statement.source_notice == example["analysis_response"]["predictions"][0]["value"]["source_notice"]


def test_original_qcancer_notice_is_preserved_without_entering_the_llm_prompt(example):
    class Planner:
        from app.contracts.common import ComponentProvenance
        provenance = ComponentProvenance(name="notice-test", version="1", method="llm", provider="mock", model="synthetic")
        def complete(self, messages, schema):
            self.messages = messages
            payload = json.loads(messages[1]["content"])
            return json.dumps({"summary_kind": payload["summary_kind"], "style": "compact", "entries": [
                {"fact_key": row["key"], "observation_ids": row["observation_ids"], "quantities": row["quantities"]}
                for row in payload["facts"]]})
    planner = Planner()
    output = ExplanationEngine(planner).explain_api(example["analysis_response"])
    notice = example["analysis_response"]["predictions"][0]["value"]["source_notice"]
    assert output.mode == "llm" and prediction_statement(output).source_notice == notice
    assert notice not in json.dumps(planner.messages)


def test_missing_qcancer_notice_is_not_fabricated(example):
    for prediction in (example["analysis_response"]["predictions"][0], example["analysis_response"]["provenance"]["predictions"][0]):
        prediction["value"].pop("source_notice")
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert prediction_statement(output).source_notice is None
    assert "qcancer_source_notice_missing" in {row.code for row in output.limitations}


@pytest.mark.parametrize("status", ["insufficient_data", "invalid_input", "unsupported_input"])
def test_uncalculated_model_statuses_never_show_a_numeric_risk(example, status):
    for prediction in (example["analysis_response"]["predictions"][0], example["analysis_response"]["provenance"]["predictions"][0]):
        prediction["value"].update(status=status, any_cancer_risk_percent=None, colorectal_cancer_risk_percent=None,
            missing_inputs=["bmi"] if status == "insufficient_data" else [], invalid_inputs=[] if status == "insufficient_data" else ["synthetic input problem"])
    output = ExplanationEngine().explain_api(example["analysis_response"])
    statement = prediction_statement(output)
    assert not statement.quantities and "not calculated" in statement.text_en
    assert "qcancer_estimate_unavailable" in {row.code for row in output.limitations}
    # Failure to calculate a prediction does not change the independent rule flag.
    assert "Physician review required" in output.summary_en


@pytest.mark.parametrize("field,value", [("colorectal_cancer_risk_percent", "NaN"),
    ("any_cancer_risk_percent", 101), ("colorectal_cancer_risk_percent", -1),
    ("horizon_years", "invented horizon"), ("colorectal_cancer_risk_percent", None)])
def test_unverifiable_qcancer_numbers_are_omitted(example, field, value):
    for prediction in (example["analysis_response"]["predictions"][0], example["analysis_response"]["provenance"]["predictions"][0]):
        prediction["value"][field] = value
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert not prediction_statement(output).quantities
    assert "qcancer_invalid_display_payload" in {row.code for row in output.limitations}


def test_body_and_persisted_prediction_snapshots_must_agree(example):
    example["analysis_response"]["provenance"]["predictions"][0]["value"]["colorectal_cancer_risk_percent"] = 99
    with pytest.raises(ExplanationInputError):
        ExplanationEngine().explain_api(example["analysis_response"])


@pytest.mark.parametrize("field", ["patient_id", "as_of", "evidence_observation_ids"])
def test_prediction_patient_time_and_evidence_are_checked(example, field):
    value = {"patient_id": "11111111-1111-4111-8111-111111111111", "as_of": "2099-01-01T00:00:00Z",
             "evidence_observation_ids": ["11111111-1111-4111-8111-111111111111"]}[field]
    for prediction in (example["analysis_response"]["predictions"][0], example["analysis_response"]["provenance"]["predictions"][0]):
        prediction[field] = value
    with pytest.raises(ExplanationInputError):
        ExplanationEngine().explain_api(example["analysis_response"])


def test_prediction_only_and_saved_metadata_only_inputs_are_supported(example):
    top_only = deepcopy(example["analysis_response"])
    top_only["provenance"].pop("predictions")
    stored_only = deepcopy(example["analysis_response"])
    stored_only.pop("predictions")
    assert prediction_statement(ExplanationEngine().explain_api(top_only)).quantities
    assert prediction_statement(ExplanationEngine().explain_api(stored_only)).quantities


def test_unset_prediction_defaults_are_not_mistaken_for_conflicting_snapshots(example):
    # These additive fields match the published API, even when this test runs
    # on the earlier checkout whose public DTO predates that addition.
    class Metadata(AnalysisProvenance):
        predictions: list[ModelPrediction] = Field(default_factory=list)
    class Response(AnalysisResponse):
        predictions: list[ModelPrediction] = Field(default_factory=list)
        provenance: Metadata
    raw = deepcopy(example["analysis_response"])
    raw["provenance"].pop("predictions")
    dto = Response.model_validate(raw)
    assert prediction_statement(ExplanationEngine().explain_api(dto)).quantities


def test_prediction_numbers_never_change_rule_alerts_or_review_flags(example):
    api = example["analysis_response"]
    original = ExplanationEngine().explain_api(api)
    for prediction in (api["predictions"][0], api["provenance"]["predictions"][0]):
        prediction["value"].update(colorectal_cancer_risk_percent=99, any_cancer_risk_percent=99)
    changed = ExplanationEngine().explain_api(api)
    assert changed.summary_en == original.summary_en and changed.rule_results == original.rule_results
    assert api["trigger_results"][0]["priority"] == "review"


def test_unknown_model_version_does_not_get_assumed_percentage_semantics(example):
    for prediction in (example["analysis_response"]["predictions"][0], example["analysis_response"]["provenance"]["predictions"][0]):
        prediction["model_version"] = "future-unknown-version"
    output = ExplanationEngine().explain_api(example["analysis_response"])
    assert not prediction_statement(output).quantities
    assert "prediction_value_omitted" in {row.code for row in output.limitations}


def test_same_published_payload_also_works_in_the_rich_shared_contract(example):
    raw = json.loads((ROOT / "app/explanation/examples/mock_analysis.json").read_text())["analysis_result"]
    raw["predictions"] = example["analysis_response"]["predictions"]
    output = ExplanationEngine()(AnalysisResult.model_validate(raw))
    assert output.input_format == "analysis_result" and len(prediction_statement(output).quantities) == 3


def test_qcancer_wire_fixture_needs_no_calculator_database_or_network():
    code = '''
import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,name,*args):
        if name.startswith(("app.risk_models","app.reasoning","app.rag","app.extraction","app.services","app.db.session")):
            raise AssertionError("Unrelated implementation imported: "+name)
sys.meta_path.insert(0,Block())
from app.explanation.__main__ import main
sys.argv=["explanation","--api-v1","--example","app/explanation/examples/qcancer_api_response.json"]
raise SystemExit(main())
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "2.25 %" in result.stdout
