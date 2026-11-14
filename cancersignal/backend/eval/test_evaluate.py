"""Run from backend/: python -m pytest eval/test_evaluate.py -q  (no DB, no network)."""
from uuid import uuid4

import pytest

from app.schemas.records import ObservationRead
from eval.cases import TODAY_REF, load_cases
from eval.evaluate import (
    VARIANTS, StructuredRunner, assert_no_future_data, coded_facts_for, history_for, main, metrics, rules,
    run, run_variant,
)

CASES = {case.id: case for case in load_cases()}


def test_loader_builds_valid_observations():
    assert len(CASES) == 36
    assert {c.split for c in CASES.values()} == {"dev", "test"}
    patient_ids = [c.patient_id for c in CASES.values()]
    assert len(set(patient_ids)) == len(patient_ids)
    for case in CASES.values():
        records = [case.note, *case.today_facts, *case.history, *case.history_facts]
        assert all(isinstance(r, ObservationRead) and r.patient_id == case.patient_id for r in records)
        assert len({r.id for r in records}) == len(records)
        assert set(case.refs) == {r.id for r in records}
        assert case.refs[case.note.id] == TODAY_REF
        assert case.note.observation_type == "clinical_note" and case.note.observed_at == case.t
    # Stable IDs: loading twice gives the same UUIDs.
    again = {case.id: case for case in load_cases()}
    assert all(again[i].refs == CASES[i].refs for i in CASES)


def test_coded_facts_keep_quote_status_and_note_time():
    laine = CASES["EVAL-001"]
    (today,) = laine.today_facts
    assert (today.observation_type, today.code, today.status, today.text) == (
        "symptom", "rectal_bleeding", "negated", "Ei verta ulosteessa")
    assert today.observed_at == laine.t
    by_code = {f.code: f for f in laine.history_facts}
    assert laine.refs[by_code["change_in_bowel_habit"].id] == "NOTE-0902"
    assert by_code["change_in_bowel_habit"].observed_at < laine.t


def test_no_record_after_t_is_used():
    runner = StructuredRunner()
    for case in CASES.values():
        for variant in VARIANTS:
            records = runner.records(case, variant)
            assert_no_future_data(case, records)
            for r in records:
                assert r.observed_at < case.t or r.id in case.today_ids


def test_future_record_is_rejected():
    case = CASES["EVAL-002"]
    future = ObservationRead(id=uuid4(), patient_id=case.patient_id, observation_type="laboratory", code="F-HB-FIT",
                             numeric_value="99", unit="ug/g", observed_at=case.t, recorded_at=case.t)
    with pytest.raises(AssertionError):
        assert_no_future_data(case, [future])


def test_variants_differ_as_defined():
    laine = CASES["EVAL-001"]
    assert history_for(laine, "A") == []
    assert {r.observation_type for r in history_for(laine, "B")} == {"laboratory"}
    assert {r.observation_type for r in history_for(laine, "C")} == {"laboratory", "clinical_note"}
    assert len(history_for(laine, "C")) == len(laine.history)
    # Today's coded facts are in every variant; earlier notes' facts only in C.
    ids = lambda records: {r.id for r in records}  # noqa: E731 (pydantic models are not hashable)
    for variant in VARIANTS:
        assert ids(laine.today_facts) <= ids(coded_facts_for(laine, variant))
    assert ids(coded_facts_for(laine, "A")) == ids(coded_facts_for(laine, "B")) == ids(laine.today_facts)
    assert ids(laine.history_facts) <= ids(coded_facts_for(laine, "C"))
    assert not ids(laine.history_facts) & ids(coded_facts_for(laine, "A"))


def test_demo_patient_nieminen_a_is_review_and_c_is_urgent():
    nieminen = CASES["EVAL-002"]
    rule_set = rules()
    a = run_variant(nieminen, "A", StructuredRunner(), rule_set)
    c = run_variant(nieminen, "C", StructuredRunner(), rule_set)
    assert a.level == "review" and "SUO-08" not in a.rules
    assert c.level == "urgent" and "SUO-08" in c.rules
    assert "LAB-1030" in c.evidence_refs
    assert c.grounded and c.key_sources_hit


def test_resolved_today_overrides_older_current_fact():
    # EVAL-025: bowel change resolved in today's note; the earlier 'current' must not fire in C.
    outcome = run_variant(CASES["EVAL-025"], "C", StructuredRunner(), rules())
    assert outcome.level == "none"


def test_full_run_and_metrics_are_well_formed(tmp_path):
    outcomes = run(list(CASES.values()), StructuredRunner())
    assert len(outcomes) == 3 * len(CASES)
    assert all(o.grounded for o in outcomes)
    for variant in VARIANTS:
        m = metrics([o for o in outcomes if o.variant == variant])
        assert m["n"] == len(CASES)
        assert 0 <= m["level_accuracy"] <= 1
    assert main(["--split", "dev", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "summary.md").read_text(encoding="utf-8").startswith("# CancerSignal A/B/C evaluation")
    assert (tmp_path / "cases.csv").read_text(encoding="utf-8").startswith("case_id,")


def test_llm_cache_requires_existing_cache(tmp_path):
    with pytest.raises(SystemExit, match="cache directory not found"):
        main(["--extractor", "llm-cache", "--cache-dir", str(tmp_path / "missing"), "--out", str(tmp_path)])
