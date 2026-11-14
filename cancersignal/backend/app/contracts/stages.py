"""An empty successful output is distinct from an unavailable component."""
from typing import Literal

from pydantic import model_validator

from app.contracts.common import ComponentProvenance, MissingInformation, PatientScope, PipelineIssue
from app.contracts.features import ComputedFeature
from app.contracts.findings import ClinicalFinding
from app.contracts.qcancer import QCancerPredictors


class StageReport(PatientScope):
    contract_version: Literal["1.0"] = "1.0"
    status: Literal["complete", "partial", "failed"]
    provenance: ComponentProvenance
    missing_information: tuple[MissingInformation, ...] = ()
    issues: tuple[PipelineIssue, ...] = ()

    @model_validator(mode="after")
    def explicit_stage_state(self):
        has_error = any(issue.severity == "error" for issue in self.issues)
        if self.status == "failed" and not has_error:
            raise ValueError("Failed stages must report an explicit error.")
        if self.status == "complete" and has_error:
            raise ValueError("Complete stages cannot carry unresolved errors.")
        if self.status == "partial" and not (self.missing_information or self.issues):
            raise ValueError("Partial stages must explain incomplete output.")
        return self


class FindingBatch(StageReport):
    findings: tuple[ClinicalFinding, ...] = ()
    qcancer_predictors: QCancerPredictors | None = None

    @model_validator(mode="after")
    def finding_producer(self):
        if self.provenance.method not in ("llm", "manual", "deterministic"):
            raise ValueError("Finding batches require a finding producer, not an ML prediction adapter.")
        if self.status == "failed" and self.findings:
            raise ValueError("Failed extraction cannot publish clinical findings.")
        if any(row.patient_id != self.patient_id or row.provenance != self.provenance for row in self.findings):
            raise ValueError("Batch findings must match its patient and producer.")
        return self


class FeatureBatch(StageReport):
    features: tuple[ComputedFeature, ...] = ()

    @model_validator(mode="after")
    def feature_producer(self):
        if self.provenance.method != "deterministic":
            raise ValueError("Feature batches require deterministic provenance.")
        if self.status == "failed" and self.features:
            raise ValueError("Failed computation cannot publish numerical features.")
        if any(row.patient_id != self.patient_id or row.provenance != self.provenance for row in self.features):
            raise ValueError("Batch features must match its patient and producer.")
        return self
