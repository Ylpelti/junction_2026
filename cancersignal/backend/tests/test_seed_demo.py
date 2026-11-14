"""Versioned demo patients: JSON validity, stable IDs, expected alerts (no DB) and an opt-in DB seed test."""
import json

import pytest
from sqlalchemy import func, select

from app.db.seed_demo import DEMO_FILE, DemoFile, load, rows, seed_demo, validate
from app.db.seed_rules import colorectal_rule_rows
from app.models import Observation, Patient
from app.rag.context import ContextObservation, RetrievedContext
from app.rag.extraction import StructuredSourceExtractor
from app.reasoning.derived_findings import derive_lab_findings
from app.reasoning.trigger_engine import evaluate_triggers
from app.reasoning.vocabulary import AGE_YEARS
from app.schemas.records import ObservationRead, TriggerRuleRead
from app.services.analysis_service import age_in_years

DATA = load()


def test_demo_file_is_valid_and_synthetic():
    assert [p.key for p in DATA.patients] == ["laine", "nieminen", "korhonen", "heikkinen"]
    assert all(p.synthetic_name.startswith("SYNTHETIC ") for p in DATA.patients)


def test_labs_use_loinc_for_hb_and_ferritin_and_local_fit():
    codes = {(r.display, r.code_system, r.code) for p in DATA.patients for r in p.records if r.type == "laboratory"}
    assert ("B-Hb", "LOINC", "718-7") in codes
    assert ("P-Ferritin", "LOINC", "2276-4") in codes
    assert ("F-Hb-FIT", "local", "F-HB-FIT") in codes  # no verified LOINC code in ug/g


def test_ids_are_stable_and_unique():
    patients, observations = rows(DATA)
    again_patients, again_observations = rows(load())
    assert [p["id"] for p in patients] == [p["id"] for p in again_patients]
    assert [o["id"] for o in observations] == [o["id"] for o in again_observations]
    assert len({o["id"] for o in observations}) == len(observations)
    # Every row is a valid API observation and strictly before the demo time.
    for row in observations:
        record = ObservationRead(**row)
        assert record.observed_at < DATA.demo_time and record.recorded_at < DATA.demo_time


@pytest.mark.parametrize("patient", DATA.patients, ids=lambda p: p.key)
def test_expected_alert_without_llm(patient):
    """Same steps as create_analysis, without the DB: structured extractor, lab derivation, rules, age at t."""
    _, observations = rows(DemoFile.model_validate({**DATA.model_dump(), "patients": [patient.model_dump()]}))
    history = [ObservationRead(**row) for row in observations]
    patient_id = history[0].patient_id
    note = ObservationRead(id=patient_id, patient_id=patient_id, observation_type="clinical_note",
                           text=patient.today_note_draft, observed_at=DATA.demo_time, recorded_at=DATA.demo_time)
    context = RetrievedContext(patient_id=patient_id, cutoff=DATA.demo_time,
        observations=[ContextObservation(observation=r, source_excerpt=r.text) for r in history],
        ranked_observation_ids=[r.id for r in history])
    findings = list(StructuredSourceExtractor().extract(context, note).findings)
    findings += derive_lab_findings(history, sex=patient.sex)[0]
    rules = [TriggerRuleRead(**row) for row in colorectal_rule_rows()]
    results = evaluate_triggers(patient_id, findings, rules,
                                patient_facts={AGE_YEARS: age_in_years(patient.birth_date, DATA.demo_time)})
    triggered = [r for r in results if r.triggered]
    names = {r.id: r.name.split(":")[0] for r in rules}
    level = "urgent" if any(r.priority == "urgent" for r in triggered) else "review" if triggered else "none"
    assert level == patient.expected_without_llm.level
    assert sorted(names[r.trigger_rule_id] for r in triggered) == sorted(patient.expected_without_llm.rules)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["patients"][0].update(synthetic_name="Laine Aino"), "SYNTHETIC"),
    (lambda d: d["patients"][0]["records"][2]["coded"][0].update(quote="not in the note"), "verbatim"),
    (lambda d: d["patients"][0]["records"][0].update(code="9999-9"), "lab_codes"),
    (lambda d: d["patients"][0]["records"][0].update(observed_at="2026-11-14T09:00:00Z"), "before demo_time"),
])
def test_validation_rejects_bad_data(change, message):
    raw = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    change(raw)
    with pytest.raises(ValueError, match=message):
        validate(DemoFile.model_validate(raw))


@pytest.mark.integration
def test_seed_demo_is_insert_only_and_idempotent(db_session):
    first = seed_demo(db_session)
    count = db_session.scalar(select(func.count()).select_from(Observation))
    second = seed_demo(db_session)
    assert first == second
    assert db_session.scalar(select(func.count()).select_from(Observation)) == count
    names = set(db_session.scalars(select(Patient.synthetic_name)))
    assert {p.synthetic_name for p in DATA.patients} <= names
