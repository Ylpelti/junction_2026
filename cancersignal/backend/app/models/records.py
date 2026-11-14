from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AnalysisStatus, FindingStatus, ObservationStatus, ObservationType, Sex

EMBEDDING_DIMENSION = 1536


def enum_column(enum_class: type, name: str) -> Enum:
    # VARCHAR + CHECK keeps migrations straightforward and stores the public values.
    return Enum(enum_class, name=name, native_enum=False, create_constraint=True,
                values_callable=lambda members: [member.value for member in members])


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (CheckConstraint("length(trim(synthetic_name)) > 0", name="name_not_empty"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    synthetic_name: Mapped[str] = mapped_column(String(200))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(enum_column(Sex, "sex"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    encounters: Mapped[list["Encounter"]] = relationship(viewonly=True)
    observations: Mapped[list["Observation"]] = relationship(viewonly=True)
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(viewonly=True)
    trigger_results: Mapped[list["TriggerResult"]] = relationship(viewonly=True)


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        Index("ix_encounters_patient_time", "patient_id", "occurred_at"),
        CheckConstraint("length(trim(encounter_type)) > 0", name="type_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    encounter_type: Mapped[str] = mapped_column(String(80))
    organization: Mapped[str | None] = mapped_column(String(200))

    patient: Mapped[Patient] = relationship(viewonly=True)
    observations: Mapped[list["Observation"]] = relationship(viewonly=True)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        ForeignKeyConstraint(["encounter_id", "patient_id"], ["encounters.id", "encounters.patient_id"]),
        Index("ix_observations_patient_time", "patient_id", "observed_at"),
        Index("ix_observations_patient_recorded", "patient_id", "recorded_at"),
        Index("ix_observations_encounter_id", "encounter_id"),
        CheckConstraint("text IS NOT NULL OR numeric_value IS NOT NULL", name="has_content"),
        CheckConstraint("text IS NULL OR length(trim(text)) > 0", name="text_not_empty"),
        CheckConstraint("numeric_value IS NULL OR numeric_value != 'NaN'::numeric", name="finite_value"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    encounter_id: Mapped[UUID | None] = mapped_column(Uuid)
    observation_type: Mapped[ObservationType] = mapped_column(enum_column(ObservationType, "observation_type"))
    code: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str | None] = mapped_column(Text)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[ObservationStatus | None] = mapped_column(enum_column(ObservationStatus, "observation_status"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    patient: Mapped[Patient] = relationship(viewonly=True)
    encounter: Mapped[Encounter | None] = relationship(viewonly=True)
    embeddings: Mapped[list["ObservationEmbedding"]] = relationship(viewonly=True)
    finding_evidence: Mapped[list["FindingEvidence"]] = relationship(viewonly=True)
    trigger_evidence: Mapped[list["TriggerResultEvidence"]] = relationship(viewonly=True)


class ObservationEmbedding(Base):
    __tablename__ = "observation_embeddings"
    __table_args__ = (
        UniqueConstraint("observation_id", "embedding_model"),
        CheckConstraint("length(trim(embedding_model)) > 0", name="model_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    observation_id: Mapped[UUID] = mapped_column(ForeignKey("observations.id"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    embedding_model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    observation: Mapped[Observation] = relationship(viewonly=True)


class TriggerRule(Base):
    __tablename__ = "trigger_rules"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        CheckConstraint("length(trim(name)) > 0 AND length(trim(version)) > 0", name="name_version_not_empty"),
        CheckConstraint("jsonb_typeof(conditions) = 'object'", name="conditions_object"),
        CheckConstraint(
            "conditions ? 'lahde' AND conditions ? 'lahde_kohta' AND "
            "jsonb_typeof(conditions->'lahde') = 'string' AND "
            "jsonb_typeof(conditions->'lahde_kohta') = 'string' AND "
            "length(trim(conditions->>'lahde')) > 0 AND length(trim(conditions->>'lahde_kohta')) > 0",
            name="rule_has_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    conditions: Mapped[dict] = mapped_column(JSONB)
    recommended_action: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    results: Mapped[list["TriggerResult"]] = relationship(viewonly=True)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        Index("ix_analysis_runs_patient_time", "patient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[AnalysisStatus] = mapped_column(enum_column(AnalysisStatus, "analysis_status"))
    model_name: Mapped[str | None] = mapped_column(String(200))

    patient: Mapped[Patient] = relationship(viewonly=True)
    findings: Mapped[list["ClinicalFinding"]] = relationship(viewonly=True)
    trigger_results: Mapped[list["TriggerResult"]] = relationship(viewonly=True)


class ClinicalFinding(Base):
    __tablename__ = "clinical_findings"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        ForeignKeyConstraint(["analysis_run_id", "patient_id"], ["analysis_runs.id", "analysis_runs.patient_id"]),
        Index("ix_clinical_findings_analysis_run_id", "analysis_run_id"),
        CheckConstraint("length(trim(finding_type)) > 0", name="type_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    finding_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[FindingStatus] = mapped_column(enum_column(FindingStatus, "finding_status"))

    analysis_run: Mapped[AnalysisRun] = relationship(viewonly=True)
    evidence: Mapped[list["FindingEvidence"]] = relationship(viewonly=True)


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["finding_id", "patient_id"], ["clinical_findings.id", "clinical_findings.patient_id"]),
        ForeignKeyConstraint(["observation_id", "patient_id"], ["observations.id", "observations.patient_id"]),
        Index("ix_finding_evidence_observation_id", "observation_id"),
        CheckConstraint(
            "(start_offset IS NULL AND end_offset IS NULL) OR "
            "(start_offset IS NOT NULL AND end_offset IS NOT NULL AND "
            "start_offset >= 0 AND end_offset > start_offset AND source_excerpt IS NOT NULL)",
            name="valid_offsets",
        ),
    )

    finding_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    observation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)

    finding: Mapped[ClinicalFinding] = relationship(viewonly=True)
    observation: Mapped[Observation] = relationship(viewonly=True)


class TriggerResult(Base):
    __tablename__ = "trigger_results"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        UniqueConstraint("analysis_run_id", "trigger_rule_id"),
        ForeignKeyConstraint(["analysis_run_id", "patient_id"], ["analysis_runs.id", "analysis_runs.patient_id"]),
        Index("ix_trigger_results_patient_id", "patient_id"),
        Index("ix_trigger_results_trigger_rule_id", "trigger_rule_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid)
    trigger_rule_id: Mapped[UUID] = mapped_column(ForeignKey("trigger_rules.id"))
    triggered: Mapped[bool] = mapped_column(Boolean)
    explanation: Mapped[str | None] = mapped_column(Text)
    requires_clinician_review: Mapped[bool] = mapped_column(Boolean)

    patient: Mapped[Patient] = relationship(viewonly=True)
    analysis_run: Mapped[AnalysisRun] = relationship(viewonly=True)
    trigger_rule: Mapped[TriggerRule] = relationship(viewonly=True)
    evidence: Mapped[list["TriggerResultEvidence"]] = relationship(viewonly=True)


class TriggerResultEvidence(Base):
    __tablename__ = "trigger_result_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["trigger_result_id", "patient_id"], ["trigger_results.id", "trigger_results.patient_id"]),
        ForeignKeyConstraint(["observation_id", "patient_id"], ["observations.id", "observations.patient_id"]),
        Index("ix_trigger_result_evidence_observation_id", "observation_id"),
    )

    trigger_result_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    observation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[UUID] = mapped_column(Uuid)

    trigger_result: Mapped[TriggerResult] = relationship(viewonly=True)
    observation: Mapped[Observation] = relationship(viewonly=True)
