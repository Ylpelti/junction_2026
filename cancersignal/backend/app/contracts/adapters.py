"""Explicit boundaries to the existing demo pipeline, without changing API v1."""

from app.contracts.analysis import TriggerEvaluation
from app.contracts.clinical_context import RetrievedContext, RetrievedObservation, SourceObservation
from app.contracts.common import ComponentProvenance, Coverage
from app.contracts.findings import ClinicalFinding
from app.models.enums import FindingStatus


def from_legacy_context(context, *, query: str, provenance: ComponentProvenance) -> RetrievedContext:
    """Legacy context does not attest completeness; don't silently claim it does."""
    return RetrievedContext(patient_id=context.patient_id, as_of=context.cutoff, query=query,
        retrieval=provenance, coverage=Coverage(status="unknown"),
        retrieved_observations=tuple(RetrievedObservation(source=SourceObservation.model_validate(item.observation))
                                    for item in context.observations))


def to_legacy_finding(finding: ClinicalFinding):
    from app.schemas.analysis import StructuredFinding
    # A legacy enum cannot retain both historical absence and unknown temporal state.
    mapping = {
        ("present", "current"): FindingStatus.CURRENT,
        ("present", "historical"): FindingStatus.HISTORICAL,
        ("present", "resolved"): FindingStatus.RESOLVED,
        ("absent", "current"): FindingStatus.NEGATED,
        ("uncertain", "current"): FindingStatus.UNCERTAIN,
    }
    status = mapping.get((finding.polarity, finding.temporal_status))
    if status is None or finding.missing_information:
        raise ValueError("Legacy status cannot represent this polarity/temporal pair without information loss.")
    return StructuredFinding(finding_type=finding.finding_type, description=finding.description,
        status=status, evidence=[ref.model_dump() for ref in finding.evidence], uncertainty=finding.uncertainty)


def to_legacy_trigger(evaluation: TriggerEvaluation):
    from app.reasoning.interfaces import TriggerEvaluation as LegacyTriggerEvaluation
    if evaluation.evaluation_status == "indeterminate":
        raise ValueError("Indeterminate outcomes cannot be converted to a boolean result.")
    if evaluation.supporting_feature_ids or evaluation.missing_information:
        raise ValueError("Legacy trigger output cannot retain feature links or missing-information metadata.")
    return LegacyTriggerEvaluation(trigger_rule_id=evaluation.trigger_rule_id,
        triggered=evaluation.evaluation_status == "matched", explanation=evaluation.explanation,
        evidence_observation_ids=list(evaluation.supporting_observation_ids))
