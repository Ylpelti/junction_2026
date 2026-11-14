"""Idempotent per-patient indexing. Caller owns commit/rollback."""
from sqlalchemy import delete, select

from app.contracts.clinical_context import SourceObservation
from app.models import Observation, Patient
from app.rag.embeddings import EmbeddingError, checked_vector, chunk_source, source_digest
from app.rag.repository import PatientNotFound, scoped_observations
from app.rag.storage import EmbeddingChunk


def index_patient(session, patient_id, embedder, *, force=False, scope=None):
    if scope is not None and scope.patient_id != patient_id:
        raise ValueError("Indexing scope must belong to the requested patient.")
    if session.get(Patient, patient_id) is None:
        raise PatientNotFound("Synthetic patient does not exist.")
    counts = {"indexed_observations": 0, "reused_observations": 0, "chunks_written": 0}
    # Lock source rows in UUID order: concurrent indexers serialize per source.
    query = scoped_observations(scope) if scope is not None else select(Observation).where(Observation.patient_id == patient_id)
    records = session.scalars(query.order_by(Observation.id).with_for_update()).all()
    with session.begin_nested():
        for record in records:
            source = SourceObservation.model_validate(record)
            digest = source_digest(source)
            chunks = chunk_source(source, embedder)
            existing = session.scalars(select(EmbeddingChunk).where(
                EmbeddingChunk.observation_id == source.id, EmbeddingChunk.model_key == embedder.model_key)
                .order_by(EmbeddingChunk.chunk_index)).all()
            valid = len(existing) == len(chunks) and all(
                row.source_digest == digest and row.chunk_index == index
                and (row.start_offset, row.end_offset) == (chunk.start, chunk.end)
                for index, (row, chunk) in enumerate(zip(existing, chunks)))
            if valid and not force:
                counts["reused_observations"] += 1
                continue
            vectors = embedder.passages([chunk.passage for chunk in chunks])
            if len(vectors) != len(chunks):
                raise EmbeddingError("Embedding provider returned the wrong number of vectors.")
            vectors = [checked_vector(vector) for vector in vectors]
            session.execute(delete(EmbeddingChunk).where(EmbeddingChunk.observation_id == source.id,
                                                        EmbeddingChunk.model_key == embedder.model_key))
            session.add_all(EmbeddingChunk(observation_id=source.id, model_key=embedder.model_key,
                source_digest=digest, chunk_index=index, start_offset=chunk.start, end_offset=chunk.end,
                embedding=vector) for index, (chunk, vector) in enumerate(zip(chunks, vectors)))
            session.flush()
            counts["indexed_observations"] += 1
            counts["chunks_written"] += len(chunks)
    return counts
