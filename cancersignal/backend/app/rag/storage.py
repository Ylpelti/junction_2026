"""RAG-owned embedding cache. No changes to shared observation/embedding models."""
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models import Observation


class RagBase(DeclarativeBase):
    pass


class EmbeddingChunk(RagBase):
    __tablename__ = "rag_embedding_chunks"
    __table_args__ = (
        UniqueConstraint("observation_id", "model_key", "chunk_index", name="uq_rag_chunk_profile"),
        CheckConstraint("chunk_index >= 0", name="ck_rag_chunk_index"),
        CheckConstraint("(start_offset IS NULL AND end_offset IS NULL) OR "
                        "(start_offset >= 0 AND end_offset > start_offset AND start_offset IS NOT NULL AND end_offset IS NOT NULL)",
                        name="ck_rag_chunk_offsets"),
        Index("ix_rag_chunk_model", "model_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    observation_id: Mapped[UUID] = mapped_column(ForeignKey(Observation.id, ondelete="CASCADE"))
    model_key: Mapped[str] = mapped_column(String(200))
    source_digest: Mapped[str] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
