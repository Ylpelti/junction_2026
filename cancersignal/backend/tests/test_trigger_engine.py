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


# ---- Colorectal rulebook (docs/rulebook-colorectal.md) ----------------------

from app.db.seed_rules import COLORECTAL_RULES, colorectal_rule_rows
from app.reasoning import vocabulary as v
from app.reasoning.trigger_engine import DemonstrationRule

SEEDED = {row["name"].split(":")[0]: TriggerRuleRead(**row) for row in colorectal_rule_rows()}


def colorectal(rule_id, findings, age=None):
    facts = None if age is None else {v.AGE_YEARS: age}
    return evaluate_triggers(uuid4(), findings, [SEEDED[rule_id]], patient_facts=facts)[0]


def fit(value, unit=v.FIT_UNIT):
    return finding(v.FIT_RESULT, numeric_value=value, unit=unit)


@pytest.mark.parametrize(("rule_id", "kinds", "age", "expected"), [
    ("SUO-01", [v.ABDOMINAL_MASS], 30, True),
    ("SUO-01", [v.ABDOMINAL_PAIN], 30, False),
    ("SUO-02", [v.CHANGE_IN_BOWEL_HABIT], 30, True),
    ("SUO-02", [v.ABDOMINAL_PAIN], 30, False),
    ("SUO-03", [v.IRON_DEFICIENCY_ANAEMIA], 30, True),
    ("SUO-03", [v.ANAEMIA], 30, False),
    ("SUO-04", [v.WEIGHT_LOSS, v.ABDOMINAL_PAIN], 40, True),
    ("SUO-04", [v.WEIGHT_LOSS, v.ABDOMINAL_PAIN], 39, False),
    ("SUO-04", [v.WEIGHT_LOSS], 60, False),
    ("SUO-05", [v.RECTAL_BLEEDING, v.ABDOMINAL_PAIN], 49, True),
    ("SUO-05", [v.RECTAL_BLEEDING, v.WEIGHT_LOSS], 30, True),
    ("SUO-05", [v.RECTAL_BLEEDING, v.ABDOMINAL_PAIN], 50, False),
    ("SUO-05", [v.RECTAL_BLEEDING], 30, False),
    ("SUO-06", [v.ABDOMINAL_PAIN], 50, True),
    ("SUO-06", [v.RECTAL_BLEEDING], 71, True),
    ("SUO-06", [v.ABDOMINAL_PAIN], 49, False),
    ("SUO-06", [v.ANAEMIA], 70, False),
    ("SUO-07", [v.ANAEMIA], 60, True),
    ("SUO-07", [v.ANAEMIA], 59, False),
    ("SUO-07", [v.IRON_DEFICIENCY_ANAEMIA], 70, False),
    ("SUO-09", [v.RECTAL_MASS], 30, True),
    ("SUO-09", [v.ABDOMINAL_MASS], 30, False),
])
def test_colorectal_rules_match_and_boundaries(rule_id, kinds, age, expected):
    facts = [finding(kind) for kind in kinds]
    result = colorectal(rule_id, facts, age)
    assert result.triggered == expected
    if expected:
        assert set(result.evidence_observation_ids) <= {ref.observation_id for f in facts for ref in f.evidence}
        assert result.evidence_observation_ids
    else:
        assert result.evidence_observation_ids == []


@pytest.mark.parametrize(("value", "expected"), [("10", True), ("48", True), ("9.9", False)])
def test_positive_fit_boundary(value, expected):
    assert colorectal("SUO-08", [fit(value)]).triggered == expected


def test_fit_rule_requires_exact_unit():
    assert not colorectal("SUO-08", [fit("48", unit="µg/g")]).triggered


@pytest.mark.parametrize(("value", "symptoms", "expected"), [
    ("9.9", [v.RECTAL_BLEEDING], True),
    ("0", [v.CHANGE_IN_BOWEL_HABIT], True),
    ("10", [v.RECTAL_BLEEDING], False),
    ("9.9", [], False),
])
def test_negative_fit_with_symptoms(value, symptoms, expected):
    assert colorectal("SUO-10", [fit(value), *(finding(kind) for kind in symptoms)]).triggered == expected


def test_negated_rectal_bleeding_does_not_trigger():
    assert not colorectal("SUO-06", [finding(v.RECTAL_BLEEDING, status="negated")], age=70).triggered


def test_resolved_iron_deficiency_anaemia_does_not_trigger():
    assert not colorectal("SUO-03", [finding(v.IRON_DEFICIENCY_ANAEMIA, status="resolved")]).triggered


@pytest.mark.parametrize("facts", [None, {}, {v.AGE_YEARS: None}, {v.AGE_YEARS: True}])
def test_missing_age_never_triggers_an_age_rule(facts):
    result = evaluate_triggers(uuid4(), [finding(v.ABDOMINAL_PAIN)], [SEEDED["SUO-06"]], patient_facts=facts)[0]
    assert not result.triggered


def test_patient_condition_adds_no_evidence():
    pain = finding(v.ABDOMINAL_PAIN)
    result = colorectal("SUO-06", [pain], age=67)
    assert result.evidence_observation_ids == [pain.evidence[0].observation_id]


def test_priority_is_returned_from_the_rule():
    assert colorectal("SUO-08", [fit("48")]).priority == "urgent"
    assert colorectal("SUO-09", [finding(v.RECTAL_MASS)]).priority == "urgent"
    assert colorectal("SUO-01", [finding(v.ABDOMINAL_MASS)]).priority == "review"
    # Older rules without a priority are review-level.
    assert evaluate_triggers(uuid4(), [finding()], [rule(group("ALL", leaf()))])[0].priority == "review"


def test_three_argument_call_still_works():
    assert evaluate_triggers(uuid4(), [finding(v.RECTAL_MASS)], [SEEDED["SUO-09"]])[0].triggered


def collect_finding_types(expression):
    if expression["kind"] == "finding":
        return {expression["finding_type"]}
    if expression["kind"] == "patient":
        return set()
    return set().union(*(collect_finding_types(child) for child in expression["conditions"]))


def test_seeded_rules_are_valid_sourced_demonstration_rules():
    rows = colorectal_rule_rows()
    assert [row["name"].split(":")[0] for row in rows] == [f"SUO-{n:02d}" for n in range(1, 11)]
    assert len({row["id"] for row in rows}) == len(rows) == len(COLORECTAL_RULES)
    for row in rows:
        definition = DemonstrationRule.model_validate(row["conditions"])
        assert row["conditions"]["lahde"].strip() and row["conditions"]["lahde_kohta"].strip()
        assert definition.priority in ("urgent", "review")
        assert row["enabled"] and row["version"] == "nice-2023-demo-1"
        assert collect_finding_types(row["conditions"]["expression"]) <= v.ALL_FINDINGS
    assert {row["name"].split(":")[0] for row in rows if row["conditions"]["priority"] == "urgent"} == {"SUO-08", "SUO-09"}
