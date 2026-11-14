from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field, ValidationError

from app.reasoning.interfaces import TriggerEvaluation
from app.reasoning.vocabulary import AGE_YEARS
from app.schemas.analysis import StructuredFinding
from app.schemas.records import NonEmpty, Record, TriggerRuleRead
from app.services.errors import PipelineError


class NumericCondition(Record):
    operator: Literal["lt", "lte", "gt", "gte", "eq"]
    value: Decimal = Field(allow_inf_nan=False)
    unit: NonEmpty


class FindingCondition(Record):
    kind: Literal["finding"] = "finding"
    finding_type: NonEmpty
    statuses: list[Literal["current", "historical"]] = Field(default_factory=lambda: ["current"], min_length=1)
    numeric: NumericCondition | None = None


class PatientCondition(Record):
    """Patient-level fact such as age at time t. Not a finding and adds no evidence."""
    kind: Literal["patient"] = "patient"
    field: Literal["age_years"]
    numeric: NumericCondition


class ConditionGroup(Record):
    kind: Literal["group"] = "group"
    operator: Literal["ALL", "ANY"]
    conditions: list[Annotated[Union[FindingCondition, PatientCondition, "ConditionGroup"], Field(discriminator="kind")]] = Field(min_length=1, max_length=50)


ConditionGroup.model_rebuild()


class DemonstrationRule(Record):
    demonstration: Literal[True]
    lahde: NonEmpty
    lahde_kohta: NonEmpty
    # Older demonstration rules have no priority; they are review-level.
    priority: Literal["urgent", "review"] = "review"
    expression: ConditionGroup


PATIENT_FACT_UNITS = {AGE_YEARS: "years"}


def compare(left: Decimal, condition: NumericCondition) -> bool:
    right = condition.value
    return {"lt": left < right, "lte": left <= right, "gt": left > right,
            "gte": left >= right, "eq": left == right}[condition.operator]


def matches_numeric(finding: StructuredFinding, condition: NumericCondition):
    if finding.numeric_value is None or finding.unit != condition.unit:
        return False
    return compare(finding.numeric_value, condition)


def patient_fact(facts: Mapping[str, object] | None, condition: PatientCondition) -> Decimal | None:
    """Return the fact as Decimal, or None when missing or unusable. Never guess."""
    if not facts or condition.numeric.unit != PATIENT_FACT_UNITS[condition.field]:
        return None
    value = facts.get(condition.field)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def evaluate_condition(condition, findings, facts=None, depth=0):
    if depth > 12:
        raise PipelineError("rule_nesting_limit")
    if isinstance(condition, PatientCondition):
        value = patient_fact(facts, condition)
        return (value is not None and compare(value, condition.numeric)), set()
    if isinstance(condition, FindingCondition):
        matching = [finding for finding in findings if finding.finding_type == condition.finding_type
            and finding.status in condition.statuses
            and not finding.uncertainty
            and (condition.numeric is None or matches_numeric(finding, condition.numeric))]
        return bool(matching), {ref.observation_id for finding in matching for ref in finding.evidence}
    evaluated = [evaluate_condition(child, findings, facts, depth + 1) for child in condition.conditions]
    matched = all(value for value, _ in evaluated) if condition.operator == "ALL" else any(value for value, _ in evaluated)
    return matched, set().union(*(ids for value, ids in evaluated if value)) if matched else set()


def evaluate_triggers(patient_id: UUID, findings: list[StructuredFinding], rules: list[TriggerRuleRead],
                      patient_facts: Mapping[str, object] | None = None) -> list[TriggerEvaluation]:
    """Pure rule evaluation; caller validates patient and evidence ownership.

    Only explicitly sourced demonstration rules are supported. Unknown condition
    formats fail explicitly instead of silently producing negative results.
    `patient_facts` (e.g. {"age_years": 67}) are computed by the caller at time t;
    a missing fact makes its condition false.
    """
    output = []
    for rule in rules:
        if not rule.enabled:
            continue
        try:
            definition = DemonstrationRule.model_validate(rule.conditions)
        except ValidationError:
            raise PipelineError("unsupported_rule_conditions") from None
        triggered, evidence = evaluate_condition(definition.expression, findings, patient_facts)
        output.append(TriggerEvaluation(trigger_rule_id=rule.id, triggered=triggered,
            priority=definition.priority,
            evidence_observation_ids=sorted(evidence, key=str),
            explanation=("Demonstration rule matched; physician review suggested." if triggered
                         else "No signals identified by this demonstration rule. Missing or uncertain facts may remain.")))
    return output
