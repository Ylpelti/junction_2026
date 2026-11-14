"""create standardized patient and evidence model

Revision ID: 0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('patients',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('synthetic_name', sa.String(length=200), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('sex', sa.Enum('female', 'male', 'intersex', 'unknown', name='sex', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(synthetic_name)) > 0', name=op.f('ck_patients_name_not_empty')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_patients'))
    )
    op.create_table('trigger_rules',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('recommended_action', sa.Text(), nullable=False),
    sa.Column('version', sa.String(length=80), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.CheckConstraint("conditions ? 'lahde' AND conditions ? 'lahde_kohta' AND jsonb_typeof(conditions->'lahde') = 'string' AND jsonb_typeof(conditions->'lahde_kohta') = 'string' AND length(trim(conditions->>'lahde')) > 0 AND length(trim(conditions->>'lahde_kohta')) > 0", name=op.f('ck_trigger_rules_rule_has_source')),
    sa.CheckConstraint("jsonb_typeof(conditions) = 'object'", name=op.f('ck_trigger_rules_conditions_object')),
    sa.CheckConstraint('length(trim(name)) > 0 AND length(trim(version)) > 0', name=op.f('ck_trigger_rules_name_version_not_empty')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_trigger_rules')),
    sa.UniqueConstraint('name', 'version', name=op.f('uq_trigger_rules_name'))
    )
    op.create_table('analysis_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='analysis_status', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('model_name', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_analysis_runs_patient_id_patients')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_runs')),
    sa.UniqueConstraint('id', 'patient_id', name=op.f('uq_analysis_runs_id'))
    )
    op.create_index('ix_analysis_runs_patient_time', 'analysis_runs', ['patient_id', 'created_at'], unique=False)
    op.create_table('encounters',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('encounter_type', sa.String(length=80), nullable=False),
    sa.Column('organization', sa.String(length=200), nullable=True),
    sa.CheckConstraint('length(trim(encounter_type)) > 0', name=op.f('ck_encounters_type_not_empty')),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_encounters_patient_id_patients')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_encounters')),
    sa.UniqueConstraint('id', 'patient_id', name=op.f('uq_encounters_id'))
    )
    op.create_index('ix_encounters_patient_time', 'encounters', ['patient_id', 'occurred_at'], unique=False)
    op.create_table('clinical_findings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('analysis_run_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('finding_type', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('current', 'historical', 'resolved', 'negated', 'uncertain', name='finding_status', native_enum=False, create_constraint=True), nullable=False),
    sa.CheckConstraint('length(trim(finding_type)) > 0', name=op.f('ck_clinical_findings_type_not_empty')),
    sa.ForeignKeyConstraint(['analysis_run_id', 'patient_id'], ['analysis_runs.id', 'analysis_runs.patient_id'], name=op.f('fk_clinical_findings_analysis_run_id_analysis_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinical_findings')),
    sa.UniqueConstraint('id', 'patient_id', name=op.f('uq_clinical_findings_id'))
    )
    op.create_index('ix_clinical_findings_analysis_run_id', 'clinical_findings', ['analysis_run_id'], unique=False)
    op.create_table('observations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('encounter_id', sa.Uuid(), nullable=True),
    sa.Column('observation_type', sa.Enum('clinical_note', 'symptom', 'laboratory', 'investigation', 'vital_sign', 'diagnosis', 'medication', name='observation_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('code', sa.String(length=100), nullable=True),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('numeric_value', sa.Numeric(precision=18, scale=6), nullable=True),
    sa.Column('unit', sa.String(length=80), nullable=True),
    sa.Column('status', sa.Enum('current', 'historical', 'resolved', 'negated', 'uncertain', 'completed', 'planned', name='observation_status', native_enum=False, create_constraint=True), nullable=True),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("numeric_value IS NULL OR numeric_value != 'NaN'::numeric", name=op.f('ck_observations_finite_value')),
    sa.CheckConstraint('text IS NOT NULL OR numeric_value IS NOT NULL', name=op.f('ck_observations_has_content')),
    sa.CheckConstraint('text IS NULL OR length(trim(text)) > 0', name=op.f('ck_observations_text_not_empty')),
    sa.ForeignKeyConstraint(['encounter_id', 'patient_id'], ['encounters.id', 'encounters.patient_id'], name=op.f('fk_observations_encounter_id_encounters')),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_observations_patient_id_patients')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_observations')),
    sa.UniqueConstraint('id', 'patient_id', name=op.f('uq_observations_id'))
    )
    op.create_index('ix_observations_encounter_id', 'observations', ['encounter_id'], unique=False)
    op.create_index('ix_observations_patient_recorded', 'observations', ['patient_id', 'recorded_at'], unique=False)
    op.create_index('ix_observations_patient_time', 'observations', ['patient_id', 'observed_at'], unique=False)
    op.create_table('trigger_results',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('analysis_run_id', sa.Uuid(), nullable=False),
    sa.Column('trigger_rule_id', sa.Uuid(), nullable=False),
    sa.Column('triggered', sa.Boolean(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('requires_clinician_review', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['analysis_run_id', 'patient_id'], ['analysis_runs.id', 'analysis_runs.patient_id'], name=op.f('fk_trigger_results_analysis_run_id_analysis_runs')),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_trigger_results_patient_id_patients')),
    sa.ForeignKeyConstraint(['trigger_rule_id'], ['trigger_rules.id'], name=op.f('fk_trigger_results_trigger_rule_id_trigger_rules')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_trigger_results')),
    sa.UniqueConstraint('analysis_run_id', 'trigger_rule_id', name=op.f('uq_trigger_results_analysis_run_id')),
    sa.UniqueConstraint('id', 'patient_id', name=op.f('uq_trigger_results_id'))
    )
    op.create_index('ix_trigger_results_patient_id', 'trigger_results', ['patient_id'], unique=False)
    op.create_index('ix_trigger_results_trigger_rule_id', 'trigger_results', ['trigger_rule_id'], unique=False)
    op.create_table('finding_evidence',
    sa.Column('finding_id', sa.Uuid(), nullable=False),
    sa.Column('observation_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('source_excerpt', sa.Text(), nullable=True),
    sa.Column('start_offset', sa.Integer(), nullable=True),
    sa.Column('end_offset', sa.Integer(), nullable=True),
    sa.CheckConstraint('(start_offset IS NULL AND end_offset IS NULL) OR (start_offset IS NOT NULL AND end_offset IS NOT NULL AND start_offset >= 0 AND end_offset > start_offset AND source_excerpt IS NOT NULL)', name=op.f('ck_finding_evidence_valid_offsets')),
    sa.ForeignKeyConstraint(['finding_id', 'patient_id'], ['clinical_findings.id', 'clinical_findings.patient_id'], name=op.f('fk_finding_evidence_finding_id_clinical_findings')),
    sa.ForeignKeyConstraint(['observation_id', 'patient_id'], ['observations.id', 'observations.patient_id'], name=op.f('fk_finding_evidence_observation_id_observations')),
    sa.PrimaryKeyConstraint('finding_id', 'observation_id', name=op.f('pk_finding_evidence'))
    )
    op.create_index('ix_finding_evidence_observation_id', 'finding_evidence', ['observation_id'], unique=False)
    op.create_table('observation_embeddings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('observation_id', sa.Uuid(), nullable=False),
    sa.Column('embedding', Vector(1536), nullable=True),
    sa.Column('embedding_model', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(embedding_model)) > 0', name=op.f('ck_observation_embeddings_model_not_empty')),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], name=op.f('fk_observation_embeddings_observation_id_observations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_observation_embeddings')),
    sa.UniqueConstraint('observation_id', 'embedding_model', name=op.f('uq_observation_embeddings_observation_id'))
    )
    op.create_table('trigger_result_evidence',
    sa.Column('trigger_result_id', sa.Uuid(), nullable=False),
    sa.Column('observation_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['observation_id', 'patient_id'], ['observations.id', 'observations.patient_id'], name=op.f('fk_trigger_result_evidence_observation_id_observations')),
    sa.ForeignKeyConstraint(['trigger_result_id', 'patient_id'], ['trigger_results.id', 'trigger_results.patient_id'], name=op.f('fk_trigger_result_evidence_trigger_result_id_trigger_results')),
    sa.PrimaryKeyConstraint('trigger_result_id', 'observation_id', name=op.f('pk_trigger_result_evidence'))
    )
    op.create_index('ix_trigger_result_evidence_observation_id', 'trigger_result_evidence', ['observation_id'], unique=False)


def downgrade() -> None:
    # Keep the vector extension: other schemas may use it.
    op.drop_index('ix_trigger_result_evidence_observation_id', table_name='trigger_result_evidence')
    op.drop_table('trigger_result_evidence')
    op.drop_table('observation_embeddings')
    op.drop_index('ix_finding_evidence_observation_id', table_name='finding_evidence')
    op.drop_table('finding_evidence')
    op.drop_index('ix_trigger_results_trigger_rule_id', table_name='trigger_results')
    op.drop_index('ix_trigger_results_patient_id', table_name='trigger_results')
    op.drop_table('trigger_results')
    op.drop_index('ix_observations_patient_time', table_name='observations')
    op.drop_index('ix_observations_patient_recorded', table_name='observations')
    op.drop_index('ix_observations_encounter_id', table_name='observations')
    op.drop_table('observations')
    op.drop_index('ix_clinical_findings_analysis_run_id', table_name='clinical_findings')
    op.drop_table('clinical_findings')
    op.drop_index('ix_encounters_patient_time', table_name='encounters')
    op.drop_table('encounters')
    op.drop_index('ix_analysis_runs_patient_time', table_name='analysis_runs')
    op.drop_table('analysis_runs')
    op.drop_table('trigger_rules')
    op.drop_table('patients')
