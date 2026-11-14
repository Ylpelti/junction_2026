"""Persistent nurse-to-physician handoff, referencing existing analyses."""
from alembic import op
import sqlalchemy as sa

revision = "review_0001"
down_revision = "rag_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("physician_review_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("priority", sa.String(6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_by", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id", "patient_id"], ["analysis_runs.id", "analysis_runs.patient_id"]),
        sa.UniqueConstraint("analysis_id", name="uq_physician_review_analysis"),
        sa.CheckConstraint("status = 'pending'", name="review_status"),
        sa.CheckConstraint("priority IN ('urgent', 'review', 'normal')", name="review_priority"),
        sa.CheckConstraint("submitted_by IS NULL OR length(trim(submitted_by)) > 0", name="review_submitter"))
    op.create_index("ix_physician_review_queue", "physician_review_requests", ["status", "created_at", "id"])
    op.create_index("ix_physician_review_patient", "physician_review_requests", ["patient_id"])


def downgrade():
    op.drop_index("ix_physician_review_patient", table_name="physician_review_requests")
    op.drop_index("ix_physician_review_queue", table_name="physician_review_requests")
    op.drop_table("physician_review_requests")
