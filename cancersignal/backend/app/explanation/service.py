from hashlib import sha256
import json
import logging
from pathlib import Path
import tempfile

from pydantic import ValidationError

from app.contracts.analysis import AnalysisResult
from app.contracts.common import ComponentProvenance, PipelineIssue
from app.contracts.validation import EvidenceValidationError
from app.explanation.facts import build_catalog
from app.explanation.providers import ExplanationProvider, PROMPT_VERSION, ProviderError, SYSTEM_PROMPT
from app.explanation.schemas import ExplanationPlan, ExplanationResult, Limitation, PredictionDisplaySpec, plan_schema

SUMMARY = {
    "review_signals": ("Signals identified in stored rule results. Physician review required.",
                       "The structured analysis contains matched rules. Physician review required."),
    "indeterminate": ("Insufficient information: rule results contain uncertainty or missing data.",
                      "Available information cannot fully determine whether the stored rules match."),
    "no_signals": ("No signals identified in stored rule results. Review the limitations.",
                   "No signals identified in the supplied rule results. Missing or uncertain information remains relevant."),
    "observations_only": ("Structured findings and calculated results are summarised below. Rule evaluation is unavailable.",
                          "This summary uses the supplied findings and calculated results. Rule evaluation is unavailable."),
}
FALLBACK = ComponentProvenance(name="clinical-explanation-en", version="2.0", method="deterministic", prompt_version=PROMPT_VERSION)


class ExplanationInputError(ValueError):
    """Unsafe/inconsistent input cannot be explained, even by a fallback."""


class PlanError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def validate_plan(plan, catalog):
    index = {statement.key: statement for statement in catalog.statements}
    keys = [entry.fact_key for entry in plan.entries]
    if plan.summary_kind != catalog.summary_kind:
        raise PlanError("altered_summary")
    if len(set(keys)) != len(keys) or any(key not in index for key in keys):
        raise PlanError("invalid_fact_reference")
    selected = set(keys)
    if not catalog.required.issubset(selected) or (index and not selected):
        raise PlanError("missing_required_fact")
    if any(selected.intersection(group) and not group.issubset(selected) for group in catalog.finding_groups):
        raise PlanError("incomplete_finding_group")
    for entry in plan.entries:
        fact = index[entry.fact_key]
        if len(set(entry.observation_ids)) != len(entry.observation_ids) or set(entry.observation_ids) != set(fact.observation_ids):
            raise PlanError("invalid_evidence_reference")
        expected = {number.slot: (number.value, number.unit) for number in fact.quantities}
        actual = {number.slot: (number.value, number.unit) for number in entry.quantities}
        if len(actual) != len(entry.quantities) or actual != expected:
            raise PlanError("invalid_numeric_claim")
    return tuple(index[key] for key in keys)


