"""Versioned synthetic demo import/reset. Caller owns the outer transaction."""
import argparse
import json
import os
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import (AlertDismissal, PhysicianDecision, AnalysisRun, ClinicalFinding, Encounter, FindingEvidence,
    Observation, ObservationEmbedding, Patient, PhysicianReviewRequest,
    TriggerResult, TriggerResultEvidence)
from app.rag.storage import EmbeddingChunk
from app.schemas.records import EncounterRead, ObservationRead, PatientRead, Record

DATA = Path(__file__).with_name('demo_data') / 'patients.en-v2.json'
NAMES = {'laine': 'SYNTHETIC Laine EN v2', 'nieminen': 'SYNTHETIC Nieminen EN v2',
         'heikkinen': 'SYNTHETIC Heikkinen EN v2', 'korhonen': 'SYNTHETIC Korhonen EN v2'}
# https://loinc.org/718-7 verified 2026-11-14: blood Hb mass/volume; g/L.
# B-Hb is an existing application alias, not a national numeric code.
LAB_CODES = {('http://loinc.org', '718-7', 'g/L'): 'B-Hb'}


def demo_id(kind, key):
    return uuid5(NAMESPACE_URL, f'https://cancersignal.invalid/demo/en-v2/{kind}/{key}')


class DemoPatient(PatientRead):
    key: str


class DemoEncounter(EncounterRead):
    key: str


class DemoObservation(ObservationRead):
    key: str
    code_system: str | None = None


class Dataset(Record):
    version: Literal[2]
    patients: list[DemoPatient] = Field(min_length=4, max_length=4)
    encounters: list[DemoEncounter] = Field(min_length=1)
    observations: list[DemoObservation] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_graph(self):
        if {p.key for p in self.patients} != set(NAMES):
            raise ValueError('Dataset must contain exactly the four registered demo patients')
        patients = {p.id: p for p in self.patients}
        encounters = {e.id: e for e in self.encounters}
        for kind, rows in [('patient', self.patients), ('encounter', self.encounters),
                           ('observation', self.observations)]:
            if len({r.id for r in rows}) != len(rows):
                raise ValueError(f'Duplicate {kind} IDs')
            for row in rows:
                if row.id != demo_id(kind, row.key):
                    raise ValueError(f'Non-deterministic {kind} ID: {row.key}')
                if kind != 'patient':
                    owner = patients.get(row.patient_id)
                    if owner is None or row.key.split('/')[0] != owner.key:
                        raise ValueError(f'Invalid patient ownership: {row.key}')
        for p in self.patients:
            if p.synthetic_name != NAMES[p.key] or p.birth_date >= p.created_at.date():
                raise ValueError('Invalid synthetic patient metadata')
            if not any(e.patient_id == p.id for e in self.encounters):
                raise ValueError('Every patient needs encounters')
        for e in self.encounters:
            if e.organization != 'SYNTHETIC Health Centre':
                raise ValueError('Encounter must be clearly synthetic')
            if e.occurred_at.date() <= patients[e.patient_id].birth_date:
                raise ValueError('Encounter predates birth')
        for o in self.observations:
            e = encounters.get(o.encounter_id)
            if e is None or e.patient_id != o.patient_id:
                raise ValueError(f'Invalid encounter ownership: {o.key}')
            if not o.text or not o.text.startswith('SYNTHETIC — '):
                raise ValueError('All source observations must be clearly synthetic')
            if o.recorded_at < o.observed_at or o.observed_at < e.occurred_at:
                raise ValueError(f'Invalid measurement/recording chronology: {o.key}')
            if o.observation_type == 'laboratory':
                if (o.code_system, o.code, o.unit) not in LAB_CODES:
                    raise ValueError(f'Unsupported laboratory code/system/unit: {o.key}')
                if o.numeric_value is None or o.numeric_value <= 0 or o.status != 'completed':
                    raise ValueError('Demo Hb requires a positive completed measurement')
            elif o.code_system is not None:
                raise ValueError('Code systems currently supported only for demo labs')
        return self


def load_dataset(path=DATA):
    return Dataset.model_validate_json(Path(path).read_text(encoding='utf-8'))


def rows_for(dataset):
    for model, records in [(Patient, dataset.patients), (Encounter, dataset.encounters),
                           (Observation, dataset.observations)]:
        rows = []
        for record in records:
            row = record.model_dump(exclude={'key', 'code_system'})
            if isinstance(record, DemoObservation) and record.observation_type == 'laboratory':
                row['code'] = LAB_CODES[(record.code_system, record.code, record.unit)]
            rows.append(row)
        yield model, rows


