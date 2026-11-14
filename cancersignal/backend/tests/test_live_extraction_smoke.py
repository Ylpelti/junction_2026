"""Explicitly opted-in real inference; never used by ordinary automated tests."""
import json
import os
from pathlib import Path

import pytest

from app.contracts.clinical_context import RetrievedContext, SourceObservation, StructuredPatientContext
from app.extraction.providers import ChatCompletionsProvider, ProviderSettings
from app.extraction.service import ClinicalExtractor


@pytest.mark.skipif(os.getenv("RUN_LIVE_EXTRACTION") != "1", reason="Paid external inference requires RUN_LIVE_EXTRACTION=1")
def test_real_provider_validates_synthetic_extraction():
    example = json.loads((Path(__file__).resolve().parents[1] / "examples/extraction/synthetic.json").read_text())
    settings = ProviderSettings(_env_file=os.getenv("CANCERSIGNAL_EXTRACTION_ENV_FILE"))
    assert settings.api_key.get_secret_value(), "Configure EXTRACTION_API_KEY before opting in"
    # No replay cache: this test must actually invoke the configured provider.
    extractor = ClinicalExtractor(ChatCompletionsProvider(settings, allow_live=True))
    batch = extractor(
        RetrievedContext.model_validate(example["context"]),
        input_note=SourceObservation.model_validate(example["input_note"]),
        structured_context=StructuredPatientContext.model_validate(example["structured_context"]) if example.get("structured_context") else None,
    )
    assert batch.status in ("complete", "partial"), [issue.code for issue in batch.issues]
    assert batch.findings, "Expected source-backed findings from the synthetic clinical note"
