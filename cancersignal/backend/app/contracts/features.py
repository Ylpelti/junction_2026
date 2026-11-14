from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from app.contracts.common import ComponentProvenance, Contract, Coverage, MissingInformation, TimeWindow
from app.schemas.records import NonEmpty


class ComputedFeature(Contract):
    id: UUID = Field(default_factory=uuid4)
    patient_id: UUID
    feature_type: NonEmpty
    status: Literal["computed", "insufficient_data", "invalid_input"]
    value: Decimal | None = Field(default=None, allow_inf_nan=False)
    unit: NonEmpty | None = None
    input_units: tuple[NonEmpty, ...] = ()
    unit_handling: Literal["preserved", "explicit_conversion"] = "preserved"
    conversion_method: NonEmpty | None = None
    calculation_method: NonEmpty
    provenance: ComponentProvenance
    evidence_observation_ids: tuple[UUID, ...] = ()
    reference_window: TimeWindow | None = None
    missing_information: tuple[MissingInformation, ...] = ()
    input_coverage: Coverage = Coverage()

    @model_validator(mode="after")
    def reproducible_shape(self):
        if self.provenance.method != "deterministic":
            raise ValueError("Computed features require deterministic algorithm provenance.")
        if len(set(self.evidence_observation_ids)) != len(self.evidence_observation_ids):
            raise ValueError("Feature source IDs must be unique.")
        if self.status == "computed":
            if self.value is None or not self.unit or not self.input_units or not self.evidence_observation_ids:
                raise ValueError("Computed values require explicit units and source measurements.")
            if len(set(self.input_units)) != len(self.input_units):
                raise ValueError("Declare each input unit once.")
            if self.unit_handling == "preserved" and (len(self.input_units) != 1 or self.conversion_method):
                raise ValueError("Mixed input units require explicit versioned conversion metadata.")
            if self.unit_handling == "explicit_conversion" and not self.conversion_method:
                raise ValueError("Unit conversion must identify its method.")
            if self.input_coverage.status != "complete" and not self.missing_information:
                raise ValueError("Computed features with incomplete/unknown coverage must explain it.")
        elif self.value is not None or not self.missing_information:
            raise ValueError("Unavailable features have no value and must explain missing/invalid inputs.")
        if (self.input_coverage.eligible_count is not None
                and self.input_coverage.eligible_count < len(self.evidence_observation_ids)):
            raise ValueError("Input coverage cannot contain fewer records than the evidence.")
        return self
