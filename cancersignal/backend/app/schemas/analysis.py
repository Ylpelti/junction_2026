from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import AnalysisStatus, FindingStatus
from app.contracts.predictions import ModelPrediction
from app.contracts.evidence import EvidenceReference
from app.contracts.findings import FindingContent
from app.schemas.records import (
    ClinicalFindingRead, EncounterRead, NonEmpty,
    ObservationCreate, ObservationRead, Record,
)


class StructuredFinding(FindingContent):
    status: FindingStatus
    numeric_value: Decimal | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = None


class AnalysisRequest(Record):
    note_observation_id: UUID | None = None
    note: ObservationCreate | None = None

    @model_validator(mode="after")
    def exactly_one_note(self):
        if (self.note_observation_id is None) == (self.note is None):
            raise ValueError("Supply either note_observation_id or note, exclusively.")
        if self.note is not None and (self.note.observation_type != "clinical_note" or not self.note.text):
            raise ValueError("Analysis requires a clinical_note with source text.")
        return self


class RuleSnapshot(Record):
    name: str
    version: str
    source: str
    source_section: str
    recommended_action: str
    demonstration_only: bool
    # Snapshots stored before priorities existed default to review.
    priority: Literal["urgent", "review"] = "review"


class AnalysisProvenance(Record):
    input_observation_id: UUID | None = None
    cutoff: AwareDatetime | None = None
    context_observation_ids: list[UUID] = Field(default_factory=list)
    retrieval_method: str | None = None
    extraction_method: str | None = None
    rule_snapshots: dict[str, RuleSnapshot] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list)
    # Patient-level facts computed in Python at the cutoff, e.g. {"age_years": 67}.
    patient_facts: dict[str, int] = Field(default_factory=dict)
    predictions: list[ModelPrediction] = Field(default_factory=list)
    error_code: str | None = None


class FindingResponse(ClinicalFindingRead):
    evidence: list[EvidenceReference]


class TriggerResponse(Record):
    id: UUID
    trigger_rule_id: UUID
    rule_name: str
    rule_version: str
    demonstration_only: bool
    rule_source: str
    rule_source_section: str
    # Alert level set by the rule definition, never by the LLM.
    priority: Literal["urgent", "review"]
    triggered: bool
    explanation: str
    recommended_action: str | None
    requires_clinician_review: bool
    evidence_observation_ids: list[UUID]


class AnalysisResponse(Record):
    id: UUID
    patient_id: UUID
    created_at: AwareDatetime
    status: AnalysisStatus
    findings: list[FindingResponse]
    trigger_results: list[TriggerResponse]
    predictions: list[ModelPrediction] = Field(default_factory=list)
    # Original records for resolving every evidence reference in this response.
    source_observations: list[ObservationRead]
    explanation: str
    provenance: AnalysisProvenance


class TimelineEvent(Record):
    event_type: Literal["encounter", "observation"]
    occurred_at: AwareDatetime
    encounter: EncounterRead | None = None
    observation: ObservationRead | None = None
