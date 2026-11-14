from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.contracts.analysis import RuleReference
from app.contracts.common import ComponentProvenance, Contract, PipelineIssue
from app.schemas.records import NonEmpty

SummaryKind = Literal["review_signals", "indeterminate", "no_signals", "observations_only"]


class Quantity(Contract):
    slot: NonEmpty
    value: Decimal = Field(allow_inf_nan=False)
    unit: NonEmpty


class PlanEntry(Contract):
    fact_key: NonEmpty
    observation_ids: tuple[UUID, ...]
    quantities: tuple[Quantity, ...]


class ExplanationPlan(Contract):
    """The LLM can select/order grounded statements, never author unchecked claims."""
    summary_kind: SummaryKind
    style: Literal["compact", "standard"]
    entries: tuple[PlanEntry, ...] = Field(max_length=128)


class ExplanationStatement(Contract):
    key: NonEmpty
    kind: Literal["finding", "measurement", "feature", "prediction", "rule"]
    text_fi: NonEmpty
    observation_ids: tuple[UUID, ...]
    quantities: tuple[Quantity, ...] = ()
    finding_ids: tuple[UUID, ...] = ()
    feature_ids: tuple[UUID, ...] = ()
    prediction_index: int | None = Field(default=None, ge=0)
    rule_reference: RuleReference | None = None
    requires_clinician_review: bool | None = None
    # Verbatim producer metadata, never generated prose or an LLM prompt field.
    source_notice: str | None = None


class Limitation(Contract):
    code: NonEmpty
    text_fi: NonEmpty
    observation_ids: tuple[UUID, ...] = ()
    related_keys: tuple[str, ...] = ()


class ExplanationResult(Contract):
    contract_version: Literal["1.0"] = "1.0"
    language: Literal["fi"] = "fi"
    input_format: Literal["analysis_result", "api_v1"] = "analysis_result"
    analysis_id: UUID
    patient_id: UUID
    as_of: AwareDatetime
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["llm", "fallback", "unavailable"]
    summary_fi: NonEmpty
    findings: tuple[ExplanationStatement, ...] = ()
    mathematical_outputs: tuple[ExplanationStatement, ...] = ()
    rule_results: tuple[ExplanationStatement, ...] = ()
    limitations: tuple[Limitation, ...]
    provenance: ComponentProvenance
    attempted_provider: ComponentProvenance | None = None
    issues: tuple[PipelineIssue, ...] = ()
    reference_integrity: Literal["validated"] = "validated"
    numerical_consistency: Literal["exact_input_copy"] = "exact_input_copy"
    calculation_correctness: Literal["not_assessed"] = "not_assessed"
    clinical_validity: Literal["not_assessed"] = "not_assessed"


class PredictionDisplaySpec(Contract):
    """Explicit display mapping, not a risk model, conversion, or validation claim.

    Paths address keys INSIDE ModelPrediction.value. Identity matching is exact.
    There is deliberately no assumed score/probability/units payload format.
    """
    model_name: NonEmpty
    model_version: NonEmpty
    prediction_type: NonEmpty
    value_path: tuple[str, ...]
    unit_path: tuple[str, ...] = Field(min_length=1)


def plan_schema() -> dict:
    schema = ExplanationPlan.model_json_schema()

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema
