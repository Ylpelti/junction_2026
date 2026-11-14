"""API retrieval configuration and rich-context bridge work without PostgreSQL."""
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.clinical_context import SourceObservation
from app.core.config import PipelineSettings
from app.rag.retrieval import retrieve_context
from app.services import history_retrieval
from app.services.history_retrieval import AnalysisRetriever, build_retriever
from app.services.llm_extraction import to_contract_context


def test_modes_and_limits_are_explicit_and_baseline_remains_available():
    settings = PipelineSettings(_env_file=None, retrieval="baseline")
    assert build_retriever(settings) is retrieve_context
    for mode in ("auto", "lexical", "hybrid"):
        configured = build_retriever(PipelineSettings(_env_file=None, retrieval=mode,
            retrieval_top_k=2, retrieval_max_source_chars=1000, retrieval_auto_index=False))
        assert configured.options.mode == mode
        assert configured.options.top_k == 2 and configured.options.max_source_chars == 1000
        assert configured.auto_index is False


@pytest.mark.parametrize("field,value", [("retrieval", "imaginary"), ("retrieval_top_k", 0), ("retrieval_max_source_chars", 0)])
def test_invalid_configuration_is_rejected(field, value):
    with pytest.raises(ValidationError):
        PipelineSettings(_env_file=None, **{field: value})


@pytest.mark.parametrize("mode,method", [("auto", "structured"), ("lexical", "full_text"), ("hybrid", "full_text")])
def test_adapter_preserves_sources_coverage_and_provenance_offline(monkeypatch, mode, method):
    source = SourceObservation(id=uuid4(), patient_id=uuid4(), observation_type="symptom", code="DEMO",
        text="SYNTHETIC pain resolved", status="resolved", observed_at="2024-01-01T00:00:00Z", recorded_at="2024-01-01T00:00:00Z")
    repository = SimpleNamespace(sources=lambda scope: (source,), lexical_scores=lambda scope, query: {source.id: 1.0})
    monkeypatch.setattr(history_retrieval, "PatientRepository", lambda session: repository)
    calls = []
    def unavailable():
        calls.append(True)
        raise ImportError("SYNTHETIC optional embedding library absent")
    context = AnalysisRetriever(mode=mode, embedder_factory=unavailable)(source.patient_id, "pain",
        SimpleNamespace(begin_nested=nullcontext), before=source.observed_at.replace(year=2026))
    assert bool(calls) == (mode == "hybrid")
    assert context.observations[0].observation.model_dump() == source.model_dump()
    assert context.observations[0].source_excerpt == source.text
    assert context.ranked_observation_ids == [source.id]
    shared = to_contract_context(context, "pain")
    assert shared is context.source_context
    assert shared.retrieval.method == method and shared.retrieval.configuration_digest
    assert shared.coverage.status == "complete"
    assert bool(shared.coverage.missing_information) == (mode == "hybrid")
