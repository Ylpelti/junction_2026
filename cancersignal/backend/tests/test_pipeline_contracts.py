from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.adapters import from_legacy_context, to_legacy_finding, to_legacy_trigger
from app.contracts.analysis import AnalysisResult, TriggerEvaluation
from app.contracts.clinical_context import RetrievedContext, SourceObservation, StructuredPatientContext
from app.contracts.common import ComponentProvenance, Coverage, PatientScope
from app.contracts.evidence import EvidenceReference
from app.contracts.features import ComputedFeature
from app.contracts.findings import ClinicalFinding
from app.contracts.stages import FeatureBatch, FindingBatch
from app.contracts.validation import (
    EvidenceValidationError, merge_source_contexts, snapshot_digest, validate_evidence, validate_feature, validate_finding,
)

FIXTURES = Path(__file__).parent / "fixtures/pipeline_contracts"


def fixture(name="longitudinal"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def result_payload(name="longitudinal"):
    return fixture(name)["analysis_result"]


def scope(payload):
    return PatientScope.model_validate({key: payload[key] for key in
        ("patient_id", "as_of", "observed_since", "recorded_before")})


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_synthetic_examples_validate_and_roundtrip_without_database(path):
    raw = json.loads(path.read_text())
    assert raw["synthetic"] is True
    for key, model in (("rag_context", RetrievedContext), ("structured_context", StructuredPatientContext),
                       ("analysis_result", AnalysisResult), ("finding_batch", FindingBatch), ("feature_batch", FeatureBatch)):
        record = model.model_validate(raw[key])
        assert model.model_validate_json(record.model_dump_json()) == record
    result = AnalysisResult.model_validate(raw["analysis_result"])
    assert all("SYNTHETIC" in (source.text or "") for source in result.source_observations)
    assert result.validation_scope == "reference_integrity_only"


def test_structured_history_is_independent_of_ranked_context():
    raw = fixture()
    rag = RetrievedContext.model_validate(raw["rag_context"])
    structured = StructuredPatientContext.model_validate(raw["structured_context"])
    assert len(structured.observations) == 2
    assert not {row.id for row in structured.observations}.intersection(hit.source.id for hit in rag.retrieved_observations)
    assert {row.observed_at.year for row in structured.observations} == {2020, 2025}
    assert all(isinstance(row.numeric_value, Decimal) and row.unit == "g/L" for row in structured.observations)


def test_original_snapshots_and_nested_references_are_immutable():
    raw = fixture()
    result = AnalysisResult.model_validate(raw["analysis_result"])
    with pytest.raises(ValidationError, match="frozen"):
        result.source_observations[0].text = "Altered"
    with pytest.raises(ValidationError, match="frozen"):
        result.findings[0].evidence[0].source_excerpt = "Altered"
    assert result_payload() == raw["analysis_result"]


def test_absence_and_resolution_remain_distinct_and_missing_is_not_negative():
    result = AnalysisResult.model_validate(result_payload("negated_resolved"))
    assert {(finding.polarity, finding.temporal_status) for finding in result.findings} == {
        ("absent", "current"), ("present", "resolved")}
    contradictory = AnalysisResult.model_validate(result_payload("contradictory_incomplete"))
    assert contradictory.findings[0].polarity == "uncertain"
    assert contradictory.findings[0].temporal_status == "unknown"
    assert contradictory.computed_features[0].value is None
    assert contradictory.trigger_evaluations[0].evaluation_status == "indeterminate"


@pytest.mark.parametrize("changes", [{"polarity": "uncertain"}, {"temporal_status": "unknown"}])
def test_unknown_claim_states_require_explicit_reason(changes):
    raw = result_payload()["findings"][0] | changes
    with pytest.raises(ValidationError):
        ClinicalFinding.model_validate(raw)


@pytest.mark.parametrize("change", [
    {"patient_id": str(uuid4())}, {"observed_at": "2026-01-01T00:00:00Z"},
    {"recorded_at": "2026-01-01T00:00:00Z"}, {"recorded_at": "2027-01-01T00:00:00Z"},
])
def test_retrieved_context_rejects_foreign_or_unavailable_history(change):
    raw = fixture()["rag_context"]
    raw["retrieved_observations"][0]["source"].update(change)
    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(raw)


@pytest.mark.parametrize("change", [
    {"as_of": "2026-01-01T00:00:00"},
    {"recorded_before": "2027-01-01T00:00:00Z"},
    {"observed_since": "2026-01-01T00:00:00Z"},
])
def test_scope_rejects_naive_or_leaking_boundaries(change):
    with pytest.raises(ValidationError):
        scope(result_payload() | change)


@pytest.mark.parametrize("model,key", [(RetrievedContext, "rag_context"), (StructuredPatientContext, "structured_context")])
def test_complete_coverage_cannot_hide_truncated_records(model, key):
    raw = fixture()[key]
    raw["coverage"]["eligible_count"] += 1
    with pytest.raises(ValidationError, match="Complete coverage"):
        model.model_validate(raw)


def test_partial_coverage_requires_explanation_and_structured_access_cannot_be_semantic():
    with pytest.raises(ValidationError):
        StructuredPatientContext.model_validate(fixture()["structured_context"] | {"coverage": {"status": "partial"}})
    raw = fixture()["structured_context"]
    raw["access"]["method"] = "semantic"
    with pytest.raises(ValidationError):
        StructuredPatientContext.model_validate(raw)


def test_explicit_code_filter_does_not_accept_unrequested_measurements():
    raw = fixture()["structured_context"] | {"requested_codes": ["SOME-OTHER-CODE"]}
    with pytest.raises(ValidationError):
        StructuredPatientContext.model_validate(raw)


def test_relevance_is_not_restricted_to_probability_scale():
    raw = fixture()["rag_context"]
    raw["retrieved_observations"][0]["relevance"] = {"value": -0.25, "metric": "cosine_similarity"}
    assert RetrievedContext.model_validate(raw).retrieved_observations[0].relevance.value == -0.25
    raw["retrieved_observations"][0]["relevance"]["value"] = float("nan")
    with pytest.raises(ValidationError):
        RetrievedContext.model_validate(raw)


def test_reference_validation_is_explicitly_not_clinical_entailment():
    raw = result_payload()
    finding = ClinicalFinding.model_validate(raw["findings"][0])
    report = validate_finding(finding, raw["source_observations"], scope=scope(raw))
    assert report.reference_integrity == "validated"
    assert report.clinical_support == "not_assessed"
    assert report.time_scope_checked and not report.calculation_reproduced


@pytest.mark.parametrize("case,code", [
    ("missing", "missing_observation"), ("foreign", "cross_patient_evidence"),
    ("quote", "invalid_source_quote"), ("offset", "invalid_source_offsets"),
    ("no_quote", "missing_source_quote"), ("future", "source_outside_scope"),
])
def test_evidence_rejections_are_explicit(case, code):
    raw = result_payload()
    reference = deepcopy(raw["findings"][0]["evidence"][0])
    sources = deepcopy(raw["source_observations"])
    if case == "missing":
        reference["observation_id"] = str(uuid4())
    elif case == "foreign":
        sources[0]["patient_id"] = str(uuid4())
    elif case == "quote":
        reference["source_excerpt"] = "Invented source sentence"
    elif case == "offset":
        reference["end_offset"] += 1
    elif case == "no_quote":
        reference.update(source_excerpt=None, start_offset=None, end_offset=None)
    else:
        sources[0]["recorded_at"] = "2027-01-01T00:00:00Z"
    with pytest.raises(EvidenceValidationError) as error:
        validate_evidence(scope(raw).patient_id, [EvidenceReference.model_validate(reference)], sources, scope=scope(raw))
    assert error.value.code == code


def test_optional_repository_resolution_still_checks_patient_and_time():
    raw = result_payload()
    source = SourceObservation.model_validate(raw["source_observations"][0])
    reference = EvidenceReference(observation_id=source.id, source_excerpt=source.text)
    requested = []
    def resolver(patient_id, identifiers):
        requested.append((patient_id, identifiers))
        return [source]
    report = validate_evidence(source.patient_id, [reference], [], scope=scope(raw), resolver=resolver)
    assert requested == [(source.patient_id, (source.id,))]
    assert report.observation_ids == (source.id,)
    with pytest.raises(EvidenceValidationError, match="cross_patient"):
        validate_evidence(uuid4(), [reference], [], resolver=resolver)


def test_duplicate_ids_and_mutated_reference_shapes_are_rejected():
    raw = result_payload()
    reference = EvidenceReference.model_validate(raw["findings"][0]["evidence"][0])
    with pytest.raises(EvidenceValidationError, match="duplicate_evidence"):
        validate_evidence(scope(raw).patient_id, [reference, reference], raw["source_observations"])
    reference.start_offset = None
    with pytest.raises(EvidenceValidationError, match="invalid_evidence_shape"):
        validate_evidence(scope(raw).patient_id, [reference], raw["source_observations"])


def test_computed_value_is_decimal_and_reproducibility_requires_a_verifier():
    raw = result_payload()
    feature = ComputedFeature.model_validate(raw["computed_features"][0])
    assert feature.value == Decimal("-22")
    report = validate_feature(feature, raw["source_observations"], scope=scope(raw))
    assert not report.calculation_reproduced
    def reproduce(record, sources):
        assert record.calculation_method == "latest_minus_baseline"
        return sources[-1].numeric_value - sources[0].numeric_value
    assert validate_feature(feature, raw["source_observations"], scope=scope(raw), reproduce=reproduce).calculation_reproduced
    with pytest.raises(EvidenceValidationError, match="calculation_mismatch"):
        validate_feature(feature, raw["source_observations"], scope=scope(raw), reproduce=lambda record, sources: Decimal("-21"))


@pytest.mark.parametrize("changes", [
    {"value": "NaN"}, {"value": None}, {"input_units": []}, {"evidence_observation_ids": []},
    {"status": "insufficient_data"}, {"input_coverage": {"status": "unknown"}},
])
def test_feature_cannot_disguise_missing_inputs_as_a_value(changes):
    with pytest.raises(ValidationError):
        ComputedFeature.model_validate(result_payload()["computed_features"][0] | changes)


def test_input_units_are_preserved_and_mixed_units_require_explicit_conversion():
    raw = result_payload()
    feature = deepcopy(raw["computed_features"][0])
    sources = deepcopy(raw["source_observations"])
    sources[-1].update(numeric_value="12.3", unit="g/dL")
    with pytest.raises(EvidenceValidationError, match="input_unit_mismatch"):
        validate_feature(ComputedFeature.model_validate(feature), sources, scope=scope(raw))
    feature["input_units"] = ["g/L", "g/dL"]
    with pytest.raises(ValidationError):
        ComputedFeature.model_validate(feature)
    feature.update(unit_handling="explicit_conversion", conversion_method="synthetic-conversion-fixture-v1")
    report = validate_feature(ComputedFeature.model_validate(feature), sources, scope=scope(raw))
    assert not report.calculation_reproduced  # Declaring conversion is not proof it ran correctly.
    assert sources[-1]["numeric_value"] == "12.3" and sources[-1]["unit"] == "g/dL"


@pytest.mark.parametrize("change,code", [
    ({"trigger_rule_id": str(uuid4())}, "invalid_rule_reference"),
    ({"trigger_rule_version": "wrong-version"}, "invalid_rule_reference"),
    ({"supporting_finding_ids": [str(uuid4())]}, "invalid_finding_reference"),
    ({"supporting_feature_ids": [str(uuid4())]}, "invalid_feature_reference"),
    ({"supporting_observation_ids": []}, "incomplete_trigger_evidence"),
    ({"patient_id": str(uuid4())}, "cross_patient_trigger"),
])
def test_invalid_trigger_links_reject_the_entire_result(change, code):
    raw = result_payload()
    raw["trigger_evaluations"][0].update(change)
    with pytest.raises(ValidationError, match=code):
        AnalysisResult.model_validate(raw)


def test_unavailable_feature_and_absent_finding_cannot_support_positive_trigger():
    raw = result_payload("contradictory_incomplete")
    raw["trigger_evaluations"][0].update(evaluation_status="matched", requires_clinician_review=True)
    with pytest.raises(ValidationError, match="uncertain_positive_trigger"):
        AnalysisResult.model_validate(raw)
    raw = result_payload("no_matching_trigger")
    raw["trigger_evaluations"][0].update(evaluation_status="matched", requires_clinician_review=True)
    with pytest.raises(ValidationError, match="uncertain_positive_trigger"):
        AnalysisResult.model_validate(raw)


def test_source_snapshot_digest_detects_changes_and_is_order_independent():
    raw = result_payload()
    assert snapshot_digest(raw["source_observations"]) == snapshot_digest(reversed(raw["source_observations"]))
    raw["source_observations"][0]["text"] += " Changed later."
    with pytest.raises(ValidationError, match="snapshot_mismatch"):
        AnalysisResult.model_validate(raw)


def test_provenance_requires_real_component_identity_and_does_not_accept_ml_as_fact():
    with pytest.raises(ValidationError):
        ComponentProvenance(name="extract", version="1", method="llm")
    raw = result_payload()["findings"][0]
    raw["provenance"] = dict(name="predictor", version="1", method="ml", provider="synthetic", model="synthetic-model")
    with pytest.raises(ValidationError, match="not documented findings"):
        ClinicalFinding.model_validate(raw)


def test_legacy_projection_preserves_negation_and_refuses_temporal_or_boolean_loss():
    result = AnalysisResult.model_validate(result_payload("negated_resolved"))
    assert to_legacy_finding(result.findings[0]).status == "negated"
    assert to_legacy_finding(result.findings[1]).status == "resolved"
    raw = result_payload()["findings"][0] | {"polarity": "absent"}
    with pytest.raises(ValueError, match="information loss"):
        to_legacy_finding(ClinicalFinding.model_validate(raw))
    unknown = AnalysisResult.model_validate(result_payload("contradictory_incomplete")).trigger_evaluations[0]
    with pytest.raises(ValueError, match="Indeterminate"):
        to_legacy_trigger(unknown)


def test_legacy_import_paths_and_context_remain_compatible():
    from app.schemas.analysis import EvidenceReference as OldReference
    from app.rag.context import ContextObservation, RetrievedContext as OldContext
    from app.contracts.predictions import ModelPrediction
    from app.reasoning.interfaces import ModelPrediction as OldPrediction
    assert OldReference is EvidenceReference
    assert OldPrediction is ModelPrediction
    raw = fixture()["rag_context"]
    source = SourceObservation.model_validate(raw["retrieved_observations"][0]["source"])
    legacy = OldContext(patient_id=source.patient_id, cutoff=raw["as_of"],
        observations=[ContextObservation(observation=source, source_excerpt=source.text)],
        ranked_observation_ids=[source.id])
    converted = from_legacy_context(legacy, query="SYNTHETIC", provenance=ComponentProvenance.model_validate(raw["retrieval"]))
    assert converted.retrieved_observations[0].source.id == source.id
    assert converted.coverage.status == "unknown"


def test_independent_contexts_merge_without_rewriting_or_losing_sources():
    raw = fixture()
    rag = RetrievedContext.model_validate(raw["rag_context"])
    structured = StructuredPatientContext.model_validate(raw["structured_context"])
    sources = merge_source_contexts(rag, structured)
    assert len(sources) == 4
    assert snapshot_digest(sources) == raw["analysis_result"]["metadata"]["source_snapshot_digest"]
    foreign = deepcopy(raw["structured_context"])
    foreign["patient_id"] = str(uuid4())
    for row in foreign["observations"]:
        row["patient_id"] = foreign["patient_id"]
    with pytest.raises(EvidenceValidationError, match="context_scope_mismatch"):
        merge_source_contexts(rag, StructuredPatientContext.model_validate(foreign))


def test_merging_deduplicates_identical_sources_but_rejects_conflicting_snapshots():
    raw = fixture()
    raw["rag_context"]["retrieved_observations"].append({"source": raw["structured_context"]["observations"][0]})
    raw["rag_context"]["coverage"]["eligible_count"] += 1
    structured = StructuredPatientContext.model_validate(raw["structured_context"])
    assert len(merge_source_contexts(RetrievedContext.model_validate(raw["rag_context"]), structured)) == 4
    raw["rag_context"]["retrieved_observations"][-1]["source"]["text"] += " Changed."
    with pytest.raises(EvidenceValidationError, match="conflicting_source_snapshot"):
        merge_source_contexts(RetrievedContext.model_validate(raw["rag_context"]), structured)


def test_input_note_is_explicit_input_and_never_its_own_history():
    raw = fixture()
    note = deepcopy(raw["rag_context"]["retrieved_observations"][0]["source"])
    note.update(id=str(uuid4()), observation_type="clinical_note", observed_at=raw["rag_context"]["as_of"],
                recorded_at="2026-01-01T00:05:00Z")
    note = SourceObservation.model_validate(note)
    rag = RetrievedContext.model_validate(raw["rag_context"])
    structured = StructuredPatientContext.model_validate(raw["structured_context"])
    assert note.id in {row.id for row in merge_source_contexts(rag, structured, input_note=note)}
    raw["rag_context"]["retrieved_observations"].append({"source": note.model_dump(mode="json")})
    raw["rag_context"]["coverage"]["eligible_count"] += 1
    with pytest.raises(ValidationError, match="patient/time scope"):
        RetrievedContext.model_validate(raw["rag_context"])


def test_partial_numerical_estimate_cannot_become_a_positive_trigger():
    raw = result_payload()
    raw["computed_features"][0]["input_coverage"] = {
        "status": "partial", "eligible_count": 3,
        "missing_information": [{"code": "incomplete_history", "description": "SYNTHETIC missing baseline records."}]}
    raw["computed_features"][0]["missing_information"] = [{"code": "incomplete_history", "description": "Only available sources could be compared."}]
    # The feature estimate itself is representable; a positive clinical outcome is not.
    assert ComputedFeature.model_validate(raw["computed_features"][0]).value == Decimal("-22")
    with pytest.raises(ValidationError, match="missing_positive_feature"):
        AnalysisResult.model_validate(raw)


def test_feature_reference_window_and_missing_information_references_are_checked():
    raw = result_payload()
    feature = raw["computed_features"][0]
    feature["reference_window"]["start"] = "2024-01-01T00:00:00Z"
    with pytest.raises(ValidationError, match="feature_window_outside_scope"):
        AnalysisResult.model_validate(raw)
    raw = result_payload()
    raw["missing_information"] = [{"code": "unknown", "description": "SYNTHETIC", "observation_ids": [str(uuid4())]}]
    with pytest.raises(ValidationError, match="invalid_missing_information_reference"):
        AnalysisResult.model_validate(raw)


def test_failed_and_completed_statuses_cannot_hide_errors():
    raw = result_payload() | {"status": "failed"}
    with pytest.raises(ValidationError, match="missing_failure_details"):
        AnalysisResult.model_validate(raw)
    raw = result_payload()
    raw["issues"] = [{"code": "unavailable", "message": "SYNTHETIC stage failed", "component": "extractor", "severity": "error"}]
    with pytest.raises(ValidationError, match="completed_with_errors"):
        AnalysisResult.model_validate(raw)


def test_standalone_indeterminate_evaluation_requires_missing_information():
    raw = result_payload("contradictory_incomplete")["trigger_evaluations"][0]
    raw["missing_information"] = []
    with pytest.raises(ValidationError, match="Indeterminate"):
        TriggerEvaluation.model_validate(raw)


@pytest.mark.parametrize("model,key", [(FindingBatch, "finding_batch"), (FeatureBatch, "feature_batch")])
def test_failed_stage_cannot_masquerade_as_empty_success(model, key):
    raw = fixture()[key]
    output_key = "findings" if model is FindingBatch else "features"
    raw.update(status="failed")
    with pytest.raises(ValidationError, match="explicit error"):
        model.model_validate(raw)
    raw["issues"] = [{"code": "unavailable", "message": "SYNTHETIC stage unavailable", "component": "fixture", "severity": "error"}]
    with pytest.raises(ValidationError, match="cannot publish"):
        model.model_validate(raw)
    raw[output_key] = []
    assert model.model_validate(raw).status == "failed"
    raw.update(status="complete")
    with pytest.raises(ValidationError, match="unresolved errors"):
        model.model_validate(raw)
