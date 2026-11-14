"""Deterministic, explicitly synthetic source records; no clinical evaluation."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Encounter, Observation, ObservationEmbedding, Patient, TriggerRule
from app.models.enums import ObservationStatus, ObservationType, Sex
from app.reasoning import vocabulary as v

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


# ---- Colorectal demonstration rules (docs/rulebook-colorectal.md) ------------
# Demonstration only, not clinically validated for Finland. Kept separate from
# seed() so tests that expect no enabled rules keep their fixture.

RULE_VERSION = "nice-2023-demo-1"
FIT_ACTION = "Physician review: consider FIT"
DG56_11 = ("NICE DG56/HTG690", "1.1")


def finding(finding_type: str, **numeric) -> dict:
    leaf = {"kind": "finding", "finding_type": finding_type, "statuses": ["current"]}
    if numeric:
        leaf["numeric"] = numeric
    return leaf


def age(operator: str, years: int) -> dict:
    return {"kind": "patient", "field": v.AGE_YEARS, "numeric": {"operator": operator, "value": years, "unit": "years"}}


def all_of(*conditions) -> dict:
    return {"kind": "group", "operator": "ALL", "conditions": list(conditions)}


def any_of(*conditions) -> dict:
    return {"kind": "group", "operator": "ANY", "conditions": list(conditions)}


# (id, title, expression, priority, recommended_action, (lahde, lahde_kohta))
COLORECTAL_RULES = [
    ("SUO-01", "Abdominal mass", all_of(finding(v.ABDOMINAL_MASS)), "review", FIT_ACTION, DG56_11),
    ("SUO-02", "Change in bowel habit", all_of(finding(v.CHANGE_IN_BOWEL_HABIT)), "review", FIT_ACTION, DG56_11),
    ("SUO-03", "Iron-deficiency anaemia", all_of(finding(v.IRON_DEFICIENCY_ANAEMIA)), "review", FIT_ACTION, DG56_11),
    ("SUO-04", "Age 40+ with weight loss and abdominal pain",
     all_of(age("gte", 40), finding(v.WEIGHT_LOSS), finding(v.ABDOMINAL_PAIN)), "review", FIT_ACTION, DG56_11),
    ("SUO-05", "Age under 50 with rectal bleeding and abdominal pain or weight loss",
     all_of(age("lt", 50), finding(v.RECTAL_BLEEDING), any_of(finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", FIT_ACTION, DG56_11),
    ("SUO-06", "Age 50+ with rectal bleeding, abdominal pain or weight loss",
     all_of(age("gte", 50), any_of(finding(v.RECTAL_BLEEDING), finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", FIT_ACTION, DG56_11),
    ("SUO-07", "Age 60+ with anaemia", all_of(age("gte", 60), finding(v.ANAEMIA)), "review", FIT_ACTION, DG56_11),
    ("SUO-08", "Positive FIT (10 ug/g or more)",
     all_of(finding(v.FIT_RESULT, operator="gte", value=10, unit=v.FIT_UNIT)), "urgent",
     "Urgent physician review: suspected cancer pathway referral", ("NICE DG56/HTG690", "1.2")),
    ("SUO-09", "Rectal mass", all_of(finding(v.RECTAL_MASS)), "urgent",
     "Urgent physician review: consider suspected cancer referral without FIT", ("NICE NG12", "1.3")),
    ("SUO-10", "Negative FIT with ongoing symptoms",
     all_of(finding(v.FIT_RESULT, operator="lt", value=10, unit=v.FIT_UNIT),
            any_of(finding(v.RECTAL_BLEEDING), finding(v.CHANGE_IN_BOWEL_HABIT),
                   finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", "Physician review: safety netting, consider further investigation", ("NICE DG56/HTG690", "1.3–1.4")),
]


def colorectal_rule_rows() -> list[dict]:
    rows = []
    for rule_id, title, expression, priority, action, (lahde, lahde_kohta) in COLORECTAL_RULES:
        rows.append(dict(
            id=synthetic_id(f"rule/colorectal/{rule_id}"),
            name=f"{rule_id}: {title}",
            description=f"{title}. Demonstration rule based on {lahde} {lahde_kohta}; not clinically validated for Finland.",
            conditions={"demonstration": True, "priority": priority, "lahde": lahde, "lahde_kohta": lahde_kohta,
                        "expression": expression},
            recommended_action=action,
            version=RULE_VERSION,
            enabled=True,
        ))
    return rows


def seed_rules(session: Session) -> dict[str, int]:
    """Insert the enabled colorectal demonstration rules; insert-only and idempotent."""
    rows = colorectal_rule_rows()
    for row in rows:
        session.execute(insert(TriggerRule).values(**row).on_conflict_do_nothing())
    return {TriggerRule.__tablename__: len(rows)}


def main() -> None:
    with Session(get_engine()) as session, session.begin():
        counts = seed(session) | seed_rules(session)
    print(f"SYNTHETIC fixture ready (stable IDs, insert-only): {counts}")


if __name__ == "__main__":
    main()
