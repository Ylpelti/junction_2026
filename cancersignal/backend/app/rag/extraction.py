from app.models.enums import FindingStatus, ObservationType
from app.rag.context import ExtractionResult, RetrievedContext
from app.schemas.analysis import EvidenceReference, StructuredFinding
from app.schemas.records import ObservationRead


class StructuredSourceExtractor:
    """Demo adapter: copy the latest explicitly coded symptom/lab source facts.

    Free-text notes are not interpreted. No clinical thresholds or diagnoses are
    inferred. Status is explicit in the source; repeated codes use the latest
    source state so a later negation/resolution cannot resurrect an older signal.
    """

    name = "structured-source-demo-v1"

    def extract(self, context: RetrievedContext, note: ObservationRead) -> ExtractionResult:
        latest = {}
        for item in sorted(context.observations, key=lambda item: (
                item.observation.observed_at, item.observation.recorded_at, str(item.observation.id))):
            record = item.observation
            if record.observation_type in (ObservationType.SYMPTOM, ObservationType.LABORATORY) and record.code:
                latest[(record.observation_type, record.code)] = record
        output = ExtractionResult(missing_information=[
            "Free-text clinical-note extraction is not configured; only explicitly coded structured source facts are copied.",
            "Demonstration output is not a diagnosis or clinically validated risk assessment.",
        ])
        if not context.observations:
            output.missing_information.append("No eligible patient history exists before the input note.")
        statuses = {status.value: status for status in FindingStatus}
        for record in latest.values():
            status = statuses.get(record.status, FindingStatus.UNCERTAIN)
            # Completed historical measurements are facts, not current disease findings.
            if record.observation_type == ObservationType.LABORATORY and record.status == "completed":
                status = FindingStatus.HISTORICAL
            uncertainty = None
            if status == FindingStatus.UNCERTAIN:
                uncertainty = "Source is uncertain or has no usable explicit clinical status."
            if record.observation_type == ObservationType.SYMPTOM and record.text is None:
                output.missing_information.append(f"Structured symptom {record.id} has no source quote and was not extracted.")
                continue
            evidence = EvidenceReference(observation_id=record.id, source_excerpt=record.text,
                start_offset=0 if record.text else None, end_offset=len(record.text) if record.text else None)
            output.findings.append(StructuredFinding(
                finding_type=record.code, status=status,
                description=record.text or f"Source measurement {record.code}: {record.numeric_value} {record.unit or ''}".strip(),
                evidence=[evidence], uncertainty=uncertainty,
                numeric_value=record.numeric_value, unit=record.unit,
            ))
        return output
