"""Read-only API v1 presentation adapter, not a reconstruction of missing models.

API v1 has observation-level rule evidence, not causal finding/feature links.
Rule statements are therefore projected directly, without inventing the richer
TriggerEvaluation.supporting_finding_ids required by the internal contract.
"""
from dataclasses import dataclass
import json

from app.contracts.analysis import AnalysisResult, PipelineMetadata, RuleReference
from app.contracts.clinical_context import SourceObservation
from app.contracts.common import ComponentProvenance, MissingInformation, PipelineIssue
from app.contracts.findings import ClinicalFinding
from app.contracts.predictions import ModelPrediction
from app.contracts.validation import source_index
from app.explanation.facts import Catalog, RULE_TEXT, build_catalog
from app.explanation.schemas import ExplanationStatement, Limitation
from app.schemas.analysis import AnalysisResponse

PROJECTION = ComponentProvenance(name="api-v1-explanation-projection", version="1.0", method="deterministic")
STATES = {"current": ("present", "current"), "historical": ("present", "historical"),
          "resolved": ("present", "resolved"), "negated": ("absent", "current"),
          "uncertain": ("uncertain", "unknown")}


@dataclass(frozen=True)
class ApiExplanationInput:
    identity: AnalysisResult
    catalog: Catalog
    canonical_input: str


