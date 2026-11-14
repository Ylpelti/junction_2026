from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.base import Base
from app.db.seed import seed, synthetic_id
from app.models import (
    AnalysisRun, ClinicalFinding, Encounter, FindingEvidence, Observation,
    ObservationEmbedding, Patient, TriggerResult, TriggerResultEvidence, TriggerRule,
)
from app.schemas import records as schemas

pytestmark = pytest.mark.integration


@pytest.fixture
def graph(db_session):
    seed(db_session)
    patient_id = synthetic_id("patient/0")
    other_patient_id = synthetic_id("patient/1")
    run = AnalysisRun(patient_id=patient_id, status="completed", model_name="SYNTHETIC TEST FIXTURE")
    rule = TriggerRule(
        name="SYNTHETIC TEST ONLY", description="Not a clinical rule.",
        conditions={"lahde": "SYNTHETIC TEST FIXTURE", "lahde_kohta": "fixture-v1"},
        recommended_action="Physician review", version="test-1", enabled=False,
    )
    db_session.add_all([run, rule])
    db_session.flush()
    finding = ClinicalFinding(analysis_run_id=run.id, patient_id=patient_id,
                              finding_type="synthetic_example", description="Fixture only", status="uncertain")
    result = TriggerResult(patient_id=patient_id, analysis_run_id=run.id, trigger_rule_id=rule.id,
                           triggered=False, requires_clinician_review=False, explanation="SYNTHETIC fixture; not evaluated.")
    db_session.add_all([finding, result])
    db_session.flush()
    return dict(patient=patient_id, other_patient=other_patient_id, run=run, rule=rule,
                finding=finding, result=result, observation=synthetic_id("note/0/0"),
                other_observation=synthetic_id("note/1/0"))


def test_migrations_create_all_tables_and_foreign_keys(database_engine):
    inspector = inspect(database_engine)
    assert set(Base.metadata.tables).issubset(inspector.get_table_names())
    for name, table in Base.metadata.tables.items():
        assert len(inspector.get_foreign_keys(name)) == len(table.foreign_key_constraints)
    with database_engine.connect() as connection:
        assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


def test_seed_is_reproducible_and_history_is_patient_and_time_scoped(db_session):
    seed(db_session)
    before = set(db_session.scalars(select(Observation.id)))
    seed(db_session)
    assert set(db_session.scalars(select(Observation.id))) == before
    assert len(before) == 98
    assert db_session.scalar(select(func.count()).select_from(Patient)) == 8
    assert db_session.scalar(select(func.count()).select_from(Encounter)) == 32
    assert db_session.scalar(select(func.count()).select_from(ObservationEmbedding)) == 8
    patient = db_session.get(Patient, synthetic_id("patient/0"))
    assert patient.synthetic_name.startswith("SYNTHETIC")
    assert len(patient.encounters) == 4
    assert len(patient.observations) == 12
    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    # Contract example only: no retrieval/ranking component is implemented.
    history = db_session.scalars(select(Observation).where(
        Observation.patient_id == patient.id,
        Observation.observed_at < cutoff,
        Observation.recorded_at < cutoff,
    )).all()
    assert len(history) == 9
    assert {record.observed_at.year for record in history} == {2020, 2022, 2024}
    assert all(record.patient_id == patient.id and record.observed_at < cutoff for record in history)
    assert all("SYNTHETIC" in record.text for record in history)


def test_findings_results_and_evidence_roundtrip_through_schemas(db_session, graph):
    g = graph
    observation = db_session.get(Observation, g["observation"])
    excerpt = observation.text[:16]
    evidence = FindingEvidence(**schemas.FindingEvidenceCreate(
        finding_id=g["finding"].id, observation_id=observation.id, patient_id=g["patient"],
        source_excerpt=excerpt, start_offset=0, end_offset=len(excerpt),
    ).model_dump())
    trigger_evidence = TriggerResultEvidence(**schemas.TriggerResultEvidenceCreate(
        trigger_result_id=g["result"].id, observation_id=observation.id, patient_id=g["patient"],
    ).model_dump())
    db_session.add_all([evidence, trigger_evidence])
    db_session.flush()
    assert g["finding"].evidence[0].observation.id == observation.id
    assert g["result"].evidence[0].observation.id == observation.id
    assert g["result"].analysis_run.patient.id == g["patient"]
    assert evidence.observation.text[evidence.start_offset:evidence.end_offset] == evidence.source_excerpt
    db_session.refresh(g["run"])
    assert g["run"].created_at.utcoffset().total_seconds() == 0
    for model, schema in (
        (Patient, schemas.PatientRead), (Encounter, schemas.EncounterRead),
        (Observation, schemas.ObservationRead), (ObservationEmbedding, schemas.ObservationEmbeddingRead),
        (AnalysisRun, schemas.AnalysisRunRead), (ClinicalFinding, schemas.ClinicalFindingRead),
        (FindingEvidence, schemas.FindingEvidenceRead), (TriggerRule, schemas.TriggerRuleRead),
        (TriggerResult, schemas.TriggerResultRead), (TriggerResultEvidence, schemas.TriggerResultEvidenceRead),
    ):
        record = db_session.scalar(select(model).limit(1))
        assert schema.model_validate(record).model_dump(mode="json")


