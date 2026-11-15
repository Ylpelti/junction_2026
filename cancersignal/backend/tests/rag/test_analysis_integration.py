"""Synthetic API -> existing RAG -> persisted analysis tests; no external models."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.api.dependencies import get_analysis_pipeline
from app.core.config import get_pipeline_settings
from app.db.seed import seed, synthetic_id
from app.db.seed_rules import seed_rules
from app.db.session import get_session
from app.main import create_app
from app.models import Observation
from app.rag.embeddings import source_digest
from app.rag.extraction import StructuredSourceExtractor
from app.rag.storage import EmbeddingChunk
from app.services import analysis_service
from app.services.history_retrieval import AnalysisRetriever
from app.services.llm_extraction import to_contract_context
from .fakes import FakeEmbedder

pytestmark = pytest.mark.integration
PREFIX = "/api/v1"
PATIENT = synthetic_id("patient/0")


class Capture:
    name = "synthetic-test-capture"

    def __init__(self):
        self.context = None
        self.base = StructuredSourceExtractor()

    def extract(self, context, note):
        self.context = context
        return self.base.extract(context, note)


@pytest.fixture
def api(db_session, monkeypatch):
    monkeypatch.setenv("CANCERSIGNAL_EXTRACTION", "off")
    monkeypatch.setenv("CANCERSIGNAL_RETRIEVAL", "auto")
    get_pipeline_settings.cache_clear()
    seed(db_session)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    capture = Capture()
    pipeline = replace(get_analysis_pipeline(), extractor=capture)
    app.dependency_overrides[get_analysis_pipeline] = lambda: pipeline
    with TestClient(app) as client:
        def configure(retriever):
            app.dependency_overrides[get_analysis_pipeline] = lambda: replace(pipeline, retrieve=retriever)
        yield SimpleNamespace(client=client, capture=capture, configure=configure)
    get_pipeline_settings.cache_clear()


def when(year):
    return datetime(year, 1, 1, tzinfo=timezone.utc)


def note_payload(patient=PATIENT, **changes):
    return dict(patient_id=str(patient), observation_type="clinical_note", text="zzhandoffmarker",
                observed_at="2027-01-01T00:00:00Z", recorded_at="2027-01-01T00:00:00Z") | changes


def analyze(api, patient=PATIENT, **changes):
    response = api.client.post(f"{PREFIX}/patients/{patient}/analyses", json={"note": note_payload(patient, **changes)})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == "completed", result
    return result


def retriever(mode, **changes):
    return AnalysisRetriever(mode=mode, top_k=1, embedder_factory=FakeEmbedder, **changes)


@pytest.mark.parametrize("mode", ["auto", "lexical", "hybrid"])
def test_saved_analysis_resolves_original_evidence_and_keeps_qcancer_unknowns(api, db_session, mode):
    api.configure(retriever(mode))
    result = analyze(api, text="fatigue")
    assert mode in result["provenance"]["retrieval_method"] or mode == "auto"
    assert api.client.get(f"{PREFIX}/analyses/{result['id']}").json() == result
    sources = {row["id"]: row for row in result["source_observations"]}
    for finding in result["findings"]:
        for ref in finding["evidence"]:
            original = sources[ref["observation_id"]]
            assert original["patient_id"] == str(PATIENT)
            assert api.client.get(f"{PREFIX}/observations/{original['id']}").json() == original
            if ref["source_excerpt"] is not None:
                assert original["text"][ref["start_offset"]:ref["end_offset"]] == ref["source_excerpt"]
    prediction = result["predictions"][0]
    assert prediction["value"]["status"] == "insufficient_data"
    assert "binary_factors.new_rectalbleed" in prediction["value"]["missing_inputs"]
    assert "binary_factors.c_hb" not in prediction["value"]["missing_inputs"]
    assert prediction["value"]["any_cancer_risk_percent"] is None
    assert str(synthetic_id("lab/0/3")) in prediction["evidence_observation_ids"]


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize("cutoff, latest", [("2025-01-01T00:00:00Z", "resolved"), ("2027-01-01T00:00:00Z", "negated")])
def test_seeded_resolved_history_retains_supporting_followup_and_investigation(api, mode, cutoff, latest):
    patient = synthetic_id("patient/2")
    api.configure(retriever(mode))
    result = analyze(api, patient, text="Abdominal discomfort", observed_at=cutoff, recorded_at=cutoff)
    rows = {item.observation.id: item.observation for item in api.capture.context.observations}
    assert rows[synthetic_id("symptom/2/0")].status == "current"
    assert rows[synthetic_id("symptom/2/2")].status == "resolved"
    assert synthetic_id("investigation/2") in rows
    symptom = next(f for f in result["findings"] if f["finding_type"] == "SYNTHETIC-SYMPTOM")
    assert symptom["status"] == ("uncertain" if latest == "negated" else latest)
    assert api.capture.context.source_context.retrieval.method in ("full_text", "hybrid")


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_all_lab_trends_reach_models_even_when_no_labs_are_retrieved(api, db_session, monkeypatch, mode):
    anchor = Observation(patient_id=PATIENT, observation_type="clinical_note", text="SYNTHETIC zzhandoffmarker",
                         observed_at=when(2019), recorded_at=when(2019))
    db_session.add(anchor)
    db_session.flush()
    seed_rules(db_session)
    numerical_inputs, qcancer_inputs = [], []
    derive = analysis_service.derive_lab_findings
    build = analysis_service.build_qcancer_input

    def capture_labs(history, **kwargs):
        numerical_inputs.extend(history)
        return derive(history, **kwargs)

    def capture_qcancer(**kwargs):
        value = build(**kwargs)
        qcancer_inputs.append(value)
        return value

    monkeypatch.setattr(analysis_service, "derive_lab_findings", capture_labs)
    monkeypatch.setattr(analysis_service, "build_qcancer_input", capture_qcancer)
    # Dense may nominate a lab with the fake embedder; a one-character budget
    # intentionally omits every whole timeline group in both modes.
    api.configure(retriever(mode, max_source_chars=1))
    result = analyze(api)
    assert api.capture.context.observations == []
    assert [row.numeric_value for row in numerical_inputs] == [132, 125, 112, 108]
    assert {row.id for row in numerical_inputs} == {synthetic_id(f"lab/0/{i}") for i in range(4)}
    assert all(row.patient_id == PATIENT for row in numerical_inputs)
    assert qcancer_inputs[0].binary_factors == {"c_hb": True}
    assert qcancer_inputs[0].bmi is None and qcancer_inputs[0].smoke_cat is None
    assert any(f["finding_type"] == "anaemia" for f in result["findings"])
    assert any(t["rule_name"].startswith("SUO-07") and t["triggered"] for t in result["trigger_results"])
    assert any("selective_history" in gap for gap in result["provenance"]["missing_information"])
    assert set(result["provenance"]["context_observation_ids"]) == {str(row.id) for row in numerical_inputs}
    converted = to_contract_context(api.capture.context, "zzhandoffmarker")
    assert converted is api.capture.context.source_context
    assert converted.coverage.status == "partial" and converted.coverage.eligible_count == 13
    assert converted.retrieval.configuration_digest


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_patient_and_both_strict_time_cutoffs_apply_to_retrieval_models_and_index(api, db_session, monkeypatch, mode):
    forbidden = []
    for owner, event, recorded in ((synthetic_id("patient/1"), 2020, 2020),
                                  (PATIENT, 2027, 2020), (PATIENT, 2020, 2027), (PATIENT, 2028, 2020)):
        row = Observation(patient_id=owner, observation_type="laboratory", code="SYNTHETIC-HB",
                          text="SYNTHETIC fatigue", numeric_value=1, unit="g/L", status="completed",
                          observed_at=when(event), recorded_at=when(recorded))
        db_session.add(row)
        forbidden.append(row)
    db_session.flush()
    forbidden_ids = {row.id for row in forbidden}
    numerical = []
    original = analysis_service.derive_lab_findings
    def capture(history, **kwargs):
        numerical.extend(history)
        return original(history, **kwargs)
    monkeypatch.setattr(analysis_service, "derive_lab_findings", capture)
    api.configure(retriever(mode))
    result = analyze(api, text="fatigue")
    context_ids = {item.observation.id for item in api.capture.context.observations}
    assert not context_ids.intersection(forbidden_ids)
    assert not {row.id for row in numerical}.intersection(forbidden_ids)
    assert all(row.patient_id == PATIENT and row.observed_at < when(2027) and row.recorded_at < when(2027) for row in numerical)
    cache_ids = set(db_session.scalars(select(EmbeddingChunk.observation_id)))
    assert not cache_ids.intersection(forbidden_ids)
    assert result["provenance"]["input_observation_id"] not in {str(identifier) for identifier in cache_ids | context_ids}


def test_new_api_observation_and_modified_observation_are_reindexed_before_next_analysis(api, db_session):
    encoder = FakeEmbedder()
    api.configure(AnalysisRetriever(mode="hybrid", top_k=1, embedder_factory=lambda: encoder))
    analyze(api)
    first_calls = encoder.calls
    payload = note_payload(text="SYNTHETIC zzhandoffmarker new history", observed_at="2025-08-01T00:00:00Z",
                           recorded_at="2025-08-01T00:00:00Z")
    response = api.client.post(f"{PREFIX}/patients/{PATIENT}/observations", json=payload)
    assert response.status_code == 201
    identifier = response.json()["id"]
    second = analyze(api)
    assert encoder.calls == first_calls + 1
    assert identifier in second["provenance"]["context_observation_ids"]
    row = db_session.get(Observation, identifier)
    chunk = db_session.scalar(select(EmbeddingChunk).where(EmbeddingChunk.observation_id == row.id))
    old_digest = chunk.source_digest
    row.text = "SYNTHETIC zzhandoffmarker corrected; symptom resolved."
    row.status = "resolved"
    db_session.commit()
    revised = analyze(api)
    db_session.expire_all()
    chunks = db_session.scalars(select(EmbeddingChunk).where(EmbeddingChunk.observation_id == row.id)).all()
    assert encoder.calls == first_calls + 2
    source = next(item.observation for item in api.capture.context.observations if str(item.observation.id) == identifier)
    assert source.status == "resolved" and source.text == row.text
    assert chunks and all(c.source_digest == source_digest(source) != old_digest for c in chunks)
    assert api.client.get(f"{PREFIX}/analyses/{revised['id']}").json() == revised


@pytest.mark.parametrize("failure", ["loader", "passages", "query", "missing_table", "missing_vectors", "stale_vectors"])
def test_embedding_failures_fall_back_to_lexical_without_losing_analysis_or_partial_cache(api, db_session, failure):
    class Broken(FakeEmbedder):
        def passages(self, texts):
            if failure == "passages" and self.calls:
                raise RuntimeError("SYNTHETIC provider failure")
            return super().passages(texts)

        def query(self, value):
            # passage generation also calls FakeEmbedder.query; fail only at search.
            if failure == "query" and not value.startswith("type:"):
                raise OSError("SYNTHETIC query failure")
            return super().query(value)

    def factory():
        if failure == "loader":
            raise ImportError("SYNTHETIC optional dependency absent")
        return Broken()

    auto_index = failure not in ("missing_vectors", "stale_vectors")
    if failure == "stale_vectors":
        from app.rag.indexing import index_patient
        index_patient(db_session, PATIENT, FakeEmbedder())
        db_session.get(Observation, synthetic_id("note/0/0")).text += " corrected source"
        db_session.commit()
    if failure == "missing_table":
        db_session.execute(text("DROP TABLE rag_embedding_chunks"))
    old_ids = set(db_session.scalars(select(EmbeddingChunk.id))) if failure != "missing_table" else set()
    api.configure(AnalysisRetriever(mode="hybrid", top_k=1, embedder_factory=factory, auto_index=auto_index))
    result = analyze(api, text="fatigue")
    assert result["provenance"]["retrieval_method"].endswith(":lexical")
    assert any("hybrid_unavailable_lexical_fallback" in gap for gap in result["provenance"]["missing_information"])
    assert api.capture.context.source_context.retrieval.method == "full_text"
    assert result["findings"] and result["predictions"][0]["value"]["status"] == "insufficient_data"
    if failure != "missing_table":
        assert set(db_session.scalars(select(EmbeddingChunk.id))) == old_ids
    assert api.client.get(f"{PREFIX}/analyses/{result['id']}").json() == result


def test_baseline_and_selective_modes_keep_identical_qcancer_results(api):
    from app.rag.retrieval import retrieve_context
    api.configure(retrieve_context)
    baseline = analyze(api)
    for mode in ("lexical", "hybrid"):
        api.configure(retriever(mode, max_source_chars=1))
        assert analyze(api)["predictions"] == baseline["predictions"]


def test_later_normal_lab_is_used_even_when_retrieval_cannot_include_it(api, db_session, monkeypatch):
    normal = Observation(patient_id=PATIENT, observation_type="laboratory", code="SYNTHETIC-HB", numeric_value=145,
        unit="g/L", text="SYNTHETIC later haemoglobin report", status="completed", observed_at=when(2026).replace(month=6),
        recorded_at=when(2026).replace(month=6))
    db_session.add(normal)
    db_session.flush()
    values = []
    build = analysis_service.build_qcancer_input
    def capture(**kwargs):
        value = build(**kwargs)
        values.append(value)
        return value
    monkeypatch.setattr(analysis_service, "build_qcancer_input", capture)
    api.configure(retriever("lexical", max_source_chars=1))
    result = analyze(api, text="fatigue")
    assert api.capture.context.observations == []
    assert values[0].binary_factors == {"c_hb": False}  # Explicit normal result, never a missing-value default.
    assert str(normal.id) in result["predictions"][0]["evidence_observation_ids"]
    assert not any(f["finding_type"] == "anaemia" for f in result["findings"])


def test_complete_source_backed_qcancer_inputs_calculate_identically_across_modes(api):
    from app.contracts.qcancer import QCancerPredictors, MALE_BINARY_INPUTS
    from app.rag.context import ExtractionResult
    from app.rag.retrieval import retrieve_context
    factors = sorted(MALE_BINARY_INPUTS - {"c_hb"})
    text = "SYNTHETIC explicit model fixture: BMI=25; alcohol UK units/day=0; smoking=never; " + "; ".join(f"{f}=false" for f in factors)
    class ExplicitSyntheticInputs:
        def extract(self, context, note):
            reference = dict(observation_id=note.id, source_excerpt=note.text)
            predictors = QCancerPredictors.model_validate(dict(
                bmi=dict(value=25, evidence=[reference]),
                alcohol_uk_units_per_day=dict(value=0, evidence=[reference]),
                smoking=dict(status="never", evidence=[reference]),
                binary_factors=[dict(factor=f, value=False, evidence=[reference]) for f in factors]))
            return ExtractionResult(qcancer_predictors=predictors)
    api.capture.base = ExplicitSyntheticInputs()
    note_id = str(uuid4())
    api.configure(retrieve_context)
    baseline = analyze(api, text=text, id=note_id)
    assert baseline["predictions"][0]["value"]["status"] == "calculated"
    for mode in ("lexical", "hybrid"):
        api.configure(retriever(mode, max_source_chars=1))
        # Reuse the same explicit source, so model evidence identity also stays stable.
        response = api.client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": note_id})
        assert response.status_code == 201
        assert response.json()["predictions"] == baseline["predictions"]


def test_partial_retrieval_works_with_the_real_llm_adapter_and_offline_response(api):
    from app.extraction.providers import FixtureProvider
    from app.extraction.service import ClinicalExtractor
    from app.services.llm_extraction import LlmNoteExtractor
    note_id = synthetic_id("note/0/3")
    raw = json.dumps({"findings": [{"finding_type": "documented_observation", "description": "SYNTHETIC fatigue mentioned.",
        "polarity": "present", "temporal_status": "current", "uncertainty": None, "missing_information": [],
        "evidence": [{"observation_id": str(note_id), "source_excerpt": "fatigue", "start_offset": None, "end_offset": None}]}],
        "missing_information": []})
    api.capture.base = LlmNoteExtractor(StructuredSourceExtractor(), clinical=ClinicalExtractor(FixtureProvider(raw)))
    api.configure(retriever("lexical", max_source_chars=1))
    response = api.client.post(f"{PREFIX}/patients/{PATIENT}/analyses", json={"note_observation_id": str(note_id)})
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "completed", result
    assert api.capture.context.source_context.coverage.status == "partial"
    assert any("selective_history" in gap for gap in result["provenance"]["missing_information"])
    assert not any(f["finding_type"] == "documented_observation" for f in result["findings"])
    assert result["provenance"]["semantic_validation"]["rejected"][0]["reason"] == "outside_assertion_grammar"


def test_scope_mismatch_is_rejected_before_any_indexing(api, db_session):
    from app.contracts.common import PatientScope
    from app.rag.indexing import index_patient
    with pytest.raises(ValueError, match="requested patient"):
        index_patient(db_session, PATIENT, FakeEmbedder(), scope=PatientScope(patient_id=uuid4(), as_of=when(2027)))