def prepare_api_response(response: AnalysisResponse | dict, *, input_note: SourceObservation | None = None,
                         prediction_specs=()) -> ApiExplanationInput:
    """Validate available API evidence and preserve missing metadata as limitations.

    The internal identity projection contains findings/measurements only. It is
    not returned as a supposedly lossless AnalysisResult conversion.
    """
    raw = response.model_dump(mode="python", exclude_unset=True) if isinstance(response, AnalysisResponse) else dict(response)
    raw_metadata = dict(raw.get("provenance", {}))
    top_present, stored_present = "predictions" in raw, "predictions" in raw_metadata

    def predictions_from(values):
        if not isinstance(values, (list, tuple)):
            raise ValueError("Predictions must be an explicit list")
        rows = tuple(ModelPrediction.model_validate(row.model_dump(mode="python") if hasattr(row, "model_dump") else row) for row in values)
        if any(len(set(row.evidence_observation_ids)) != len(row.evidence_observation_ids) for row in rows):
            raise ValueError("Duplicate prediction evidence")
        return rows

    supplied = predictions_from(raw.get("predictions", ()))
    stored = predictions_from(raw_metadata.get("predictions", ()))
    if top_present and stored_present and supplied != stored:
        raise ValueError("Response predictions and saved prediction snapshots disagree")
    predictions = supplied if top_present else stored
    # Normalize known additive fields separately so this adapter also runs with
    # the earlier API DTO, which predates the published QCancer integration.
    dto = dict(raw)
    dto.pop("predictions", None)
    dto_metadata = dict(raw_metadata)
    dto_metadata.pop("predictions", None)
    dto["provenance"] = dto_metadata
    response = AnalysisResponse.model_validate(dto)
    metadata = response.provenance
    if metadata.cutoff is None:
        raise ValueError("API v1 analysis cutoff is required; created_at is not an event-time cutoff.")
    if response.status == "completed" and metadata.error_code is not None:
        raise ValueError("An error-marked analysis cannot be explained as completed.")
    sources = source_index(SourceObservation.model_validate(row.model_dump(mode="python")) for row in response.source_observations)
    if input_note is not None:
        input_note = SourceObservation.model_validate(input_note.model_dump(mode="python") if hasattr(input_note, "model_dump") else input_note)
        if (input_note.id != metadata.input_observation_id or input_note.patient_id != response.patient_id
                or input_note.observation_type != "clinical_note" or input_note.observed_at != metadata.cutoff):
            raise ValueError("Provided input note does not match the saved analysis.")
        if input_note.id in sources and sources[input_note.id] != input_note:
            raise ValueError("Conflicting input-note snapshots.")
        sources[input_note.id] = input_note
    note_id = metadata.input_observation_id if metadata.input_observation_id in sources else None
    if note_id is not None and not sources[note_id].text:
        raise ValueError("The original input note must contain text.")
    findings = []
    if len({row.id for row in response.findings}) != len(response.findings):
        raise ValueError("Duplicate finding IDs.")
    for row in response.findings:
        if row.patient_id != response.patient_id or row.analysis_run_id != response.id or not row.evidence:
            raise ValueError("Finding does not belong to this analysis or has no original evidence.")
        polarity, temporal = STATES[row.status]
        uncertainty = row.uncertainty if row.uncertainty and row.uncertainty.strip() else None
        if row.status == "uncertain":
            # API v1 cannot independently represent polarity and timing. Do not
            # recover them by parsing the free-text uncertainty/description.
            uncertainty = uncertainty or "API v1 marks this finding uncertain and does not separately establish its timing."
        findings.append(ClinicalFinding(id=row.id, patient_id=row.patient_id, finding_type=row.finding_type,
            description=row.description, polarity=polarity, temporal_status=temporal,
            evidence=tuple(row.evidence), uncertainty=uncertainty, provenance=PROJECTION))
    missing = tuple(MissingInformation(code="api_v1_missing_information",
        description=text if text.strip() else "API v1 reported unspecified missing information.") for text in metadata.missing_information)
    issues = ((PipelineIssue(code="api_v1_analysis_failed", message="The API reports a failed analysis.",
                             component="api-v1-projection", severity="error"),) if response.status == "failed" else ())
    projection = AnalysisResult(analysis_id=response.id, patient_id=response.patient_id, as_of=metadata.cutoff,
        created_at=response.created_at, status=response.status, input_note_id=note_id,
        findings=tuple(findings), predictions=predictions, source_observations=tuple(sources.values()), missing_information=missing, issues=issues,
        metadata=PipelineMetadata(pipeline_version="api-v1-explanation-projection-1", components=(PROJECTION,)))
    base = build_catalog(projection, prediction_specs)
    limits = [*base.limitations,
        Limitation(code="api_v1_features_not_exposed", text_fi="API-vastaus ei sisällä erillisiä laskennallisia piirretietueita. Niitä ei päätellä kuvaustekstistä."),
        Limitation(code="api_v1_provenance_limited", text_fi="API-vastaus ei yksilöi jokaisen löydöksen alkuperäistä tuottajaa tai malliversiota; sovitin ei päättele niitä.")]
    if not predictions:
        limits.append(Limitation(code="api_v1_model_outputs_not_exposed", text_fi="Annetussa API-vastauksessa ei ole erillisiä malliennusteita. Niitä ei päätellä kuvaustekstistä."))
    if note_id is None:
        limits.append(Limitation(code="api_v1_input_note_not_loaded", text_fi="Alkuperäinen uusi hoitokirjaus ei ole mukana annetussa aineistossa. Selitys koskee vain toimitettuja rakenteisia tuloksia ja lähteitä."))
    if len({row.id for row in response.trigger_results}) != len(response.trigger_results) or len({row.trigger_rule_id for row in response.trigger_results}) != len(response.trigger_results):
        raise ValueError("Duplicate trigger results or rule IDs.")
    statements, required = list(base.statements), set(base.required)
    # API v1 does not disclose which findings were causal. Preserve every finding
    # instead of guessing a support relationship from shared observation IDs.
    required.update(f"finding:{row.id}" for row in response.findings)
    finding_sources = {ref.observation_id for row in response.findings for ref in row.evidence}
    for result in response.trigger_results:
        ids = result.evidence_observation_ids
        if (len(set(ids)) != len(ids) or not set(ids).issubset(finding_sources)
                or (result.triggered and (not ids or not result.requires_clinician_review))):
            raise ValueError("Rule evidence/review state is inconsistent with the saved API result.")
        # Finding evidence is already validated by the identity projection. Rule
        # evidence must be a subset; it must not imply a new finding association.
        reference = RuleReference(trigger_rule_id=result.trigger_rule_id, version=result.rule_version,
                                  source=result.rule_source, source_section=result.rule_source_section)
        snapshot = metadata.rule_snapshots.get(str(result.trigger_rule_id))
        if snapshot is not None and (snapshot.version, snapshot.source, snapshot.source_section, snapshot.priority) != (
                result.rule_version, result.rule_source, result.rule_source_section, result.priority):
            raise ValueError("Rule response and saved snapshot disagree.")
        outcome = "matched" if result.triggered else "not_matched"
        text = RULE_TEXT[outcome]
        if result.requires_clinician_review and not result.triggered:
            text += " Lähtötulos on merkitty ammattilaisen arvioitavaksi."
        key = f"rule:{result.trigger_rule_id}"
        statements.append(ExplanationStatement(key=key, kind="rule", text_fi=text, observation_ids=tuple(ids),
            rule_reference=reference, requires_clinician_review=result.requires_clinician_review))
        required.add(key)
    if response.trigger_results:
        limits.append(Limitation(code="api_v1_trigger_links_limited", text_fi="API ilmoittaa sääntötulosten lähteet, mutta ei suoria löydös- tai piirretunnisteita. Näitä yhteyksiä ei päätellä."))
        limits.append(Limitation(code="api_v1_boolean_rule_outcomes", text_fi="API kuvaa sääntötulokset totuusarvoina; erillistä epävarmaa sääntötilaa ei ole saatavilla."))
    summary = "review_signals" if any(row.triggered for row in response.trigger_results) else "no_signals" if response.trigger_results else "observations_only"
    canonical_response = response.model_dump(mode="json")
    if top_present:
        canonical_response["predictions"] = [row.model_dump(mode="json") for row in supplied]
    if stored_present:
        canonical_response["provenance"]["predictions"] = [row.model_dump(mode="json") for row in stored]
    canonical = json.dumps({"input_format": "api_v1", "response": canonical_response,
                            "provided_input_note": input_note.model_dump(mode="json") if input_note else None},
                           sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return ApiExplanationInput(projection, Catalog(tuple(statements), frozenset(required), base.finding_groups, tuple(limits), summary), canonical)
