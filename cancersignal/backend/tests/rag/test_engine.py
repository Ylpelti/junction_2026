from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contracts.clinical_context import RetrievedContext, SourceObservation
from app.contracts.common import PatientScope
from app.rag.embeddings import checked_vector, chunk_source, source_digest, EmbeddingError, LocalE5Embedder
from app.rag.engine import RetrievalEngine, RetrievalError, RetrievalOptions, source_size
from .fakes import FakeEmbedder


def source(patient, year, *, text="SYNTHETIC pain", **extra):
    return SourceObservation(id=uuid4(), patient_id=patient, observation_type="clinical_note", text=text,
        observed_at=datetime(year, 1, 1, tzinfo=timezone.utc), recorded_at=datetime(year, 1, 2, tzinfo=timezone.utc), **extra)


class Repository:
    def __init__(self, records):
        self.records = records
        self.scores = {}
        self.chunks = []
    def sources(self, scope):
        return self.records
    def lexical_scores(self, scope, query):
        return self.scores
    def dense_chunks(self, scope, query, model):
        return self.chunks


def test_old_match_includes_later_negative_and_investigation_without_rewriting_sources():
    patient = uuid4()
    rows = [source(patient, 2020, code="DEMO-CODE"),
            source(patient, 2022, text="SYNTHETIC normal investigation", status="completed"),
            source(patient, 2024, text="SYNTHETIC pain resolved", status="resolved", code="DEMO-CODE")]
    rows[1] = SourceObservation.model_validate(rows[1].model_dump() | {"observation_type": "investigation"})
    repo = Repository(rows)
    repo.scores = {rows[0].id: 10.0}
    engine = RetrievalEngine(repo, options=RetrievalOptions(mode="lexical", top_k=1))
    output = engine.search(scope=PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z"), query="pain")
    assert [hit.source for hit in output.context.retrieved_observations] == rows
    assert output.context.coverage.status == "complete"
    assert output.diagnostics.expansion_reasons[str(rows[2].id)]
    assert RetrievedContext.model_validate_json(output.context.model_dump_json()) == output.context


def test_budget_does_not_publish_old_match_without_its_resolution():
    patient = uuid4()
    rows = [source(patient, 2020, code="X"), source(patient, 2025, code="X", status="resolved")]
    repo = Repository(rows)
    repo.scores = {rows[0].id: 1.0}
    engine = RetrievalEngine(repo, options=RetrievalOptions(mode="lexical", top_k=1, max_source_chars=source_size(rows[0])))
    context = engine(scope=PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z"), query="pain")
    assert not context.retrieved_observations
    assert context.coverage.status == "partial"
    assert "timeline_group_exceeds_budget" in {gap.code for gap in context.coverage.missing_information}


def test_auto_uses_complete_history_when_it_fits_and_complete_never_silently_truncates():
    patient = uuid4()
    rows = [source(patient, 2020)]
    engine = RetrievalEngine(Repository(rows))
    scope = PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z")
    assert engine.search(scope=scope, query="anything").diagnostics.effective_mode == "complete"
    with pytest.raises(RetrievalError, match="exceeds"):
        RetrievalEngine(Repository(rows), options=RetrievalOptions(mode="complete", max_source_chars=1))(scope=scope, query="pain")


def test_scope_is_rechecked_even_if_a_repository_misbehaves():
    patient = uuid4()
    scope = PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z")
    for row in (source(uuid4(), 2020), source(patient, 2027)):
        with pytest.raises(RetrievalError, match="outside"):
            RetrievalEngine(Repository([row]))(scope=scope, query="pain")


def test_hybrid_rrf_preserves_branch_scores_and_ignores_changed_source_embeddings():
    patient = uuid4()
    rows = [source(patient, 2020), source(patient, 2021, text="SYNTHETIC unrelated")]
    repo = Repository(rows)
    repo.scores = {rows[0].id: 5, rows[1].id: 2}
    repo.chunks = [SimpleNamespace(observation_id=rows[1].id, source_digest=source_digest(rows[1]),
                                 distance=0.1, start_offset=0, end_offset=len(rows[1].text)),
                   SimpleNamespace(observation_id=rows[0].id, source_digest="stale", distance=0.2, start_offset=0, end_offset=4)]
    output = RetrievalEngine(repo, embedder=FakeEmbedder(), options=RetrievalOptions(mode="hybrid", expand_timeline=False)).search(
        scope=PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z"), query="pain")
    assert str(rows[1].id) in output.diagnostics.semantic_scores
    assert str(rows[0].id) not in output.diagnostics.semantic_scores
    assert output.diagnostics.fused_scores[str(rows[1].id)] == pytest.approx(1/62 + 1/61)
    assert str(rows[0].id) in output.diagnostics.missing_embedding_ids


def test_chunks_cover_long_source_with_exact_original_offsets_and_no_truncation():
    row = source(uuid4(), 2020, text="SYNTHETIC: abdominal pain. " * 200)
    encoder = FakeEmbedder()
    chunks = chunk_source(row, encoder)
    assert len(chunks) > 1 and chunks[0].start == 0 and chunks[-1].end == len(row.text)
    assert all(left.end >= right.start for left, right in zip(chunks, chunks[1:]))
    for chunk in chunks:
        assert chunk.passage.endswith(row.text[chunk.start:chunk.end])
        assert encoder.token_count("passage: " + chunk.passage) <= encoder.max_tokens
    assert row.text == "SYNTHETIC: abdominal pain. " * 200


@pytest.mark.parametrize("value", [[0.0]*384, [1.0]*383, [float('nan')]*384])
def test_invalid_vectors_fail_explicitly(value):
    with pytest.raises(EmbeddingError):
        checked_vector(value)


def test_identical_numeric_values_do_not_invalidate_cache_due_to_decimal_scale():
    row = source(uuid4(), 2020, numeric_value=Decimal("123.00"), unit="g/L")
    assert source_digest(row) == source_digest(row.model_copy(update={"numeric_value": Decimal("123.000000")}))
    assert source_digest(row) != source_digest(row.model_copy(update={"unit": "g/dL"}))


def test_dense_requires_explicit_adapter_and_lexical_empty_query_is_not_a_risk_result():
    patient = uuid4()
    repo = Repository([source(patient, 2020)])
    scope = PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z")
    with pytest.raises(RetrievalError, match="requires"):
        RetrievalEngine(repo, options=RetrievalOptions(mode="dense"))(scope=scope, query="pain")
    context = RetrievalEngine(repo, options=RetrievalOptions(mode="lexical"))(scope=scope, query="")
    assert not context.retrieved_observations and context.coverage.status == "partial"


def test_long_query_covers_every_character_instead_of_silent_truncation():
    encoder = LocalE5Embedder.__new__(LocalE5Embedder)
    encoder.max_tokens = 20
    encoder.token_count = len
    seen = []
    def encode(texts):
        seen.extend(texts)
        return [checked_vector([1.0]*384) for text in texts]
    encoder._encode = encode
    query = "SYNTHETIC long query. " * 30
    assert len(encoder.query(query)) == 384
    assert len(seen) > 1 and all(len(text) <= encoder.max_tokens for text in seen)
    assert ''.join(text.removeprefix('query: ') for text in seen) == query
