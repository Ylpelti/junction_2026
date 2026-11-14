from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from app.schemas.records import NonEmpty, Record

CONTRACT_VERSION = "1.0"


class Contract(Record):
    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True, revalidate_instances="always")


class MissingInformation(Contract):
    code: NonEmpty
    description: NonEmpty
    observation_ids: tuple[UUID, ...] = ()


class ComponentProvenance(Contract):
    name: NonEmpty
    version: NonEmpty
    method: Literal["keyword", "full_text", "semantic", "structured", "hybrid", "llm", "deterministic", "manual", "ml"]
    provider: NonEmpty | None = None
    model: NonEmpty | None = None
    prompt_version: NonEmpty | None = None
    configuration_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def model_identity(self):
        if self.method in ("llm", "ml") and (not self.provider or not self.model):
            raise ValueError("LLM/ML provenance requires provider and model identity.")
        return self


class TimeWindow(Contract):
    start: AwareDatetime | None = None
    end: AwareDatetime

    @model_validator(mode="after")
    def increasing(self):
        if self.start is not None and self.start >= self.end:
            raise ValueError("Window start must precede its exclusive end.")
        return self


class PatientScope(Contract):
    patient_id: UUID
    as_of: AwareDatetime
    observed_since: AwareDatetime | None = None
    recorded_before: AwareDatetime | None = None

    @model_validator(mode="after")
    def scope_bounds(self):
        if self.recorded_before is None:
            object.__setattr__(self, "recorded_before", self.as_of)
        if self.recorded_before > self.as_of:
            raise ValueError("Knowledge cutoff cannot extend beyond as_of.")
        if self.observed_since is not None and self.observed_since >= self.as_of:
            raise ValueError("observed_since must precede as_of.")
        return self

    def permits(self, source, *, input_note_id: UUID | None = None) -> bool:
        if source.patient_id != self.patient_id:
            return False
        if source.id == input_note_id:
            return source.observation_type == "clinical_note" and source.observed_at == self.as_of
        return (source.observed_at < self.as_of and source.recorded_at < self.recorded_before
                and (self.observed_since is None or source.observed_at >= self.observed_since))


class Coverage(Contract):
    status: Literal["complete", "partial", "unknown"] = "unknown"
    eligible_count: int | None = Field(default=None, ge=0)
    missing_information: tuple[MissingInformation, ...] = ()

    @model_validator(mode="after")
    def explicit_coverage(self):
        if self.status == "complete" and self.eligible_count is None:
            raise ValueError("Complete coverage requires an eligible_count.")
        if self.status == "partial" and not self.missing_information:
            raise ValueError("Partial coverage must explain the missing data.")
        return self

    def validate_count(self, returned_count: int):
        if self.eligible_count is not None and self.eligible_count < returned_count:
            raise ValueError("eligible_count cannot be smaller than returned observations.")
        if self.status == "complete" and self.eligible_count != returned_count:
            raise ValueError("Complete coverage requires an exact eligible_count.")
        if self.status == "partial" and not self.missing_information:
            raise ValueError("Partial coverage must explain the missing data.")


class PipelineIssue(Contract):
    code: NonEmpty
    message: NonEmpty
    component: NonEmpty
    severity: Literal["warning", "error"]
