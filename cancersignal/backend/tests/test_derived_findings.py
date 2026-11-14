from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.reasoning import vocabulary as v
from app.reasoning.derived_findings import derive_lab_findings
from app.reasoning.trigger_engine import evaluate_triggers
from app.schemas.records import ObservationRead
from app.services.analysis_service import age_in_years, run_evaluator

PATIENT = uuid4()


def lab(code, value, unit, when=datetime(2026, 8, 14, 9, tzinfo=timezone.utc), text="SYNTHETIC laboratory report."):
    return ObservationRead(id=uuid4(), patient_id=PATIENT, observation_type="laboratory", code=code,
        text=text, numeric_value=Decimal(value), unit=unit, status="completed",
        observed_at=when, recorded_at=when)


def by_type(findings):
    return {f.finding_type: f for f in findings}


def test_low_haemoglobin_gives_anaemia_citing_the_lab():
    hb = lab("B-Hb", "108", "g/l")
    findings, missing = derive_lab_findings([hb], sex="female")
    found = by_type(findings)
    assert set(found) == {v.ANAEMIA}
    anaemia = found[v.ANAEMIA]
    assert anaemia.status == "current"
    assert [ref.observation_id for ref in anaemia.evidence] == [hb.id]
    assert anaemia.evidence[0].source_excerpt == hb.text
    assert "108" in anaemia.description
    assert any("ferritin" in m.lower() for m in missing)


def test_haemoglobin_and_low_ferritin_give_iron_deficiency_anaemia():
    hb, ferritin = lab("B-Hb", "108", "g/l"), lab("P-Ferritin", "9", "µg/l")
    found = by_type(derive_lab_findings([hb, ferritin], sex="female")[0])
    assert set(found) == {v.ANAEMIA, v.IRON_DEFICIENCY_ANAEMIA}
    assert {ref.observation_id for ref in found[v.IRON_DEFICIENCY_ANAEMIA].evidence} == {hb.id, ferritin.id}


def test_normal_ferritin_gives_anaemia_only():
    found = by_type(derive_lab_findings([lab("B-Hb", "108", "g/l"), lab("P-Ferritin", "40", "ug/l")], sex="female")[0])
    assert set(found) == {v.ANAEMIA}


@pytest.mark.parametrize(("sex", "value", "expected"), [
    ("female", "116", True), ("female", "117", False),
    ("male", "133", True), ("male", "134", False),
])
def test_demo_haemoglobin_limits_depend_on_sex(sex, value, expected):
    findings, _ = derive_lab_findings([lab("SYNTHETIC-HB", value, "g/L")], sex=sex)
    assert (v.ANAEMIA in by_type(findings)) == expected


def test_only_the_latest_haemoglobin_is_used():
    old = lab("B-Hb", "100", "g/l", when=datetime(2025, 1, 1, tzinfo=timezone.utc))
    new = lab("B-Hb", "140", "g/l", when=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert derive_lab_findings([new, old], sex="male")[0] == []


def test_unknown_sex_is_not_guessed():
    findings, missing = derive_lab_findings([lab("B-Hb", "90", "g/l")], sex="unknown")
    assert findings == []
    assert any("sex" in m for m in missing)


def test_fit_result_keeps_source_value_and_unit():
    source = lab("F-Hb-FIT", "48", "ug/g")
    found = by_type(derive_lab_findings([source], sex="male")[0])
    fit = found[v.FIT_RESULT]
    assert fit.numeric_value == source.numeric_value == Decimal("48")
    assert fit.unit == source.unit == v.FIT_UNIT
    assert [ref.observation_id for ref in fit.evidence] == [source.id]


def test_unmapped_lab_codes_are_reported():
    _, missing = derive_lab_findings([lab("P-Krea", "82", "umol/l")], sex="male")
    assert any("P-Krea" in m for m in missing)


def test_non_laboratory_observations_are_ignored():
    note = ObservationRead(id=uuid4(), patient_id=PATIENT, observation_type="clinical_note", text="Hb 90",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert derive_lab_findings([note], sex="male")[0] == []


@pytest.mark.parametrize(("at", "expected"), [
    (datetime(2026, 11, 13, 23, tzinfo=timezone.utc), 49),
    (datetime(2026, 11, 14, 0, tzinfo=timezone.utc), 50),
])
def test_age_is_whole_years_at_time_t(at, expected):
    assert age_in_years(date(1976, 11, 14), at) == expected


class Pipeline:
    def __init__(self, evaluate):
        self.evaluate = evaluate


def test_run_evaluator_passes_patient_facts_only_when_supported():
    calls = []

    def three_arguments(patient_id, findings, rules):
        calls.append("legacy")
        return []

    assert run_evaluator(Pipeline(three_arguments), uuid4(), [], [], {v.AGE_YEARS: 70}) == []
    assert calls == ["legacy"]
    assert run_evaluator(Pipeline(evaluate_triggers), uuid4(), [], [], {v.AGE_YEARS: 70}) == []
