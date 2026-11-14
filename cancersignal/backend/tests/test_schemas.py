from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.records import (
    EncounterCreate, FindingEvidenceCreate, ObservationCreate,
    ObservationEmbeddingCreate, TriggerRuleCreate,
    ObservationRead,
)


def observation(**overrides):
    values = dict(patient_id=uuid4(), observation_type="clinical_note",
                  text="SYNTHETIC source note.",
                  observed_at="2024-01-01T12:00:00+02:00", recorded_at="2024-01-01T13:00:00+02:00")
    return ObservationCreate(**(values | overrides))


def test_source_text_and_stable_id_are_preserved_and_times_are_utc():
    source = "SYNTHETIC: Denies blood in stool.\nFollow-up uncertain."
    identifier = uuid4()
    record = observation(id=identifier, text=source, status="negated")
    assert record.text == source
    assert record.id == identifier
    assert record.observed_at == datetime(2024, 1, 1, 10, tzinfo=timezone.utc)
    assert record.observed_at.utcoffset() == timedelta(0)
    assert record.status.value == "negated"


@pytest.mark.parametrize("overrides", [
    {"text": None}, {"text": "  "}, {"status": "no_cancer"},
    {"observed_at": "2024-01-01T12:00:00"}, {"recorded_at": "2024-01-01T13:00:00"},
    {"numeric_value": "NaN"},
])
def test_invalid_source_records_are_rejected(overrides):
    with pytest.raises(ValidationError):
        observation(**overrides)


def test_structured_measurement_without_text():
    record = observation(text=None, observation_type="laboratory", numeric_value="120.25", unit="g/L")
    assert str(record.numeric_value) == "120.25"


def test_read_schema_never_invents_a_missing_source_identifier():
    values = observation().model_dump(exclude={"id"})
    with pytest.raises(ValidationError):
        ObservationRead(**values)


def test_encounter_requires_timezone():
    with pytest.raises(ValidationError):
        EncounterCreate(patient_id=uuid4(), occurred_at=datetime(2024, 1, 1), encounter_type="synthetic")


@pytest.mark.parametrize("vector", [[], [0.0] * 10, [float("inf")] * 1536])
def test_embedding_must_have_finite_values_and_correct_dimension(vector):
    with pytest.raises(ValidationError):
        ObservationEmbeddingCreate(observation_id=uuid4(), embedding_model="synthetic", embedding=vector)


def test_embedding_can_be_pending():
    record = ObservationEmbeddingCreate(observation_id=uuid4(), embedding_model="pending-1536")
    assert record.embedding is None


@pytest.mark.parametrize("offsets", [
    {"start_offset": 0}, {"start_offset": -1, "end_offset": 2},
    {"start_offset": 3, "end_offset": 3},
    {"start_offset": 0, "end_offset": 2, "source_excerpt": None},
])
def test_invalid_evidence_offsets_are_rejected(offsets):
    with pytest.raises(ValidationError):
        FindingEvidenceCreate(finding_id=uuid4(), observation_id=uuid4(), patient_id=uuid4(),
                              **({"source_excerpt": "SYNTHETIC"} | offsets))


@pytest.mark.parametrize("conditions", [{}, {"lahde": None, "lahde_kohta": "section"}])
def test_rule_requires_source_information(conditions):
    with pytest.raises(ValidationError):
        TriggerRuleCreate(name="SYNTHETIC", description="Fixture only", conditions=conditions,
                          recommended_action="Physician review", version="1")
