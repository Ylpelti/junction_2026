"""Offline tests for wiring app.extraction into the analysis pipeline (no network, no DB)."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

import pytest

from app.api import dependencies
from app.core.config import get_pipeline_settings
from app.extraction.providers import FixtureProvider
from app.extraction.service import ClinicalExtractor
from app.rag.context import ContextObservation, RetrievedContext
from app.rag.extraction import StructuredSourceExtractor
from app.schemas.records import ObservationRead
from app.services.errors import PipelineError
from app.services.llm_extraction import LlmNoteExtractor, build_from_settings, to_contract_context

PATIENT = uuid4()
CUTOFF = datetime(2026, 11, 14, 8, 45, tzinfo=timezone.utc)
EARLIER = datetime(2026, 8, 14, 9, tzinfo=timezone.utc)
NOTE_TEXT = "SYNTHETIC: verta ulosteessa viime viikolla. Ei vatsakipua."


def observation(**fields):
    base = dict(id=uuid4(), patient_id=PATIENT, observed_at=EARLIER, recorded_at=EARLIER)
    return ObservationRead(**(base | fields))


def legacy_context(*rows):
    return RetrievedContext(patient_id=PATIENT, cutoff=CUTOFF,
        observations=[ContextObservation(observation=row, source_excerpt=row.text) for row in rows],
        ranked_observation_ids=[row.id for row in rows])


def note():
    return observation(observation_type="clinical_note", text=NOTE_TEXT, observed_at=CUTOFF, recorded_at=CUTOFF)


def lab():
    return observation(observation_type="laboratory", code="B-Hb", text="SYNTHETIC Hb report.",
                       numeric_value=Decimal("108"), unit="g/l", status="completed")


def response(note_id, *findings):
    return json.dumps({"findings": list(findings), "missing_information": []})


def finding(note_id, kind, quote, polarity="present"):
    return {"finding_type": kind, "description": f"SYNTHETIC {kind}.", "polarity": polarity,
            "temporal_status": "current", "uncertainty": None, "missing_information": [],
            "evidence": [{"observation_id": str(note_id), "source_excerpt": quote, "start_offset": None, "end_offset": None}]}


def extractor(raw):
    return LlmNoteExtractor(StructuredSourceExtractor(), clinical=ClinicalExtractor(FixtureProvider(raw)))


def test_contract_context_keeps_scope_and_complete_history():
    history = lab()
    converted = to_contract_context(legacy_context(history), "query")
    assert converted.patient_id == PATIENT and converted.as_of == CUTOFF
    assert [hit.source.id for hit in converted.retrieved_observations] == [history.id]
    assert converted.coverage.status == "complete" and converted.coverage.eligible_count == 1
    assert converted.retrieval.method == "keyword"


def test_note_findings_are_added_to_structured_findings():
    current, history = note(), lab()
    raw = response(current.id, finding(current.id, "rectal_bleeding", "verta ulosteessa"),
                   finding(current.id, "abdominal_pain", "Ei vatsakipua.", polarity="absent"))
    result = extractor(raw).extract(legacy_context(history), current)
    by_type = {f.finding_type: f for f in result.findings}
    assert by_type["rectal_bleeding"].status == "current"
    assert [ref.observation_id for ref in by_type["rectal_bleeding"].evidence] == [current.id]
    assert by_type["rectal_bleeding"].evidence[0].source_excerpt == "verta ulosteessa"
    # Negation stays explicit and cannot trigger a rule.
    assert by_type["abdominal_pain"].status == "negated"
    # Structured lab facts from the existing extractor are kept.
    assert "B-Hb" in by_type
    assert not any(m.startswith("Free-text clinical-note extraction is not configured") for m in result.missing_information)
    assert any("clinical_interpretation_not_verified" in m for m in result.missing_information)


def test_empty_llm_result_is_a_success_not_a_failure():
    current = note()
    result = extractor(response(current.id)).extract(legacy_context(), current)
    assert result.findings == []


@pytest.mark.parametrize("raw", ["not json", json.dumps({"findings": [], "unexpected": 1})])
def test_invalid_llm_output_fails_the_run_explicitly(raw):
    with pytest.raises(PipelineError, match="^clinical_extraction_invalid_extraction_output$"):
        extractor(raw).extract(legacy_context(), note())


def test_invented_quote_fails_the_run():
    current = note()
    raw = response(current.id, finding(current.id, "rectal_bleeding", "this text is not in the note"))
    with pytest.raises(PipelineError, match="^clinical_extraction_"):
        extractor(raw).extract(legacy_context(), current)


def test_live_calls_are_off_unless_allowed(monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODEL", "synthetic-test-model")
    adapter = LlmNoteExtractor(StructuredSourceExtractor(), build_clinical=build_from_settings(None, False, None))
    with pytest.raises(PipelineError, match="^clinical_extraction_live_calls_disabled$"):
        adapter.extract(legacy_context(), note())


def test_missing_model_configuration_fails_the_run(monkeypatch):
    monkeypatch.delenv("EXTRACTION_MODEL", raising=False)
    adapter = LlmNoteExtractor(StructuredSourceExtractor(), build_clinical=build_from_settings(None, False, None))
    with pytest.raises(PipelineError, match="^clinical_extraction_misconfigured$"):
        adapter.extract(legacy_context(), note())


def test_missing_env_file_fails_the_run(tmp_path):
    adapter = LlmNoteExtractor(StructuredSourceExtractor(),
                               build_clinical=build_from_settings(tmp_path / "missing.env", False, None))
    with pytest.raises(PipelineError, match="^clinical_extraction_misconfigured$"):
        adapter.extract(legacy_context(), note())


@pytest.fixture
def fresh_settings():
    get_pipeline_settings.cache_clear()
    dependencies.build_extractor.cache_clear()
    yield
    get_pipeline_settings.cache_clear()
    dependencies.build_extractor.cache_clear()


def test_pipeline_defaults_to_structured_extraction(monkeypatch, fresh_settings):
    monkeypatch.setenv("CANCERSIGNAL_EXTRACTION", "off")
    assert isinstance(dependencies.get_analysis_pipeline().extractor, StructuredSourceExtractor)


def test_pipeline_uses_llm_extraction_when_enabled(monkeypatch, fresh_settings):
    monkeypatch.setenv("CANCERSIGNAL_EXTRACTION", "llm")
    assert isinstance(dependencies.get_analysis_pipeline().extractor, LlmNoteExtractor)
