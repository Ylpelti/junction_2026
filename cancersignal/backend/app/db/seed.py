"""Deterministic, explicitly synthetic source records; no clinical evaluation."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Encounter, Observation, ObservationEmbedding, Patient
from app.models.enums import ObservationStatus, ObservationType, Sex

# Each entry is a fictional source history, not a prediction or ground-truth label.
HISTORIES = [
    ("Repeated fatigue", ["Fatigue reported.", "Fatigue reported again; blood test requested.",
                          "Fatigue persists; follow-up date not documented.", "New fatigue note; prior follow-up outcome unknown."],
     ["current", "current", "uncertain", "uncertain"], [132, 125, 112, 108]),
    ("Routine visits", ["Routine visit; no bowel symptoms reported.", "Denies blood in stool.",
                        "Routine review; no fatigue reported.", "No new symptoms reported."],
     ["negated", "negated", "negated", "negated"], [145, 146, 144, 145]),
    ("Resolved symptoms", ["Abdominal discomfort reported.", "Investigation completed; source report records no abnormality.",
                           "Previous discomfort resolved.", "No recurrence reported."],
     ["current", "historical", "resolved", "negated"], [138, 140, 139, 141]),
    ("Uncertain follow-up", ["Intermittent bowel change reported.", "Symptoms mentioned again; investigation planned.",
                             "No investigation result available in this record.", "Patient unsure whether planned follow-up occurred."],
     ["current", "planned", "uncertain", "uncertain"], [139, 137, 134, 133]),
    ("Repeated discomfort", ["Intermittent abdominal discomfort.", "Similar discomfort mentioned at later visit.",
                             "Prior completed investigation recorded; discomfort persists.", "Symptoms reported as unchanged."],
     ["current", "current", "current", "current"], [142, 141, 142, 140]),
    ("Transient fatigue", ["Brief fatigue after disrupted sleep.", "Fatigue resolved according to source note.",
                           "Denies ongoing fatigue.", "Routine visit; no new symptoms reported."],
     ["current", "resolved", "negated", "negated"], [136, 137, 139, 138]),
    ("Mixed reports", ["Occasional bowel change; significance uncertain.", "Denies blood in stool; bowel pattern uncertain.",
                       "Bowel change reported again.", "Follow-up suggested; outcome not in available records."],
     ["uncertain", "negated", "current", "uncertain"], [140, 139, 138, 137]),
    ("Normal history", ["Routine check; no symptoms reported.", "Routine check; no bowel symptoms.",
                        "No fatigue or bleeding reported.", "Routine check; no new symptoms."],
     ["negated", "negated", "negated", "negated"], [148, 147, 149, 148]),
]


def synthetic_id(key: str):
    return uuid5(NAMESPACE_URL, f"https://cancersignal.invalid/synthetic/v1/{key}")


def seed(session: Session) -> dict[str, int]:
    """Insert missing fixture IDs atomically; never overwrite existing observations."""
    patients, encounters, observations, embeddings = [], [], [], []
    for index, (scenario, notes, statuses, hemoglobin) in enumerate(HISTORIES):
        patient_id = synthetic_id(f"patient/{index}")
        patients.append(dict(
            id=patient_id, synthetic_name=f"SYNTHETIC Patient {index + 1:02d}",
            birth_date=date(1950 + index * 4, 3, 10), sex=Sex.FEMALE if index % 2 else Sex.MALE,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ))
        for visit, year in enumerate((2020, 2022, 2024, 2026)):
            occurred_at = datetime(year, 2, 12, 9, tzinfo=timezone.utc)
            encounter_id = synthetic_id(f"encounter/{index}/{visit}")
            encounters.append(dict(
                id=encounter_id, patient_id=patient_id, occurred_at=occurred_at,
                encounter_type="synthetic_primary_care", organization="SYNTHETIC Clinic",
            ))
            shared = dict(patient_id=patient_id, encounter_id=encounter_id,
                          observed_at=occurred_at, recorded_at=occurred_at + timedelta(hours=1))
            note_id = synthetic_id(f"note/{index}/{visit}")
            observations.append(dict(
                **shared, id=note_id, observation_type=ObservationType.CLINICAL_NOTE,
                text=f"SYNTHETIC SOURCE NOTE — {scenario}. {notes[visit]}",
                status=ObservationStatus(statuses[visit]),
            ))
            observations.append(dict(
                **shared, id=synthetic_id(f"symptom/{index}/{visit}"),
                observation_type=ObservationType.SYMPTOM, code="SYNTHETIC-SYMPTOM",
                text=f"SYNTHETIC symptom record: {notes[visit]}",
                status=ObservationStatus(statuses[visit]),
            ))
            observations.append(dict(
                **shared, id=synthetic_id(f"lab/{index}/{visit}"),
                observation_type=ObservationType.LABORATORY, code="SYNTHETIC-HB",
                text="SYNTHETIC laboratory report: haemoglobin measurement.",
                numeric_value=Decimal(hemoglobin[visit]), unit="g/L", status=ObservationStatus.COMPLETED,
            ))
            if visit == 1 and index in (2, 4):
                observations.append(dict(
                    **shared, id=synthetic_id(f"investigation/{index}"),
                    observation_type=ObservationType.INVESTIGATION, code="SYNTHETIC-INVESTIGATION",
                    text="SYNTHETIC original investigation report: completed; no abnormality documented.",
                    status=ObservationStatus.COMPLETED,
                ))
            if visit == 3:
                embeddings.append(dict(
                    id=synthetic_id(f"embedding/{index}"), observation_id=note_id,
                    embedding=None, embedding_model="pending-1536",
                    created_at=occurred_at + timedelta(hours=2),
                ))

    counts = {}
    for model, rows in ((Patient, patients), (Encounter, encounters),
                        (Observation, observations), (ObservationEmbedding, embeddings)):
        # Insert separately so heterogeneous observation fields retain their nulls.
        for row in rows:
            session.execute(insert(model).values(**row).on_conflict_do_nothing(index_elements=["id"]))
        counts[model.__tablename__] = len(rows)
    return counts


def main() -> None:
    # Imported here, not at module level: RAG imports this module and must stay
    # independent of app.reasoning (tests/rag/test_independence.py).
    from app.db.seed_rules import seed_rules

    with Session(get_engine()) as session, session.begin():
        counts = seed(session) | seed_rules(session)
    print(f"SYNTHETIC fixture ready (stable IDs, insert-only): {counts}")


if __name__ == "__main__":
    main()