@pytest.mark.parametrize("case", ["encounter", "finding_run", "result_run", "finding_evidence",
                                 "finding_scope", "result_evidence", "result_scope"])
def test_cross_patient_links_rejected_by_database(db_session, graph, case):
    g = graph
    run_id = g["run"].id
    if case == "result_run":
        # Avoid a duplicate (run, rule) so this specifically tests the scope FK.
        another_run = AnalysisRun(patient_id=g["patient"], status="pending")
        db_session.add(another_run)
        db_session.flush()
        run_id = another_run.id
    invalid = {
        "encounter": lambda: Observation(patient_id=g["other_patient"], encounter_id=synthetic_id("encounter/0/0"),
            observation_type="clinical_note", text="SYNTHETIC", observed_at=datetime.now(timezone.utc)),
        "finding_run": lambda: ClinicalFinding(patient_id=g["other_patient"], analysis_run_id=g["run"].id,
            finding_type="synthetic", description="SYNTHETIC", status="negated"),
        "result_run": lambda: TriggerResult(patient_id=g["other_patient"], analysis_run_id=run_id,
            trigger_rule_id=g["rule"].id, triggered=False, requires_clinician_review=False),
        "finding_evidence": lambda: FindingEvidence(patient_id=g["patient"], finding_id=g["finding"].id,
            observation_id=g["other_observation"]),
        "finding_scope": lambda: FindingEvidence(patient_id=g["other_patient"], finding_id=g["finding"].id,
            observation_id=g["other_observation"]),
        "result_evidence": lambda: TriggerResultEvidence(patient_id=g["patient"], trigger_result_id=g["result"].id,
            observation_id=g["other_observation"]),
        "result_scope": lambda: TriggerResultEvidence(patient_id=g["other_patient"], trigger_result_id=g["result"].id,
            observation_id=g["other_observation"]),
    }[case]()
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(invalid)
        db_session.flush()
    assert error.value.orig.sqlstate == "23503"  # foreign_key_violation


def test_reassigning_linked_observation_to_another_patient_is_rejected(db_session, graph):
    g = graph
    # A source without an encounter isolates the evidence constraint under test.
    source = Observation(patient_id=g["patient"], observation_type="clinical_note", text="SYNTHETIC",
                         observed_at=datetime.now(timezone.utc))
    db_session.add(source)
    db_session.flush()
    db_session.add(FindingEvidence(patient_id=g["patient"], finding_id=g["finding"].id, observation_id=source.id))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(update(Observation).where(Observation.id == source.id).values(patient_id=g["other_patient"]))


def test_database_rejects_invalid_offsets(db_session, graph):
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(FindingEvidence(finding_id=graph["finding"].id, patient_id=graph["patient"],
            observation_id=graph["observation"], source_excerpt="SYNTHETIC", start_offset=5, end_offset=2))
        db_session.flush()
    assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize("source", [{}, {"lahde": None, "lahde_kohta": "fixture"}])
def test_database_rejects_rule_without_source(db_session, source):
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.add(TriggerRule(name="SYNTHETIC", description="Fixture", conditions=source,
            recommended_action="Review", version="1"))
        db_session.flush()
    assert error.value.orig.sqlstate == "23514"


def test_vector_column_rejects_wrong_dimension(db_session, graph):
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text(
            "INSERT INTO observation_embeddings (id, observation_id, embedding_model, embedding) "
            "VALUES (:id, :observation, 'SYNTHETIC-vector-test', '[1,2,3]'::vector)"
        ), {"id": uuid4(), "observation": graph["observation"]})


def test_vector_storage_roundtrip_without_embedding_generation(db_session, graph):
    # Fixed dummy values test the column/serializer only, not a model or vector search.
    record = ObservationEmbedding(observation_id=graph["observation"],
        embedding_model="SYNTHETIC-STORAGE-TEST", embedding=[0.0] * 1536)
    db_session.add(record)
    db_session.flush()
    db_session.refresh(record)
    read = schemas.ObservationEmbeddingRead.model_validate(record)
    assert read.embedding == [0.0] * 1536
