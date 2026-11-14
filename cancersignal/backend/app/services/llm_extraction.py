"""Connect app.extraction.ClinicalExtractor to the API v1 analysis pipeline.

The analysis pipeline calls `extractor.extract(context, note) -> ExtractionResult`
with the legacy `app.rag.context.RetrievedContext`. ClinicalExtractor uses the
shared contracts (`app.contracts.clinical_context.RetrievedContext` ->
`FindingBatch`). This adapter converts between the two. It lives in services,
not app/extraction, so the extraction package stays independent of RAG and the
pipeline (tests/extraction). It does not
retrieve, persist or evaluate rules.

- The existing structured extractor still runs first, so coded symptom and lab
  facts keep working. LLM note findings are added on top.
- A failed extraction raises PipelineError, so the analysis run is stored as
  `failed`. It never becomes "no signals identified".
- Configuration problems (missing model ID, missing httpx, live calls not
  authorized with an empty cache) fail the same explicit way.
"""
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from app.contracts.clinical_context import RetrievedContext as ContractContext
from app.contracts.clinical_context import RetrievedObservation, SourceObservation
from app.contracts.common import ComponentProvenance, Coverage
from app.contracts.validation import EvidenceValidationError
from app.extraction.compatibility import legacy_findings
from app.extraction.service import ClinicalExtractor
from app.rag.context import ExtractionResult, RetrievedContext
from app.schemas.records import ObservationRead
from app.services.errors import PipelineError

# Message from StructuredSourceExtractor that is no longer true once this adapter runs.
FREE_TEXT_NOT_CONFIGURED = "Free-text clinical-note extraction is not configured"


def to_contract_context(context: RetrievedContext, query: str) -> ContractContext:
    """The baseline retriever returns ALL eligible history before the cutoff, so coverage is complete."""
    sources = [SourceObservation.model_validate(item.observation.model_dump()) for item in context.observations]
    return ContractContext(
        patient_id=context.patient_id,
        as_of=context.cutoff,
        query=query,
        retrieved_observations=tuple(RetrievedObservation(source=row, retrieval_method="keyword") for row in sources),
        retrieval=ComponentProvenance(name=context.retrieval_method, version="1", method="keyword"),
        coverage=Coverage(status="complete", eligible_count=len(sources)),
    )


class LlmNoteExtractor:
    """FindingExtractor for the analysis pipeline: structured facts + LLM note extraction."""

    name = "structured-source-demo-v1+clinical-extraction-2"

    def __init__(self, base, *, clinical: ClinicalExtractor | None = None,
                 build_clinical: Callable[[], ClinicalExtractor] | None = None):
        if (clinical is None) == (build_clinical is None):
            raise ValueError("Supply exactly one of clinical or build_clinical.")
        self.base = base
        self._clinical = clinical
        self._build_clinical = build_clinical

    def clinical(self) -> ClinicalExtractor:
        if self._clinical is None:
            try:
                self._clinical = self._build_clinical()
            except (ValidationError, ValueError, OSError):
                # e.g. EXTRACTION_MODEL missing or the env file is unreadable. No secrets in the code.
                raise PipelineError("clinical_extraction_misconfigured") from None
        return self._clinical

    def extract(self, context: RetrievedContext, note: ObservationRead) -> ExtractionResult:
        base = ExtractionResult.model_validate(self.base.extract(context, note))
        clinical = self.clinical()
        try:
            batch = clinical(to_contract_context(context, note.text or ""),
                             input_note=SourceObservation.model_validate(note.model_dump()))
        except ImportError:
            raise PipelineError("clinical_extraction_dependency_missing") from None
        except (ValidationError, ValueError, EvidenceValidationError):
            # Caller-side contract violation, raised before any provider call.
            raise PipelineError("clinical_extraction_invalid_input") from None
        if batch.status == "failed":
            code = next((issue.code for issue in batch.issues if issue.severity == "error"), "failed")
            raise PipelineError(f"clinical_extraction_{code}")
        missing = [m for m in base.missing_information if not m.startswith(FREE_TEXT_NOT_CONFIGURED)]
        missing += [gap.description for gap in batch.missing_information]
        missing += [f"{issue.message} ({issue.code})" for issue in batch.issues]
        return ExtractionResult(findings=[*base.findings, *legacy_findings(batch)], missing_information=missing,
                                qcancer_predictors=batch.qcancer_predictors)


def build_from_settings(env_file: Path | None, allow_live: bool, cache_dir: Path | None) -> Callable[[], ClinicalExtractor]:
    """Deferred construction so a bad configuration fails the run, not app startup."""
    def build() -> ClinicalExtractor:
        from app.extraction.providers import ChatCompletionsProvider, ProviderSettings
        if env_file is not None and not env_file.is_file():
            raise ValueError("Extraction env file not found.")
        settings = ProviderSettings(_env_file=env_file) if env_file is not None else ProviderSettings()
        return ClinicalExtractor(ChatCompletionsProvider(settings, allow_live=allow_live), cache_dir=cache_dir)
    return build
