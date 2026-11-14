"""RAG-owned versioned chunk embeddings; shared tables are unchanged."""
from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision = "rag_0001"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("rag_embedding_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("observation_id", sa.Uuid(), sa.ForeignKey("observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_key", sa.String(200), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("observation_id", "model_key", "chunk_index", name="uq_rag_chunk_profile"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_rag_chunk_index"),
        sa.CheckConstraint("(start_offset IS NULL AND end_offset IS NULL) OR "
            "(start_offset >= 0 AND end_offset > start_offset AND start_offset IS NOT NULL AND end_offset IS NOT NULL)", name="ck_rag_chunk_offsets"))
    op.create_index("ix_rag_chunk_model", "rag_embedding_chunks", ["model_key"])


def downgrade():
    op.drop_index("ix_rag_chunk_model", table_name="rag_embedding_chunks")
    op.drop_table("rag_embedding_chunks")
