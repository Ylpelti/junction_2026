from datetime import datetime, timezone

import pytest

from app.db.seed import seed, synthetic_id
from app.models import Observation
from app.rag.extraction import StructuredSourceExtractor
from app.rag.retrieval import retrieve_context
from app.schemas.records import ObservationRead

pytestmark = pytest.mark.integration


def test_retrieval_filters_patient_event_time_and_recording_time_before_ranking(db_session):
    seed(db_session)
    patient = synthetic_id("patient/0")
    before = datetime(2023, 1, 1, tzinfo=timezone.utc)
    earlier = datetime(2021, 1, 1, tzinfo=timezone.utc)
    later = datetime(2024, 1, 1, tzinfo=timezone.utc)
    common = dict(observation_type="clinical_note", text="SYNTHETIC uniqueterm")
    valid = Observation(patient_id=patient, observed_at=earlier, recorded_at=earlier, **common)
    excluded = [
        Observation(patient_id=patient, observed_at=earlier, recorded_at=later, **common),
        Observation(patient_id=patient, observed_at=later, recorded_at=earlier, **common),
        Observation(patient_id=patient, observed_at=before, recorded_at=before, **common),
        Observation(patient_id=synthetic_id("patient/1"), observed_at=earlier, recorded_at=earlier, **common),
    ]
    db_session.add_all([valid, *excluded])
    db_session.flush()
    context = retrieve_context(patient, "uniqueterm", db_session, before=before)
    ids = {item.observation.id for item in context.observations}
    assert valid.id in ids
    assert not ids.intersection(record.id for record in excluded)
    assert context.ranked_observation_ids[0] == valid.id
    assert all(item.observation.patient_id == patient for item in context.observations)
    assert all(item.observation.observed_at < before and item.observation.recorded_at < before for item in context.observations)


@pytest.mark.parametrize("latest_status", ["negated", "resolved", "uncertain"])
def test_latest_explicit_state_supersedes_old_positive_code(db_session, latest_status):
    seed(db_session)
    patient = synthetic_id("patient/0")
    for year, status in [(2023, "current"), (2025, latest_status)]:
        when = datetime(year, 1, 1, tzinfo=timezone.utc)
        db_session.add(Observation(patient_id=patient, observation_type="symptom", code="SYNTHETIC-EXACT-CODE",
            text=f"SYNTHETIC source explicitly records {status}.", status=status, observed_at=when, recorded_at=when))
    db_session.flush()
    note = ObservationRead.model_validate(db_session.get(Observation, synthetic_id("note/0/3")))
    context = retrieve_context(patient, note.text, db_session, before=note.observed_at)
    result = StructuredSourceExtractor().extract(context, note)
    selected = [finding for finding in result.findings if finding.finding_type == "SYNTHETIC-EXACT-CODE"]
    assert len(selected) == 1
    assert selected[0].status == ("uncertain" if latest_status == "negated" else latest_status)
    assert selected[0].evidence[0].source_excerpt == f"SYNTHETIC source explicitly records {latest_status}."
