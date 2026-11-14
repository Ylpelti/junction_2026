"""Persist human demo actions without modifying clinical results."""
from alembic import op
import sqlalchemy as sa

revision = "workflow_0001"
down_revision = "review_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f('ck_physician_review_requests_review_status'), 'physician_review_requests', type_='check')
    op.create_check_constraint('review_status', 'physician_review_requests', "status IN ('pending', 'reviewed')")
    op.create_table('alert_dismissals',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('analysis_id', sa.Uuid(), nullable=False),
        sa.Column('patient_id', sa.Uuid(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('reason_code', sa.String(40), nullable=False),
        sa.Column('comment', sa.String(4000)),
        sa.Column('actor', sa.String(120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id', 'patient_id'], ['analysis_runs.id', 'analysis_runs.patient_id']),
        sa.UniqueConstraint('analysis_id'),
        sa.CheckConstraint("reason_code IN ('already_aware', 'another_diagnosis', 'patient_declined', 'other')", name='dismissal_reason'),
        sa.CheckConstraint('length(trim(actor)) > 0', name='dismissal_actor'))
    op.create_table('physician_decisions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('review_request_id', sa.Uuid(), sa.ForeignKey('physician_review_requests.id'), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('comment', sa.String(4000)),
        sa.Column('actor', sa.String(120), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('review_request_id'),
        sa.CheckConstraint("action IN ('fit_ordered', 'referral_made', 'no_action', 'acknowledged')", name='decision_action'),
        sa.CheckConstraint("status = 'reviewed'", name='decision_status'),
        sa.CheckConstraint('length(trim(actor)) > 0', name='decision_actor'))


def downgrade():
    # Refuse silent loss of recorded human actions. Empty disposable databases
    # remain fully reversible; populated deployments must archive explicitly.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM alert_dismissals) OR EXISTS (SELECT 1 FROM physician_decisions) OR EXISTS (SELECT 1 FROM physician_review_requests WHERE status <> \'pending\')')):
        raise RuntimeError('Archive workflow actions before downgrading workflow_0001.')
    op.drop_table('physician_decisions')
    op.drop_table('alert_dismissals')
    op.drop_constraint(op.f('ck_physician_review_requests_review_status'), 'physician_review_requests', type_='check')
    op.create_check_constraint('review_status', 'physician_review_requests', "status = 'pending'")
