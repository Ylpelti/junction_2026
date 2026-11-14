"""Bridge the existing RAG engine to AnalysisPipeline's API-v1 callable.

No clinical interpretation lives here. Optional embedding cache writes and search
share a savepoint so an unavailable cache/provider cannot poison the request.
"""
from functools import lru_cache
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.contracts.common import MissingInformation, PatientScope
from app.rag.context import ContextObservation, RetrievedContext
from app.rag.embeddings import LocalE5Embedder, MODEL_REVISION
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository
from app.rag.retrieval import retrieve_context
from app.schemas.records import ObservationRead


@lru_cache
def local_embedder(cache_dir: Path):
    return LocalE5Embedder(revision=MODEL_REVISION, cache_dir=cache_dir, local_files_only=True)


class AnalysisRetriever:
    def __init__(self, *, mode="auto", top_k=5, max_source_chars=32000,
                 auto_index=True, embedder_factory=None):
        self.options = RetrievalOptions(mode=mode, top_k=top_k, max_source_chars=max_source_chars)
        self.auto_index = auto_index
        self.embedder_factory = embedder_factory

    def __call__(self, patient_id, query, db_session, *, before):
        scope = PatientScope(patient_id=patient_id, as_of=before)
        repository = PatientRepository(db_session)
        warning = None
        if self.options.mode == "hybrid":
            try:
                with db_session.begin_nested():
                    embedder = self.embedder_factory()
                    if self.auto_index:
                        # Same patient AND both exclusive cutoffs, never the input note.
                        index_patient(db_session, patient_id, embedder, scope=scope)
                    output = RetrievalEngine(repository, options=self.options, embedder=embedder).search(scope=scope, query=query)
                    if query.strip() and output.diagnostics.missing_embedding_ids:
                        raise RuntimeError("Incomplete embedding cache.")
            except (ImportError, OSError, RuntimeError, ValueError, SQLAlchemyError):
                # Deliberately exclude provider/driver messages and patient text.
                warning = MissingInformation(code="hybrid_unavailable_lexical_fallback",
                    description="Hybrid embeddings were unavailable or incomplete; PostgreSQL lexical retrieval was used.")
                output = RetrievalEngine(repository, options=RetrievalOptions(mode="lexical",
                    top_k=self.options.top_k, max_source_chars=self.options.max_source_chars)).search(scope=scope, query=query)
        else:
            output = RetrievalEngine(repository, options=self.options).search(scope=scope, query=query)
        context = output.context
        if warning:
            coverage = context.coverage.model_copy(update={
                "missing_information": (*context.coverage.missing_information, warning)})
            context = context.model_copy(update={"coverage": coverage})
        selected = {hit.source.id for hit in context.retrieved_observations}
        ranked = [identifier for value in output.diagnostics.primary_ranked_ids
                  if (identifier := UUID(value)) in selected]
        ranked += [hit.source.id for hit in context.retrieved_observations if hit.source.id not in ranked]
        method = f"{context.retrieval.name}-v{context.retrieval.version}:{output.diagnostics.effective_mode}"
        if context.retrieval.model:
            method += f":{context.retrieval.model}"
        return RetrievedContext(patient_id=patient_id, cutoff=before,
            observations=[ContextObservation(observation=ObservationRead.model_validate(hit.source.model_dump()),
                                             source_excerpt=hit.source.text) for hit in context.retrieved_observations],
            ranked_observation_ids=ranked, retrieval_method=method, source_context=context)


def build_retriever(settings):
    if settings.retrieval == "baseline":
        return retrieve_context
    cache_dir = settings.retrieval_model_cache or Path(sys.prefix) / "rag-model-cache"
    return AnalysisRetriever(mode=settings.retrieval, top_k=settings.retrieval_top_k,
        max_source_chars=settings.retrieval_max_source_chars, auto_index=settings.retrieval_auto_index,
        embedder_factory=lambda: local_embedder(cache_dir))
