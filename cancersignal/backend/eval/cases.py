"""Load backend/eval/cases.json into the backend's own ObservationRead records.

Cases and expected labels are hand-written (see README-cases.md) and are only
read here, never changed. IDs are stable: uuid5 of the case id and record ref.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas.records import ObservationRead

CASES_FILE = Path(__file__).with_name("cases.json")
TODAY_REF = "NOTE-T"


def stable_id(*parts: str) -> UUID:
    return uuid5(NAMESPACE_URL, "https://cancersignal.invalid/eval/v1/" + "/".join(parts))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp without timezone: {value}")
    return parsed


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    category: str
    description: str
    patient_id: UUID
    sex: str
    birth_date: date
    t: datetime
    note: ObservationRead                      # today's clinical note (text), at t
    today_facts: tuple[ObservationRead, ...]   # coded symptom facts of today's note, at t
    history: tuple[ObservationRead, ...]       # earlier raw records: notes, labs, investigations (< t)
    history_facts: tuple[ObservationRead, ...]  # coded symptom facts of earlier notes (< t)
    expected_level: str
    expected_rules: frozenset[str]
    key_sources: tuple[str, ...]
    known_gap: str | None
    refs: dict[UUID, str]                      # observation id -> human-readable ref

    @property
    def labs(self) -> tuple[ObservationRead, ...]:
        return tuple(r for r in self.history if r.observation_type == "laboratory")

    @property
    def today_ids(self) -> frozenset[UUID]:
        return frozenset({self.note.id, *(r.id for r in self.today_facts)})


def _coded_facts(case_id: str, patient_id: UUID, note_ref: str, at: datetime, coded: list[dict]) -> list[ObservationRead]:
    facts = []
    for index, fact in enumerate(coded):
        if fact.get("type") != "symptom":
            raise ValueError(f"{case_id}/{note_ref}: unsupported coded type {fact.get('type')!r}")
        facts.append(ObservationRead(
            id=stable_id(case_id, note_ref, "coded", str(index), fact["code"]),
            patient_id=patient_id, observation_type="symptom", code=fact["code"], text=fact["text"],
            status=fact["status"], observed_at=at, recorded_at=at,
        ))
    return facts


def _history_record(case_id: str, patient_id: UUID, row: dict) -> ObservationRead:
    at = parse_time(row["observed_at"])
    value = row.get("numeric_value")
    return ObservationRead(
        id=stable_id(case_id, row["ref"]), patient_id=patient_id, observation_type=row["type"],
        code=row.get("code"), text=row.get("text"),
        numeric_value=Decimal(str(value)) if value is not None else None,
        unit=row.get("unit"), status=row.get("status"),
        observed_at=at, recorded_at=at,
    )


def load_case(raw: dict, t: datetime) -> Case:
    case_id = raw["id"]
    patient_id = stable_id(case_id, "patient")
    refs: dict[UUID, str] = {}

    note_raw = raw["note"]
    note_at = parse_time(note_raw["observed_at"])
    if note_at != t:
        raise ValueError(f"{case_id}: today's note must be at time t ({t.isoformat()}).")
    note_ref = note_raw.get("ref", TODAY_REF)
    note = ObservationRead(id=stable_id(case_id, note_ref), patient_id=patient_id, observation_type="clinical_note",
                           text=note_raw["text"], observed_at=t, recorded_at=t)
    refs[note.id] = note_ref
    today_facts = _coded_facts(case_id, patient_id, note_ref, t, note_raw.get("coded", []))
    refs.update({fact.id: note_ref for fact in today_facts})

    history, history_facts = [], []
    for row in raw.get("history", []):
        record = _history_record(case_id, patient_id, row)
        history.append(record)
        refs[record.id] = row["ref"]
        if row["type"] == "clinical_note":
            facts = _coded_facts(case_id, patient_id, row["ref"], record.observed_at, row.get("coded", []))
            history_facts.extend(facts)
            refs.update({fact.id: row["ref"] for fact in facts})

    # No data after time t: every history record (and its coded facts) is strictly earlier.
    for record in (*history, *history_facts):
        if not (record.observed_at < t and record.recorded_at < t):
            raise ValueError(f"{case_id}: history record {refs[record.id]} is not strictly before t.")

    patient = raw["patient"]
    expected = raw["expected"]
    return Case(
        id=case_id, split=raw["split"], category=raw["category"], description=raw.get("description", ""),
        patient_id=patient_id, sex=patient["sex"], birth_date=date.fromisoformat(patient["birth_date"]), t=t,
        note=note, today_facts=tuple(today_facts), history=tuple(history), history_facts=tuple(history_facts),
        expected_level=expected["level"], expected_rules=frozenset(expected.get("rules", [])),
        key_sources=tuple(expected.get("key_sources", [])), known_gap=raw.get("known_gap"), refs=refs,
    )


def load_cases(path: Path = CASES_FILE) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    t = parse_time(data["time_t"])
    cases = [load_case(raw, t) for raw in data["cases"]]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate case ids in cases.json.")
    return cases
