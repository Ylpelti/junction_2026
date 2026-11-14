"""Load the versioned demo patients (backend/data/patients/demo_patients.json) into PostgreSQL.

    python -m app.db.seed_demo            # from backend/, after migrations
    python -m app.db.seed_demo --check    # validate the JSON only, no database

Insert-only and idempotent: stable uuid5 IDs, existing rows are never changed.
Run `python -m app.db.seed` too if the colorectal rules are not loaded yet.
Synthetic, fictional data only.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.seed import synthetic_id
from app.models import Observation, Patient
from app.models.enums import ObservationStatus, ObservationType, Sex
from app.reasoning.derived_findings import FERRITIN_CODES, FIT_CODES, HB_CODES
from app.reasoning.vocabulary import NOTE_FINDINGS

DEMO_FILE = Path(__file__).resolve().parents[2] / "data" / "patients" / "demo_patients.json"
KNOWN_LAB_CODES = HB_CODES | FERRITIN_CODES | FIT_CODES


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CodedFact(Strict):
    code: str
    quote: str = Field(min_length=1)
    status: Literal["current", "negated", "resolved", "uncertain"]


class DemoRecord(Strict):
    ref: str = Field(min_length=1)
    type: Literal["clinical_note", "laboratory", "investigation"]
    observed_at: AwareDatetime
    text: str | None = None
    code_system: Literal["LOINC", "local"] | None = None
    code: str | None = None
    display: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    status: Literal["completed", "planned", "current", "historical", "uncertain"] | None = None
    coded: list[CodedFact] = Field(default_factory=list)


class Expected(Strict):
    level: Literal["none", "review", "urgent"]
    rules: list[str]
    note: str = ""


class DemoPatient(Strict):
    key: str = Field(pattern=r"^[a-z0-9-]+$")
    synthetic_name: str
    sex: Literal["female", "male"]
    birth_date: date
    eval_case: str | None = None
    today_note_draft: str
    expected_without_llm: Expected
    records: list[DemoRecord]


class LabCode(Strict):
    display: str
    code_system: Literal["LOINC", "local"]
    code: str
    loinc_long_common_name: str | None
    unit: str
    note: str = ""


class DemoFile(Strict):
    version: str
    description: str
    demo_time: AwareDatetime
    code_systems: dict[str, str]
    lab_codes: list[LabCode]
    patients: list[DemoPatient]


def load(path: Path = DEMO_FILE) -> DemoFile:
    data = DemoFile.model_validate_json(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: DemoFile) -> None:
    """Fail loudly on anything the API, evidence checks or rules would reject or misread."""
    keys = [p.key for p in data.patients]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate patient keys.")
    catalogue = {(c.code_system, c.code) for c in data.lab_codes}
    for patient in data.patients:
        where = f"patient {patient.key}"
        if not patient.synthetic_name.upper().startswith("SYNTHETIC "):
            raise ValueError(f"{where}: name must start with 'SYNTHETIC ' (API rule).")
        refs = [r.ref for r in patient.records]
        if len(set(refs)) != len(refs):
            raise ValueError(f"{where}: duplicate record refs.")
        for record in patient.records:
            at = f"{where} {record.ref}"
            if not record.observed_at < data.demo_time:
                raise ValueError(f"{at}: history must be strictly before demo_time.")
            if record.type == "laboratory":
                if record.code is None or record.numeric_value is None or not record.unit or record.code_system is None:
                    raise ValueError(f"{at}: laboratory records need code_system, code, numeric_value and unit.")
                if (record.code_system, record.code) not in catalogue:
                    raise ValueError(f"{at}: lab code {record.code_system} {record.code} is not in lab_codes.")
                if record.code.upper() not in KNOWN_LAB_CODES:
                    raise ValueError(f"{at}: lab code {record.code} is not recognised by derived_findings.py.")
            elif not record.text:
                raise ValueError(f"{at}: {record.type} needs text.")
            for fact in record.coded:
                if record.type != "clinical_note":
                    raise ValueError(f"{at}: only clinical notes can carry coded facts.")
                if fact.code not in NOTE_FINDINGS:
                    raise ValueError(f"{at}: coded fact {fact.code} is not in the shared vocabulary.")
                if fact.quote not in record.text:
                    raise ValueError(f"{at}: quote {fact.quote!r} is not verbatim in the note text.")


def _number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def rows(data: DemoFile) -> tuple[list[dict], list[dict]]:
    patients, observations = [], []
    for patient in data.patients:
        patient_id = synthetic_id(f"demo/{patient.key}/patient")
        patients.append(dict(id=patient_id, synthetic_name=patient.synthetic_name, birth_date=patient.birth_date,
                             sex=Sex(patient.sex), created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)))
        for record in patient.records:
            text = record.text
            if record.type == "laboratory":
                # Human-readable source text; it is also the verbatim evidence quote.
                text = f"{record.display or record.code} {_number(record.numeric_value)} {record.unit} ({record.code_system} {record.code})"
            shared = dict(patient_id=patient_id, encounter_id=None,
                          observed_at=record.observed_at, recorded_at=record.observed_at)
            observations.append(dict(
                **shared, id=synthetic_id(f"demo/{patient.key}/{record.ref}"),
                observation_type=ObservationType(record.type), code=record.code, text=text,
                numeric_value=record.numeric_value, unit=record.unit,
                status=ObservationStatus(record.status) if record.status else None,
            ))
            # Coded symptom facts for the structured demo extractor (latest status per code).
            for index, fact in enumerate(record.coded):
                observations.append(dict(
                    **shared, id=synthetic_id(f"demo/{patient.key}/{record.ref}/coded/{index}/{fact.code}"),
                    observation_type=ObservationType.SYMPTOM, code=fact.code, text=fact.quote,
                    numeric_value=None, unit=None, status=ObservationStatus(fact.status),
                ))
    return patients, observations


def seed_demo(session: Session, path: Path = DEMO_FILE) -> dict[str, int]:
    """Insert the demo patients and their records; never overwrite existing rows."""
    patients, observations = rows(load(path))
    for model, batch in ((Patient, patients), (Observation, observations)):
        for row in batch:
            session.execute(insert(model).values(**row).on_conflict_do_nothing(index_elements=["id"]))
    return {"patients": len(patients), "observations": len(observations)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the versioned synthetic demo patients into PostgreSQL.")
    parser.add_argument("--file", type=Path, default=DEMO_FILE)
    parser.add_argument("--check", action="store_true", help="Validate the JSON only; no database connection.")
    args = parser.parse_args()
    if args.check:
        data = load(args.file)
        patients, observations = rows(data)
        print(f"OK: {args.file} ({len(patients)} patients, {len(observations)} observations)")
        return
    from app.db.session import get_engine
    with Session(get_engine()) as session, session.begin():
        counts = seed_demo(session, args.file)
    print(f"SYNTHETIC demo patients ready (stable IDs, insert-only): {counts}")


if __name__ == "__main__":
    main()