def lock_demo(session):
    session.execute(text('SELECT pg_advisory_xact_lock(731902061114)'))


def check_identity(session, dataset):
    """Fail closed on UUID collisions/reparenting before writing."""
    for model, rows in rows_for(dataset):
        for row in rows:
            existing = session.scalar(select(model).where(model.id == row['id']).with_for_update())
            if existing is None:
                continue
            if model is Patient:
                if existing.synthetic_name != row['synthetic_name'] or existing.created_at != row['created_at']:
                    raise ValueError('Demo patient identity marker mismatch; no changes made')
            elif existing.patient_id != row['patient_id']:
                raise ValueError('Demo record is owned by another patient; no changes made')
            elif model is Observation and existing.encounter_id != row['encounter_id']:
                raise ValueError('Demo observation encounter mismatch; no changes made')


def seed_demo(session: Session, dataset=None):
    dataset = load_dataset() if dataset is None else Dataset.model_validate(dataset.model_dump())
    with session.begin_nested():
        lock_demo(session)
        check_identity(session, dataset)
        counts = {'inserted': 0, 'updated': 0, 'unchanged': 0}
        for model, rows in rows_for(dataset):
            for row in rows:
                existing = session.get(model, row['id'])
                if existing is None:
                    session.add(model(**row))
                    counts['inserted'] += 1
                elif any(getattr(existing, k) != v for k, v in row.items()):
                    raise ValueError('Persisted demo evidence differs; create a new dataset version and identities')
                else:
                    counts['unchanged'] += 1
            session.flush()
    return counts


def reset_demo(session: Session, *, confirm_database: str, environment: str | None = None):
    """Remove session artifacts for registered demo identities, then restore sources."""
    environment = environment if environment is not None else os.getenv('CANCERSIGNAL_DEMO_ENV')
    if environment != 'demo':
        raise ValueError('Reset requires CANCERSIGNAL_DEMO_ENV=demo')
    if not confirm_database or confirm_database != session.scalar(text('SELECT current_database()')):
        raise ValueError('Reset requires --confirm-database matching the connected database name')
    dataset = load_dataset()  # Never accept an arbitrary reset manifest.
    patient_ids = [p.id for p in dataset.patients]
    with session.begin_nested():
        lock_demo(session)
        check_identity(session, dataset)
        session.scalars(select(Patient).where(Patient.id.in_(patient_ids)).order_by(Patient.id).with_for_update()).all()
        observations = select(Observation.id).where(Observation.patient_id.in_(patient_ids))
        for cache in (EmbeddingChunk, ObservationEmbedding):
            session.execute(delete(cache).where(cache.observation_id.in_(observations)))
        review_ids = select(PhysicianReviewRequest.id).where(PhysicianReviewRequest.patient_id.in_(patient_ids))
        session.execute(delete(PhysicianDecision).where(PhysicianDecision.review_request_id.in_(review_ids)))
        session.execute(delete(AlertDismissal).where(AlertDismissal.patient_id.in_(patient_ids)))
        for model in (PhysicianReviewRequest, FindingEvidence, TriggerResultEvidence,
                      ClinicalFinding, TriggerResult, AnalysisRun, Observation, Encounter):
            session.execute(delete(model).where(model.patient_id.in_(patient_ids)))
        session.flush()
        session.expire_all()
        return seed_demo(session, dataset)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'list', 'seed', 'reset'])
    parser.add_argument('--confirm-database')
    args = parser.parse_args()
    try:
        dataset = load_dataset()
        if args.command == 'validate':
            print(f'Valid synthetic dataset: {len(dataset.patients)} patients, '
                  f'{len(dataset.encounters)} encounters, {len(dataset.observations)} observations')
        elif args.command == 'list':
            print(json.dumps({p.key: str(p.id) for p in dataset.patients}, indent=2))
        else:
            with Session(get_engine()) as session, session.begin():
                counts = (reset_demo(session, confirm_database=args.confirm_database)
                          if args.command == 'reset' else seed_demo(session, dataset))
            print(json.dumps(counts))
    except (ValueError, OSError) as error:
        parser.exit(1, f'Demo operation failed: {error}\n')
    except SQLAlchemyError:
        parser.exit(1, 'Demo database operation failed; transaction rolled back. Check configuration and migrations.\n')


if __name__ == '__main__':
    main()
