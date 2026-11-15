from datetime import datetime, timezone

import pytest
from sqlalchemy import select, func, inspect

from app.contracts.common import PatientScope
from app.db.seed import seed, synthetic_id
from app.models import Observation
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository
from app.rag.storage import EmbeddingChunk
from .fakes import FakeEmbedder

pytestmark = pytest.mark.integration


@pytest.fixture
def records(db_session):
    seed(db_session)
    patient = synthetic_id("patient/0")
    repo = PatientRepository(db_session)
    return patient, repo, PatientScope(patient_id=patient, as_of="2026-01-01T00:00:00Z")


def test_postgres_lexical_stemming_codes_numbers_and_patient_filter(db_session, records):
    patient, repo, scope = records
    for owner in (patient, synthetic_id("patient/1")):
        db_session.add(Observation(patient_id=owner, observation_type="clinical_note", text="SYNTHETIC: Investigations planned.",
            observed_at=datetime(2021, 1, 1, tzinfo=timezone.utc), recorded_at=datetime(2021, 1, 1, tzinfo=timezone.utc)))
    db_session.flush()
    scores = repo.lexical_scores(scope, "investigation")
    assert len(scores) == 1
    source = db_session.get(Observation, next(iter(scores)))
    assert source.patient_id == patient
    assert repo.lexical_scores(scope, "SYNTHETIC-HB 112 g/L")
    assert synthetic_id('lab/0/2') in repo.lexical_scores(scope, "112")
    assert repo.lexical_scores(scope, "'); DROP TABLE observations; --") is not None


def test_complete_numeric_history_is_independent_of_selective_retrieval(records):
    patient, repo, scope = records
    structured = repo.structured(scope=scope)
    assert structured.coverage.status == "complete"
    assert len(structured.observations) == 3
    assert {row.observed_at.year for row in structured.observations} == {2020, 2022, 2024}
    assert all(row.patient_id == patient for row in structured.observations)


def test_embedding_reuse_reindex_changed_content_and_profile_isolation(db_session, records):
    patient, repo, scope = records
    encoder = FakeEmbedder()
    first = index_patient(db_session, patient, encoder)
    calls = encoder.calls
    again = index_patient(db_session, patient, encoder)
    assert again['indexed_observations'] == 0 and encoder.calls == calls
    assert again['reused_observations'] == first['indexed_observations'] == 12
    row = db_session.get(Observation, synthetic_id('note/0/0'))
    row.text += ' SYNTHETIC revised source.'
    db_session.flush()
    output = RetrievalEngine(repo, embedder=encoder, options=RetrievalOptions(mode='dense')).search(scope=scope, query='fatigue')
    assert str(row.id) in output.diagnostics.missing_embedding_ids
    changed = index_patient(db_session, patient, encoder)
    assert changed['indexed_observations'] == 1
    encoder.model_key = 'SYNTHETIC-TEST-EMBEDDER-v2'
    assert index_patient(db_session, patient, encoder)['indexed_observations'] == 12
    assert db_session.scalar(select(func.count()).select_from(EmbeddingChunk)) == 24


def test_dense_and_hybrid_use_pgvector_with_scope_before_ranking(db_session, records):
    patient, repo, scope = records
    encoder = FakeEmbedder()
    index_patient(db_session, patient, encoder)
    index_patient(db_session, synthetic_id('patient/1'), encoder)
    for mode in ('dense', 'hybrid'):
        output = RetrievalEngine(repo, embedder=encoder, options=RetrievalOptions(mode=mode)).search(scope=scope, query='fatigue')
        assert output.context.retrieved_observations
        assert all(hit.source.patient_id == patient and hit.source.observed_at < scope.as_of
                   for hit in output.context.retrieved_observations)
        assert all(str(synthetic_id('note/1/0')) != identifier for identifier in output.diagnostics.semantic_scores)


def test_rag_owned_migration_and_cache_failure_are_isolated(db_session, records):
    patient, repo, scope = records
    inspector = inspect(db_session.connection())
    columns = {column['name']: column for column in inspector.get_columns('rag_embedding_chunks')}
    assert columns['embedding']['type'].dim == 384
    assert inspector.get_foreign_keys('rag_embedding_chunks')[0]['referred_table'] == 'observations'
    encoder = FakeEmbedder()
    index_patient(db_session, patient, encoder)
    original_ids = set(db_session.scalars(select(EmbeddingChunk.id)))
    class FailingEmbedder(FakeEmbedder):
        def passages(self, texts):
            if self.calls:
                raise RuntimeError('SYNTHETIC embedding failure')
            return super().passages(texts)
    with pytest.raises(RuntimeError):
        index_patient(db_session, patient, FailingEmbedder(), force=True)
    assert set(db_session.scalars(select(EmbeddingChunk.id))) == original_ids
