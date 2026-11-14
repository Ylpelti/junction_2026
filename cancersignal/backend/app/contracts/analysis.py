from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.contracts.clinical_context import SourceObservation
from app.contracts.common import ComponentProvenance, Contract, MissingInformation, PatientScope, PipelineIssue
from app.contracts.features import ComputedFeature
from app.contracts.findings import ClinicalFinding
from app.contracts.predictions import ModelPrediction
from app.models.enums import AnalysisStatus
from app.schemas.records import NonEmpty


class RuleReference(Contract):
    trigger_rule_id: UUID
    version: NonEmpty
    source: NonEmpty
    source_section: NonEmpty


class TriggerEvaluation(Contract):
    trigger_rule_id: UUID
    trigger_rule_version: NonEmpty
    patient_id: UUID
    evaluation_status: Literal["matched", "not_matched", "indeterminate"]
    explanation: NonEmpty
    supporting_finding_ids: tuple[UUID, ...] = ()
    supporting_feature_ids: tuple[UUID, ...] = ()
    supporting_observation_ids: tuple[UUID, ...] = ()
    missing_information: tuple[MissingInformation, ...] = ()
    requires_clinician_review: bool

    @model_validator(mode="after")
    def explicit_outcome(self):
        for values in (self.supporting_finding_ids, self.supporting_feature_ids, self.supporting_observation_ids):
            if len(set(values)) != len(values):
                raise ValueError("Trigger references must be unique.")
        if self.evaluation_status == "matched" and (
                not self.requires_clinician_review or not (self.supporting_finding_ids or self.supporting_feature_ids)):
            raise ValueError("Matched rules require supported facts/features and clinician review.")
        if self.evaluation_status == "indeterminate" and not self.missing_information:
            raise ValueError("Indeterminate rules must explain missing or uncertain information.")
        return self


class EvaluationMetadata(Contract):
    dataset_id: NonEmpty
    dataset_version: NonEmpty
    split: Literal["demo", "train", "validation", "held_out"]
    input_mode: Literal["A", "B", "C"]


class PipelineMetadata(Contract):
    pipeline_version: NonEmpty
    components: tuple[ComponentProvenance, ...]
    rules: tuple[RuleReference, ...] = ()
    source_snapshot_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evaluation: EvaluationMetadata | None = None


class AnalysisResult(PatientScope):
    contract_version: Literal["1.0"] = "1.0"
    validation_scope: Literal["reference_integrity_only"] = "reference_integrity_only"
    analysis_id: UUID
    created_at: AwareDatetime
    status: AnalysisStatus
    input_note_id: UUID | None = None
    findings: tuple[ClinicalFinding, ...] = ()
    computed_features: tuple[ComputedFeature, ...] = ()
    trigger_evaluations: tuple[TriggerEvaluation, ...] = ()
    predictions: tuple[ModelPrediction, ...] = ()
    source_observations: tuple[SourceObservation, ...]
    metadata: PipelineMetadata
    missing_information: tuple[MissingInformation, ...] = ()
    issues: tuple[PipelineIssue, ...] = ()

    @model_validator(mode="after")
    def result_integrity(self):
        from app.contracts.validation import validate_analysis_result
        validate_analysis_result(self)
        return self
