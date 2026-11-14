"""Pure reference validation: no database, LLM, clinical inference or calculations."""
from collections.abc import Callable, Iterable
from decimal import Decimal
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Literal
from uuid import UUID
from pydantic import ValidationError

from app.contracts.clinical_context import SourceObservation
from app.contracts.common import Contract, PatientScope
from app.contracts.evidence import EvidenceReference

if TYPE_CHECKING:
    from app.contracts.analysis import AnalysisResult
    from app.contracts.features import ComputedFeature
    from app.contracts.findings import ClinicalFinding


class EvidenceValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class ValidationReport(Contract):
    observation_ids: tuple[UUID, ...]
    reference_integrity: Literal["validated"] = "validated"
    clinical_support: Literal["not_assessed"] = "not_assessed"
    calculation_reproduced: bool = False
    time_scope_checked: bool = False


def source_index(sources: Iterable[SourceObservation]) -> dict[UUID, SourceObservation]:
    index = {}
    for row in sources:
        snapshot = SourceObservation.model_validate(row)
        if snapshot.id in index:
            raise EvidenceValidationError("duplicate_source", "Source IDs must be unique.")
        index[snapshot.id] = snapshot
    return index


def snapshot_digest(sources: Iterable[SourceObservation]) -> str:
    rows = sorted(source_index(sources).values(), key=lambda row: str(row.id))
    canonical = json.dumps([row.model_dump(mode="json") for row in rows], sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def merge_source_contexts(retrieved, structured, *, input_note: SourceObservation | None = None) -> tuple[SourceObservation, ...]:
    """Join branches without mixing patients or knowledge snapshots."""
    if (retrieved.patient_id, retrieved.as_of, retrieved.recorded_before) != (
            structured.patient_id, structured.as_of, structured.recorded_before):
        raise EvidenceValidationError("context_scope_mismatch", "Branches must share patient and event/knowledge cutoffs.")
    merged = {}
    for row in (*[hit.source for hit in retrieved.retrieved_observations], *structured.observations):
        if row.id in merged and row != merged[row.id]:
            raise EvidenceValidationError("conflicting_source_snapshot", "Branches disagree about an original source record.")
        merged[row.id] = row
    if input_note is not None:
        input_note = SourceObservation.model_validate(input_note)
        if not retrieved.permits(input_note, input_note_id=input_note.id):
            raise EvidenceValidationError("invalid_input_note_scope", "Input note must match patient and analysis event time.")
        if input_note.id in merged and input_note != merged[input_note.id]:
            raise EvidenceValidationError("conflicting_source_snapshot", "Input note reuses a historical UUID with different content.")
        merged[input_note.id] = input_note
    return tuple(sorted(merged.values(), key=lambda row: (row.observed_at, str(row.id))))


def validate_evidence(patient_id: UUID, references: Iterable[EvidenceReference], sources: Iterable[SourceObservation], *,
                      scope: PatientScope | None = None, input_note_id: UUID | None = None,
                      resolver: Callable[[UUID, tuple[UUID, ...]], Iterable[SourceObservation]] | None = None) -> ValidationReport:
    try:
        # Revalidate mutable legacy instances rather than trusting their type tag.
        references = tuple(EvidenceReference.model_validate(ref.model_dump()) for ref in references)
    except ValidationError:
        raise EvidenceValidationError("invalid_evidence_shape", "Evidence reference fields are inconsistent.") from None
    identifiers = tuple(ref.observation_id for ref in references)
    if len(set(identifiers)) != len(identifiers):
        raise EvidenceValidationError("duplicate_evidence", "Evidence IDs must be unique.")
    if scope is not None and scope.patient_id != patient_id:
        raise EvidenceValidationError("cross_patient_evidence", "Scope and patient disagree.")
    index = source_index(sources)
    missing = tuple(identifier for identifier in identifiers if identifier not in index)
    if missing and resolver is not None:
        for identifier, row in source_index(resolver(patient_id, missing)).items():
            if identifier not in missing:
                raise EvidenceValidationError("unexpected_repository_source", "Repository returned unrequested sources.")
            index[identifier] = row
    for ref in references:
        row = index.get(ref.observation_id)
        if row is None:
            raise EvidenceValidationError("missing_observation", "Referenced source does not exist in verified context.")
        if row.patient_id != patient_id:
            raise EvidenceValidationError("cross_patient_evidence", "Source belongs to another patient.")
        if scope is not None and not scope.permits(row, input_note_id=input_note_id):
            raise EvidenceValidationError("source_outside_scope", "Source violates the patient/time window.")
        if ref.source_excerpt is not None:
            if row.text is None or ref.source_excerpt not in row.text:
                raise EvidenceValidationError("invalid_source_quote", "Excerpt does not match original text.")
            if ref.start_offset is not None and (ref.end_offset is None or ref.end_offset > len(row.text)
                    or ref.start_offset < 0 or ref.end_offset <= ref.start_offset
                    or row.text[ref.start_offset:ref.end_offset] != ref.source_excerpt):
                raise EvidenceValidationError("invalid_source_offsets", "Offsets do not reproduce the original quote.")
        elif ref.start_offset is not None or ref.end_offset is not None:
            raise EvidenceValidationError("invalid_source_offsets", "Offsets require a source quote.")
        elif row.numeric_value is None:
            raise EvidenceValidationError("missing_source_quote", "Nonmeasurement evidence requires a verbatim excerpt.")
    return ValidationReport(observation_ids=tuple(sorted(identifiers, key=str)), time_scope_checked=scope is not None)


def validate_finding(finding: "ClinicalFinding", sources: Iterable[SourceObservation], *, scope: PatientScope,
                     input_note_id: UUID | None = None) -> ValidationReport:
    if finding.patient_id != scope.patient_id:
        raise EvidenceValidationError("cross_patient_finding", "Finding belongs to another patient.")
    return validate_evidence(finding.patient_id, finding.evidence, sources, scope=scope, input_note_id=input_note_id)


def validate_feature(feature: "ComputedFeature", sources: Iterable[SourceObservation], *, scope: PatientScope,
                     reproduce: Callable[["ComputedFeature", tuple[SourceObservation, ...]], Decimal] | None = None) -> ValidationReport:
    if feature.patient_id != scope.patient_id:
        raise EvidenceValidationError("cross_patient_feature", "Feature belongs to another patient.")
    index = source_index(sources)
    # Numeric evidence need not contain a text excerpt.
    references = [EvidenceReference(observation_id=identifier,
                  source_excerpt=index[identifier].text if identifier in index else None)
                  for identifier in feature.evidence_observation_ids]
    report = validate_evidence(feature.patient_id, references, index.values(), scope=scope)
    selected = tuple(index[identifier] for identifier in feature.evidence_observation_ids)
    if feature.reference_window is not None:
        if feature.reference_window.end > scope.as_of:
            raise EvidenceValidationError("feature_window_outside_scope", "Feature window exceeds analysis cutoff.")
        if any(not (row.observed_at < feature.reference_window.end and
                    (feature.reference_window.start is None or row.observed_at >= feature.reference_window.start)) for row in selected):
            raise EvidenceValidationError("feature_window_outside_scope", "Measurement falls outside the feature window.")
    if feature.status == "computed":
        if any(row.numeric_value is None for row in selected):
            raise EvidenceValidationError("missing_numeric_value", "Computed feature references an unavailable measurement.")
        if any(not row.unit for row in selected) or {row.unit for row in selected} != set(feature.input_units):
            raise EvidenceValidationError("input_unit_mismatch", "Declared input units must exactly preserve source units.")
        if reproduce is not None:
            expected = reproduce(feature, selected)
            if not isinstance(expected, Decimal) or not expected.is_finite() or expected != feature.value:
                raise EvidenceValidationError("calculation_mismatch", "Algorithm did not reproduce the declared Decimal value.")
            return ValidationReport(observation_ids=report.observation_ids, calculation_reproduced=True, time_scope_checked=True)
    return report


def validate_analysis_result(result: "AnalysisResult") -> ValidationReport:
    sources = source_index(result.source_observations)
    if any(not result.permits(row, input_note_id=result.input_note_id) for row in sources.values()):
        raise EvidenceValidationError("source_outside_scope", "Result sources violate patient/time scope.")
    if result.input_note_id is not None and result.input_note_id not in sources:
        raise EvidenceValidationError("missing_input_note", "Input note must be included in source observations.")
    if result.metadata.source_snapshot_digest is not None and snapshot_digest(sources.values()) != result.metadata.source_snapshot_digest:
        raise EvidenceValidationError("snapshot_mismatch", "Source snapshot digest does not match.")
    findings = {finding.id: finding for finding in result.findings}
    features = {feature.id: feature for feature in result.computed_features}
    if len(set(findings) | set(features)) != len(result.findings) + len(result.computed_features):
        raise EvidenceValidationError("duplicate_derived_id", "Derived record IDs must be unique.")
    for record in (*result.findings, *result.computed_features):
        if record.provenance not in result.metadata.components:
            raise EvidenceValidationError("unknown_producer", "Derived record producer must appear in pipeline metadata.")
    for finding in result.findings:
        validate_finding(finding, sources.values(), scope=result, input_note_id=result.input_note_id)
    for feature in result.computed_features:
        validate_feature(feature, sources.values(), scope=result)
    rules = {rule.trigger_rule_id: rule.version for rule in result.metadata.rules}
    if len(rules) != len(result.metadata.rules):
        raise EvidenceValidationError("duplicate_rule", "A run must use one version per rule ID.")
    evaluated = set()
    for evaluation in result.trigger_evaluations:
        if evaluation.patient_id != result.patient_id:
            raise EvidenceValidationError("cross_patient_trigger", "Trigger belongs to another patient.")
        if rules.get(evaluation.trigger_rule_id) != evaluation.trigger_rule_version:
            raise EvidenceValidationError("invalid_rule_reference", "Trigger references an unknown rule/version.")
        if evaluation.trigger_rule_id in evaluated:
            raise EvidenceValidationError("duplicate_trigger", "A rule may be evaluated only once per run.")
        evaluated.add(evaluation.trigger_rule_id)
        required_sources = set()
        for identifier in evaluation.supporting_finding_ids:
            if identifier not in findings:
                raise EvidenceValidationError("invalid_finding_reference", "Trigger references a missing finding.")
            finding = findings[identifier]
            if evaluation.evaluation_status == "matched" and (
                    finding.polarity != "present" or finding.temporal_status in ("resolved", "unknown") or finding.uncertainty):
                raise EvidenceValidationError("uncertain_positive_trigger", "A matched trigger cannot rely on absent/resolved/uncertain facts.")
            required_sources.update(ref.observation_id for ref in finding.evidence)
        for identifier in evaluation.supporting_feature_ids:
            if identifier not in features:
                raise EvidenceValidationError("invalid_feature_reference", "Trigger references a missing feature.")
            feature = features[identifier]
            if evaluation.evaluation_status == "matched" and (feature.status != "computed" or feature.input_coverage.status != "complete"):
                raise EvidenceValidationError("missing_positive_feature", "A matched trigger cannot rely on unavailable features.")
            required_sources.update(feature.evidence_observation_ids)
        if set(evaluation.supporting_observation_ids) != required_sources:
            raise EvidenceValidationError("incomplete_trigger_evidence", "Supporting source IDs must exactly cover cited findings/features.")
    missing_groups = [result.missing_information]
    missing_groups.extend(record.missing_information for record in (*result.findings, *result.computed_features, *result.trigger_evaluations))
    missing_groups.extend(feature.input_coverage.missing_information for feature in result.computed_features)
    for messages in missing_groups:
        if any(identifier not in sources for message in messages for identifier in message.observation_ids):
            raise EvidenceValidationError("invalid_missing_information_reference", "Missing-information messages cite unknown sources.")
    for prediction in result.predictions:
        if prediction.patient_id != result.patient_id or prediction.as_of != result.as_of:
            raise EvidenceValidationError("prediction_scope_mismatch", "Prediction scope must match this analysis.")
        if any(identifier not in sources for identifier in prediction.evidence_observation_ids):
            raise EvidenceValidationError("invalid_prediction_reference", "Prediction references an unknown source.")
    if result.status == "completed" and any(issue.severity == "error" for issue in result.issues):
        raise EvidenceValidationError("completed_with_errors", "Completed analyses cannot carry unresolved errors.")
    if result.status == "failed" and not any(issue.severity == "error" for issue in result.issues):
        raise EvidenceValidationError("missing_failure_details", "Failed analyses must provide an explicit pipeline error.")
    return ValidationReport(observation_ids=tuple(sorted(sources, key=str)), time_scope_checked=True)
