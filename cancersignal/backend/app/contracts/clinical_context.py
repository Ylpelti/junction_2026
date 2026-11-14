from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.contracts.common import ComponentProvenance, Contract, Coverage, PatientScope
from app.schemas.records import ObservationRead


class SourceObservation(ObservationRead, Contract):
    """Immutable snapshot reusing the existing canonical observation schema."""


class RelevanceScore(Contract):
    value: float = Field(allow_inf_nan=False)
    metric: str = Field(min_length=1)
    higher_is_better: bool = True


class RetrievedObservation(Contract):
    source: SourceObservation
    relevance: RelevanceScore | None = None
    retrieval_method: Literal["keyword", "full_text", "semantic", "structured", "hybrid"] | None = None


class RetrievedContext(PatientScope):
    contract_version: Literal["1.0"] = "1.0"
    query: str
    retrieved_observations: tuple[RetrievedObservation, ...]
    retrieval: ComponentProvenance
    coverage: Coverage = Coverage()
    generated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def history_scope(self):
        if self.retrieval.method not in ("keyword", "full_text", "semantic", "structured", "hybrid"):
            raise ValueError("Retrieval provenance must identify a retrieval method.")
        sources = [hit.source for hit in self.retrieved_observations]
        if len({source.id for source in sources}) != len(sources):
            raise ValueError("Retrieval contains duplicate source IDs.")
        if any(not self.permits(source) for source in sources):
            raise ValueError("Retrieved source violates patient/time scope.")
        self.coverage.validate_count(len(sources))
        return self


class StructuredPatientContext(PatientScope):
    contract_version: Literal["1.0"] = "1.0"
    observations: tuple[SourceObservation, ...]
    # Null means all codes; a nonempty tuple explicitly declares the requested subset.
    requested_codes: tuple[str, ...] | None = None
    coverage: Coverage
    access: ComponentProvenance

    @model_validator(mode="after")
    def numerical_scope(self):
        if self.access.method != "structured":
            raise ValueError("Numerical history must come from direct structured access.")
        if self.requested_codes is not None and not self.requested_codes:
            raise ValueError("Use null for all codes, not an empty code filter.")
        if len({row.id for row in self.observations}) != len(self.observations):
            raise ValueError("Numerical history contains duplicate source IDs.")
        for row in self.observations:
            if not self.permits(row):
                raise ValueError("Structured source violates patient/time scope.")
            if row.observation_type not in ("laboratory", "vital_sign") and row.numeric_value is None:
                raise ValueError("Structured context contains a nonmeasurement source.")
            if self.requested_codes is not None and row.code not in self.requested_codes:
                raise ValueError("Source falls outside requested codes.")
        self.coverage.validate_count(len(self.observations))
        return self
