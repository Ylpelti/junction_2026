from uuid import uuid4
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.reasoning.interfaces import ModelPrediction
from app.reasoning.trigger_engine import evaluate_triggers
from app.schemas.analysis import EvidenceReference, StructuredFinding
from app.schemas.records import TriggerRuleRead
from app.services.errors import PipelineError


def finding(kind="demo", status="current", **kwargs):
    return StructuredFinding(finding_type=kind, status=status, description="SYNTHETIC fact",
        evidence=[EvidenceReference(observation_id=uuid4(), source_excerpt="SYNTHETIC")], **kwargs)


def rule(expression, **kwargs):
    return TriggerRuleRead(id=uuid4(), name="SYNTHETIC rule", description="Demonstration only",
        conditions={"demonstration": True, "lahde": "SYNTHETIC_TEST", "lahde_kohta": "fixture", "expression": expression},
        recommended_action="Physician review", version="demo-v1", enabled=kwargs.get("enabled", True))


def group(operator, *children):
    return {"kind": "group", "operator": operator, "conditions": list(children)}


def leaf(kind="demo", **kwargs):
    return {"kind": "finding", "finding_type": kind, **kwargs}


@pytest.mark.parametrize("status", ["negated", "resolved", "uncertain", "historical"])
def test_noncurrent_findings_do_not_trigger_default_rule(status):
    result = evaluate_triggers(uuid4(), [finding(status=status)], [rule(group("ALL", leaf()))])[0]
    assert not result.triggered
    assert not result.evidence_observation_ids
    assert "No signals identified" in result.explanation


def test_explicit_uncertainty_blocks_positive_status():
    output = evaluate_triggers(uuid4(), [finding(uncertainty="Source is ambiguous")], [rule(group("ALL", leaf()))])
    assert not output[0].triggered


@pytest.mark.parametrize(("operator", "expected"), [("ALL", False), ("ANY", True)])
def test_all_any_groups(operator, expected):
    fact = finding()
    output = evaluate_triggers(uuid4(), [fact], [rule(group(operator, leaf(), leaf("missing")))])[0]
    assert output.triggered == expected
    assert output.evidence_observation_ids == ([fact.evidence[0].observation_id] if expected else [])


def test_nested_groups_preserve_only_supporting_evidence():
    a, b, unrelated = finding("a"), finding("b"), finding("irrelevant")
    output = evaluate_triggers(uuid4(), [a, b, unrelated], [rule(group("ALL", leaf("a"), group("ANY", leaf("b"), leaf("missing"))))])[0]
    assert output.triggered
    assert set(output.evidence_observation_ids) == {a.evidence[0].observation_id, b.evidence[0].observation_id}


@pytest.mark.parametrize(("unit", "expected"), [("demo_units", True), ("different_units", False)])
def test_numeric_comparison_uses_decimal_and_exact_units(unit, expected):
    record = finding(numeric_value="2.125", unit=unit)
    expression = group("ALL", leaf(numeric={"operator": "lt", "value": "3", "unit": "demo_units"}))
    assert evaluate_triggers(uuid4(), [record], [rule(expression)])[0].triggered == expected


def test_historical_sources_must_be_explicitly_allowed():
    record = finding(status="historical")
    assert evaluate_triggers(uuid4(), [record], [rule(group("ALL", leaf(statuses=["historical"])) )])[0].triggered


def test_disabled_rule_is_not_evaluated():
    assert evaluate_triggers(uuid4(), [finding()], [rule(group("ALL", leaf()), enabled=False)]) == []


def test_model_prediction_cannot_be_silently_promoted_to_a_clinical_fact():
    prediction = ModelPrediction(patient_id=uuid4(), model_name="SYNTHETIC-adapter", model_version="test-v1",
        as_of=datetime.now(timezone.utc), prediction_type="synthetic_label", value="example")
    with pytest.raises(ValidationError):
        StructuredFinding.model_validate(prediction.model_dump())


@pytest.mark.parametrize("conditions", [
    {"demonstration": False}, {},
    {"demonstration": True, "lahde": "SYNTHETIC", "lahde_kohta": "test", "expression": group("ALL")},
    {"demonstration": True, "lahde": "SYNTHETIC", "lahde_kohta": "test", "expression": group("ANY", leaf(statuses=["negated"]))},
])
def test_unsupported_rule_formats_fail_explicitly(conditions):
    source = rule(group("ALL", leaf()))
    # Invalid source metadata is also caught by the engine, not just API ingestion.
    source.conditions = conditions
    with pytest.raises(PipelineError, match="unsupported_rule_conditions"):
        evaluate_triggers(uuid4(), [finding()], [source])
