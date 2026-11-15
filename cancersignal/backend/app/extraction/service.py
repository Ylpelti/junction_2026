"""FindingExtractor protocol implementation; no retrieval, persistence or decisions."""
from hashlib import sha256
import json
import logging
from pathlib import Path
import tempfile

from pydantic import ValidationError

from app.contracts.clinical_context import RetrievedContext, SourceObservation, StructuredPatientContext
from app.contracts.common import MissingInformation, PipelineIssue
from app.contracts.findings import ClinicalFinding
from app.contracts.stages import FindingBatch
from app.contracts.validation import EvidenceValidationError, merge_source_contexts, validate_finding, validate_evidence
from app.extraction.prompt import messages
from app.extraction.semantics import validate_semantics, VERSION
from app.extraction.providers import CompletionProvider, ProviderError
from app.extraction.schema import ExtractionOutput, output_schema


class ClinicalExtractor:
    def __init__(self, provider: CompletionProvider, *, cache_dir: Path | None = None):
        self.provider = provider
        self.cache_dir = cache_dir

    def __call__(self, context: RetrievedContext, *, input_note: SourceObservation | None = None,
                 structured_context: StructuredPatientContext | None = None) -> FindingBatch:
        # Invalid caller input is a programming error. Revalidate even constructed
        # or copied Pydantic instances before any network call/cache access.
        context = RetrievedContext.model_validate(context)
        if input_note is not None:
            input_note = SourceObservation.model_validate(input_note)
            if not input_note.text:
                raise ValueError("The current nurse note must contain source text.")
        structured = (StructuredPatientContext.model_validate(structured_context)
                      if structured_context is not None else StructuredPatientContext(
                          **self._scope(context), observations=(),
                          coverage={"status": "complete", "eligible_count": 0},
                          access={"name": "not-requested", "version": "1", "method": "structured"}))
        sources = merge_source_contexts(context, structured, input_note=input_note)
        if any(not context.permits(row, input_note_id=input_note.id if input_note else None) for row in sources):
            raise EvidenceValidationError("source_outside_scope", "All supplied sources must satisfy the retrieval patient/time scope.")
        provenance = self.provider.provenance
        prompt = messages(context, input_note, structured if structured_context is not None else None)
        cache_key = sha256(json.dumps({"messages": prompt, "schema": output_schema(), "semantic_version": VERSION,
                                      "context": context.model_dump(mode="json", exclude={"generated_at"}),
                                      "provenance": provenance.model_dump(mode="json")},
                                     sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cache_file = self.cache_dir / (cache_key + ".json") if self.cache_dir is not None else None
        try:
            cached = cache_file is not None and cache_file.exists()
            logging.getLogger(__name__).info("extraction_cache %s key=%s",
                                             "hit" if cached else "miss" if cache_file else "disabled", cache_key)
            raw = cache_file.read_text(encoding="utf-8") if cached else self.provider.complete(prompt, output_schema())
            # Strict JSON: no markdown stripping, quote repair, defaults or retries.
            output = ExtractionOutput.model_validate_json(raw)
            findings = tuple(ClinicalFinding(patient_id=context.patient_id, provenance=provenance,
                                             **row.model_dump()) for row in output.findings)
            for finding in findings:
                validate_finding(finding, sources, scope=context,
                                 input_note_id=input_note.id if input_note else None)
            for reference in output.qcancer_predictors.evidence_references():
                validate_evidence(context.patient_id, (reference,), sources, scope=context,
                                  input_note_id=input_note.id if input_note else None)
            missing = [*context.coverage.missing_information, *structured.coverage.missing_information,
                       *output.missing_information]
            for coverage, label in ((context.coverage, "retrieved history"),
                                    (structured.coverage, "structured measurements")):
                if coverage.status != "complete":
                    missing.append(MissingInformation(code="incomplete_context", description=f"Coverage of {label} is {coverage.status}."))
            source_ids = {row.id for row in sources}
            for gap in (*missing, *(gap for finding in findings for gap in finding.missing_information)):
                if any(identifier not in source_ids for identifier in gap.observation_ids):
                    raise EvidenceValidationError("invalid_missing_information_reference", "Missing-information reference is outside the supplied context.")
            findings, predictors, semantic_issues, diagnostics = validate_semantics(
                findings, output.qcancer_predictors, sources, input_note.id if input_note else None)
            compact_rejections = [gap for gap in output.missing_information
                                  if gap.code in ("compact_evidence_rejected", "compact_fact_rejected")]
            diagnostics["rejected"].extend({"path": "compact", "reason": gap.description} for gap in compact_rejections)
            diagnostics["extraction_prompt"] = provenance.prompt_version
            semantic_issues += tuple(PipelineIssue(code="semantic_rejection", component=VERSION,
                severity="warning", message=gap.description) for gap in compact_rejections)
            # Never promote an LLM's interpretation to a verified clinical fact.
            issue = PipelineIssue(code="clinical_interpretation_not_verified", component="clinical-extraction",
                                  severity="warning", message="Source IDs, quotes, offsets and patient/time scope validated; clinical interpretation and completeness require review.")
            batch = FindingBatch(**self._scope(context), provenance=provenance,
                                 status="partial" if semantic_issues or missing or any(row.uncertainty or row.missing_information for row in findings) else "complete",
                                 findings=findings, qcancer_predictors=predictors, semantic_validation=diagnostics,
                                 missing_information=tuple(missing), issues=(issue, *semantic_issues))
            if cache_file is not None and not cached:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                # Only validated responses enter the cache; every read revalidates.
                self._write_cache(cache_file, output.model_dump_json())
            return batch
        except ValidationError:
            return self._failed(context, provenance, "invalid_extraction_output", "Provider output does not satisfy the extraction schema.")
        except EvidenceValidationError as exc:
            return self._failed(context, provenance, exc.code, "Extraction contains invalid source evidence; all findings were discarded.")
        except ProviderError as exc:
            return self._failed(context, provenance, exc.code, str(exc))
        except (OSError, UnicodeError):
            return self._failed(context, provenance, "cache_error", "Could not read or write the explicitly configured response cache.")

    @staticmethod
    def _write_cache(path, content):
        # Atomic replacement prevents concurrent demo workers reading half a JSON
        # response. NamedTemporaryFile creates the file with owner-only access.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(content)
                handle.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _scope(context):
        return context.model_dump(include={"patient_id", "as_of", "observed_since", "recorded_before"})

    @classmethod
    def _failed(cls, context, provenance, code, message):
        return FindingBatch(**cls._scope(context), provenance=provenance, status="failed",
                            issues=(PipelineIssue(code=code, message=message, component="clinical-extraction", severity="error"),))
