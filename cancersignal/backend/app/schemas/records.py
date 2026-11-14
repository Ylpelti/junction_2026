from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator,
)

from app.models.enums import AnalysisStatus, FindingStatus, ObservationStatus, ObservationType, Sex
from app.models.records import EMBEDDING_DIMENSION

NonEmpty = Annotated[str, Field(min_length=1, pattern=r"\S")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def timestamps_to_utc(cls, value):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return value


class IdentifiedRecord(Record):
    id: UUID = Field(default_factory=uuid4)


class PatientCreate(IdentifiedRecord):
    synthetic_name: Annotated[NonEmpty, Field(max_length=200)]
    birth_date: date
    sex: Sex


class PatientRead(PatientCreate):
    id: UUID = Field(...)
    created_at: AwareDatetime


class EncounterCreate(IdentifiedRecord):
    patient_id: UUID
    occurred_at: AwareDatetime
    encounter_type: Annotated[NonEmpty, Field(max_length=80)]
    organization: str | None = Field(default=None, max_length=200)


class EncounterRead(EncounterCreate):
    id: UUID = Field(...)


class ObservationCreate(IdentifiedRecord):
    patient_id: UUID
    encounter_id: UUID | None = None
    observation_type: ObservationType
    code: str | None = Field(default=None, max_length=100)
    text: NonEmpty | None = None
    numeric_value: Decimal | None = Field(default=None, max_digits=18, decimal_places=6, allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=80)
    status: ObservationStatus | None = None
    observed_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def has_content(self):
        if self.text is None and self.numeric_value is None:
            raise ValueError("An observation requires text or numeric_value.")
        return self


class ObservationRead(ObservationCreate):
    id: UUID = Field(...)


class ObservationEmbeddingCreate(IdentifiedRecord):
    observation_id: UUID
    embedding: Annotated[list[FiniteFloat], Field(min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION)] | None = None
    embedding_model: Annotated[NonEmpty, Field(max_length=200)]


class ObservationEmbeddingRead(ObservationEmbeddingCreate):
    id: UUID = Field(...)
    created_at: AwareDatetime


class TriggerRuleCreate(IdentifiedRecord):
    name: Annotated[NonEmpty, Field(max_length=200)]
    description: NonEmpty
    conditions: dict[str, JsonValue]
    recommended_action: NonEmpty
    version: Annotated[NonEmpty, Field(max_length=80)]
    enabled: bool = False

    @field_validator("conditions")
    @classmethod
    def source_required(cls, value):
        for key in ("lahde", "lahde_kohta"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ValueError(f"conditions.{key} must identify the rule source.")
        return value


class TriggerRuleRead(TriggerRuleCreate):
    id: UUID = Field(...)


class AnalysisRunCreate(IdentifiedRecord):
    patient_id: UUID
    status: AnalysisStatus = AnalysisStatus.PENDING
    model_name: str | None = Field(default=None, max_length=200)


class AnalysisRunRead(AnalysisRunCreate):
    id: UUID = Field(...)
    created_at: AwareDatetime


class ClinicalFindingCreate(IdentifiedRecord):
    analysis_run_id: UUID
    patient_id: UUID
    finding_type: Annotated[NonEmpty, Field(max_length=100)]
    description: NonEmpty
    status: FindingStatus


class ClinicalFindingRead(ClinicalFindingCreate):
    id: UUID = Field(...)


class FindingEvidenceCreate(Record):
    finding_id: UUID
    observation_id: UUID
    patient_id: UUID
    source_excerpt: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.start_offset is None and self.end_offset is None:
            return self
        if (self.start_offset is None or self.end_offset is None
                or self.end_offset <= self.start_offset or self.source_excerpt is None):
            raise ValueError("Offsets require an excerpt and a nonempty [start, end) range.")
        return self


class FindingEvidenceRead(FindingEvidenceCreate):
    pass


class TriggerResultCreate(IdentifiedRecord):
    patient_id: UUID
    analysis_run_id: UUID
    trigger_rule_id: UUID
    triggered: bool
    explanation: str | None = None
    requires_clinician_review: bool


class TriggerResultRead(TriggerResultCreate):
    id: UUID = Field(...)


class TriggerResultEvidenceCreate(Record):
    trigger_result_id: UUID
    observation_id: UUID
    patient_id: UUID


class TriggerResultEvidenceRead(TriggerResultEvidenceCreate):
    pass
