"""Conservative projection for consumers of the existing demo finding schema."""
from app.contracts.adapters import to_legacy_finding
from app.contracts.stages import FindingBatch
from app.models.enums import FindingStatus
from app.schemas.analysis import StructuredFinding


def legacy_findings(batch: FindingBatch) -> list[StructuredFinding]:
    """Keep the rich batch as the authoritative result; never pass failures as [].

    The old enum cannot encode historical absence/uncertainty or unknown timing.
    Such findings remain uncertain in the projection, so existing rules cannot
    treat them as positive. Missing-information metadata is retained in the
    uncertainty text and in the original batch, not silently discarded.
    """
    batch = FindingBatch.model_validate(batch)
    if batch.status == "failed":
        raise ValueError("Failed extraction must be handled before rule evaluation.")
    result = []
    for finding in batch.findings:
        try:
            result.append(to_legacy_finding(finding))
        except ValueError:
            details = f"Original polarity={finding.polarity}; temporal_status={finding.temporal_status}."
            if finding.uncertainty:
                details += " " + finding.uncertainty
            if finding.missing_information:
                details += " Missing information: " + "; ".join(gap.model_dump_json() for gap in finding.missing_information)
            result.append(StructuredFinding(finding_type=finding.finding_type, description=finding.description,
                status=FindingStatus.UNCERTAIN, uncertainty=details,
                evidence=[ref.model_dump() for ref in finding.evidence]))
    return result