class ExplanationEngine:
    def __init__(self, provider: ExplanationProvider | None = None, *,
                 prediction_specs: tuple[PredictionDisplaySpec, ...] = (), cache_dir: Path | None = None):
        self.provider, self.prediction_specs, self.cache_dir = provider, prediction_specs, cache_dir

    def __call__(self, analysis: AnalysisResult) -> ExplanationResult:
        try:
            # ModelPrediction is a mutable legacy record: rebuild the entire graph.
            result = AnalysisResult.model_validate(analysis.model_dump(mode="python"))
            if any(len(set(row.evidence_observation_ids)) != len(row.evidence_observation_ids) for row in result.predictions):
                raise ValueError("Duplicate prediction evidence")
            canonical = json.dumps(result.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
                                   allow_nan=False, separators=(",", ":"))
            catalog = build_catalog(result, self.prediction_specs)
        except (ValidationError, EvidenceValidationError, ValueError, TypeError, AttributeError):
            raise ExplanationInputError("Invalid source analysis or display contract; check references, patient, time boundaries and numeric values.") from None
        return self._explain(result, catalog, canonical)

    def explain_api(self, response, *, input_note=None) -> ExplanationResult:
        """Explain the existing API DTO without changing it or querying a database."""
        from app.explanation.adapters import prepare_api_response
        try:
            prepared = prepare_api_response(response, input_note=input_note, prediction_specs=self.prediction_specs)
        except (ValidationError, EvidenceValidationError, ValueError, TypeError, AttributeError, KeyError):
            raise ExplanationInputError("The API response has incomplete or inconsistent patient, cutoff, original sources or rule references.") from None
        return self._explain(prepared.identity, prepared.catalog, prepared.canonical_input, input_format="api_v1")

    def _explain(self, result, catalog, canonical, *, input_format="analysis_result"):
        digest = sha256(canonical.encode()).hexdigest()
        base = dict(analysis_id=result.analysis_id, patient_id=result.patient_id, as_of=result.as_of,
                    input_digest=digest, input_format=input_format)
        if result.status != "completed":
            return ExplanationResult(**base, mode="unavailable", summary_en="Analysis has not completed reliably. No clinical summary was generated.",
                limitations=(Limitation(code="analysis_not_completed", text_en="An incomplete or failed analysis is not interpreted as a completed clinical result."),),
                provenance=FALLBACK, issues=(self._issue("analysis_not_completed", "No completed source analysis is available."),))
        if not catalog.statements:
            return ExplanationResult(**base, mode="unavailable", summary_en="The source analysis has no explainable structured results. Missing information does not support a clinical conclusion.",
                limitations=(*catalog.limitations, Limitation(code="no_explainable_data", text_en="The source result has no structured findings, measurements, model predictions or rule evaluations.")),
                provenance=FALLBACK, issues=(self._issue("no_explainable_data", "No explainable structured results are available."),))
        selected, style, mode, issues, attempted = catalog.statements, "compact", "fallback", (), None
        if self.provider is not None:
            attempted = self.provider.provenance
            payload = {"summary_kind": catalog.summary_kind, "required_keys": sorted(catalog.required),
                       "finding_groups": [sorted(group) for group in catalog.finding_groups],
                       "facts": [row.model_dump(mode="json", exclude={"source_notice"}) for row in catalog.statements]}
            prompt = [{"role": "system", "content": SYSTEM_PROMPT + json.dumps(plan_schema())},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
            key = sha256(json.dumps({"input": digest, "prompt": prompt, "producer": attempted.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()
            path = self.cache_dir / (key + ".json") if self.cache_dir is not None else None
            try:
                cached = path is not None and path.exists()
                logging.getLogger(__name__).info("explanation_cache %s key=%s",
                                                 "hit" if cached else "miss" if path else "disabled", key)
                raw = path.read_text(encoding="utf-8") if cached else self.provider.complete(prompt, plan_schema())
                plan = ExplanationPlan.model_validate_json(raw)
                selected = validate_plan(plan, catalog)
                style, mode = plan.style, "llm"
                if path is not None and not cached:
                    self._cache(path, plan.model_dump_json())
            except PlanError as error:
                issues = (self._issue(error.code, "The LLM plan was rejected; deterministic text from validated source data is used."),)
                selected, style, mode = catalog.statements, "compact", "fallback"
            except ValidationError:
                issues = (self._issue("invalid_structured_response", "The LLM response does not conform to the schema; deterministic text is used."),)
            except ProviderError as error:
                issues = (self._issue(error.code, str(error)),)
            except (OSError, UnicodeError):
                issues = (self._issue("cache_error", "The explanation cache could not be processed; deterministic text is used."),)
            except Exception:
                # A provider implementation may fail unexpectedly. Never expose
                # its exception (it may contain clinical text or credentials).
                issues = (self._issue("explanation_generation_failed", "LLM explanation generation failed; deterministic text is used."),)
            if issues:
                # A write failure after validation must also take the explicit fallback path.
                selected, style, mode = catalog.statements, "compact", "fallback"
        else:
            issues = (self._issue("offline_fallback", "The explanation was generated without an LLM call."),)
        return ExplanationResult(**base, mode=mode, summary_en=SUMMARY[catalog.summary_kind][style == "standard"],
            findings=tuple(row for row in selected if row.kind == "finding"),
            mathematical_outputs=tuple(row for row in selected if row.kind in ("measurement", "feature", "prediction")),
            rule_results=tuple(row for row in selected if row.kind == "rule"), limitations=catalog.limitations,
            provenance=attempted if mode == "llm" else FALLBACK, attempted_provider=attempted, issues=issues)

    @staticmethod
    def _issue(code, message):
        return PipelineIssue(code=code, message=message, component="clinical-explanation", severity="warning")

    @staticmethod
    def _cache(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(text)
                handle.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
