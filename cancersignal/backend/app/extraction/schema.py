"""Provider output only. Patient identity and provenance are assigned by code."""
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.common import Contract, MissingInformation
from app.contracts.evidence import SourceReference
from app.reasoning.vocabulary import NOTE_FINDINGS  # Constants only; no rule/model execution.
from app.schemas.records import NonEmpty

FINDING_TYPES = NOTE_FINDINGS | {
    "investigation_planned", "investigation_completed", "investigation_status_unknown",
    "follow_up", "documented_observation",
}


class ExtractedFinding(Contract):
    finding_type: NonEmpty = Field(json_schema_extra={"enum": sorted(FINDING_TYPES)})
    description: NonEmpty
    polarity: Literal["present", "absent", "uncertain"]
    temporal_status: Literal["current", "historical", "resolved", "unknown"]
    evidence: tuple[SourceReference, ...] = Field(min_length=1, max_length=32)
    uncertainty: NonEmpty | None
    missing_information: tuple[MissingInformation, ...]

    @model_validator(mode="after")
    def extraction_scope(self):
        if self.finding_type not in FINDING_TYPES:
            raise ValueError("Unsupported extraction type; lab derivations and diagnoses are not allowed.")
        if (self.polarity == "uncertain" or self.temporal_status == "unknown") and not (
                self.uncertainty or self.missing_information):
            raise ValueError("Uncertain interpretation requires an explanation.")
        return self


class ExtractionOutput(Contract):
    findings: tuple[ExtractedFinding, ...] = Field(max_length=64)
    missing_information: tuple[MissingInformation, ...]


def output_schema() -> dict:
    """All properties required, nullable where appropriate (OpenAI strict subset)."""
    schema = ExtractionOutput.model_json_schema()

    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    return schema
