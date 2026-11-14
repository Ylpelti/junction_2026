from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from app.contracts.common import ComponentProvenance, Contract, MissingInformation
from app.contracts.evidence import EvidenceReference, SourceReference
from app.schemas.records import NonEmpty, Record


class FindingContent(Record):
    """Common content shared with the existing demo StructuredFinding contract."""
    finding_type: Annotated[NonEmpty, Field(max_length=100)]
    description: NonEmpty
    evidence: list[EvidenceReference] = Field(min_length=1)
    uncertainty: str | None = None


class ClinicalFinding(FindingContent, Contract):
    id: UUID = Field(default_factory=uuid4)
    patient_id: UUID
    polarity: Literal["present", "absent", "uncertain"]
    temporal_status: Literal["current", "historical", "resolved", "unknown"]
    evidence: tuple[SourceReference, ...] = Field(min_length=1)
    uncertainty: NonEmpty | None = None
    missing_information: tuple[MissingInformation, ...] = ()
    provenance: ComponentProvenance

    @model_validator(mode="after")
    def explicit_uncertainty(self):
        if self.provenance.method not in ("llm", "deterministic", "manual"):
            raise ValueError("Retrieval scores and ML predictions are not documented findings.")
        if (self.polarity == "uncertain" or self.temporal_status == "unknown") and not (
                self.uncertainty or self.missing_information):
            raise ValueError("Uncertainty or unknown timing requires an explicit explanation.")
        if len({ref.observation_id for ref in self.evidence}) != len(self.evidence):
            raise ValueError("Finding evidence IDs must be unique.")
        return self
