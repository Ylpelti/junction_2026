"""Persist analysis provenance, warnings, and finding uncertainty.

Existing tables lacked fields for stable analysis responses; this additive change
preserves all existing columns and API storage schemas.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analysis_runs", sa.Column("details", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("clinical_findings", sa.Column("uncertainty", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("clinical_findings", "uncertainty")
    op.drop_column("analysis_runs", "details")
