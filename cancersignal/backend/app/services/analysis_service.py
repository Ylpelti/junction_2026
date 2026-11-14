import inspect
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from app.contracts.clinical_context import SourceObservation
from app.contracts.common import PatientScope
from app.contracts.validation import EvidenceValidationError, validate_evidence
from app.contracts.qcancer import QCancerPredictors

from app.models import (
    AnalysisRun, ClinicalFinding, FindingEvidence, Observation,
    TriggerResult, TriggerResultEvidence, TriggerRule,
)
from app.models.enums import AnalysisStatus, ObservationType
from app.rag.context import ContextObservation, ExtractionResult, RetrievedContext
from app.rag.repository import PatientRepository
from app.reasoning.derived_findings import derive_lab_findings
from app.reasoning.interfaces import AnalysisPipeline, TriggerEvaluation
from app.reasoning.vocabulary import AGE_YEARS
from app.risk_models.adapter import build_qcancer_input
from app.risk_models.qcancer_2013 import qcancer_prediction
from app.schemas.analysis import (
    AnalysisProvenance, AnalysisRequest, AnalysisResponse, EvidenceReference,
    FindingResponse, RuleSnapshot, TriggerResponse,
)
from app.schemas.records import ClinicalFindingRead, ObservationRead, TriggerRuleRead
from app.services.errors import PipelineError, ServiceError
from app.services.observation_service import create_observation, get_observation
from app.services.patient_service import get_patient


def rule_snapshot(rule: TriggerRule) -> RuleSnapshot:
    return RuleSnapshot(name=rule.name, version=rule.version,
        source=str(rule.conditions.get("lahde", "")), source_section=str(rule.conditions.get("lahde_kohta", "")),
        recommended_action=rule.recommended_action,
        demonstration_only=rule.conditions.get("demonstration") is True,
        priority="urgent" if rule.conditions.get("priority") == "urgent" else "review")


def age_in_years(birth_date: date, at: datetime) -> int:
    """Whole years at time t, computed in Python (never by the LLM)."""
    day = at.date()
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def run_evaluator(pipeline: AnalysisPipeline, patient_id, findings, rules, patient_facts):
    """Pass patient facts only to evaluators that accept them (older ones take three arguments)."""
    try:
        parameters = inspect.signature(pipeline.evaluate).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    if any(p.name == "patient_facts" or p.kind == p.VAR_KEYWORD for p in parameters):
        return pipeline.evaluate(patient_id, findings, rules, patient_facts=patient_facts)
    return pipeline.evaluate(patient_id, findings, rules)


def get_analysis(session: Session, analysis_id: UUID) -> AnalysisResponse:
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.id == analysis_id).options(
        selectinload(AnalysisRun.findings).selectinload(ClinicalFinding.evidence),
        selectinload(AnalysisRun.trigger_results).selectinload(TriggerResult.evidence),
        selectinload(AnalysisRun.trigger_results).selectinload(TriggerResult.trigger_rule),
    ).execution_options(populate_existing=True))
    if run is None:
        raise ServiceError(404, "Analysis not found.")
    provenance = AnalysisProvenance.model_validate(run.details)
    findings = [FindingResponse(**ClinicalFindingRead.model_validate(finding).model_dump(),
        evidence=[EvidenceReference(observation_id=ref.observation_id,
        source_excerpt=ref.source_excerpt, start_offset=ref.start_offset, end_offset=ref.end_offset)
        for ref in sorted(finding.evidence, key=lambda ref: str(ref.observation_id))])
        for finding in sorted(run.findings, key=lambda finding: str(finding.id))]
    results = []
    for result in sorted(run.trigger_results, key=lambda result: str(result.id)):
        snapshot = provenance.rule_snapshots.get(str(result.trigger_rule_id)) or rule_snapshot(result.trigger_rule)
        results.append(TriggerResponse(id=result.id, trigger_rule_id=result.trigger_rule_id,
            rule_name=snapshot.name, rule_version=snapshot.version,
            demonstration_only=snapshot.demonstration_only, rule_source=snapshot.source,
            rule_source_section=snapshot.source_section, priority=snapshot.priority, triggered=result.triggered,
            explanation=result.explanation or "Stored result has no explanation.",
            recommended_action=snapshot.recommended_action if result.triggered else None,
            requires_clinician_review=result.requires_clinician_review,
            evidence_observation_ids=sorted((ref.observation_id for ref in result.evidence), key=str)))
    source_ids = {ref.observation_id for finding in findings for ref in finding.evidence}
    source_ids.update(identifier for result in results for identifier in result.evidence_observation_ids)
    source_ids.update(identifier for prediction in provenance.predictions for identifier in prediction.evidence_observation_ids)
    sources = session.scalars(select(Observation).where(Observation.id.in_(source_ids))
        .order_by(Observation.observed_at, Observation.id)).all() if source_ids else []
    if run.status == AnalysisStatus.FAILED:
        explanation = "Analysis failed. No findings or trigger results were persisted."
    elif run.status in (AnalysisStatus.PENDING, AnalysisStatus.RUNNING):
        explanation = "Analysis has not completed; no conclusion is available."
    elif any(result.triggered for result in results):
        explanation = "Demonstration rules suggest physician review. This is not a diagnosis or referral decision."
    else:
        explanation = "No signals identified by configured demonstration rules. Review missing information; this is not a diagnosis."
    return AnalysisResponse(id=run.id, patient_id=run.patient_id, status=run.status,
        created_at=run.created_at, findings=findings, trigger_results=results, predictions=provenance.predictions,
        source_observations=[ObservationRead.model_validate(row) for row in sources],
        explanation=explanation, provenance=provenance)


def list_analyses(session: Session, patient_id: UUID, limit=100, offset=0):
    get_patient(session, patient_id)
    ids = session.scalars(select(AnalysisRun.id).where(AnalysisRun.patient_id == patient_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id).limit(limit).offset(offset)).all()
    return [get_analysis(session, identifier) for identifier in ids]


def validate_context(session: Session, context: RetrievedContext, note: ObservationRead):
    if context.patient_id != note.patient_id or context.cutoff != note.observed_at:
        raise PipelineError("invalid_retrieval_scope")
    source_context = context.source_context
    if source_context is not None and (
            source_context.patient_id != note.patient_id or source_context.as_of != note.observed_at
            or source_context.recorded_before != note.observed_at
            or [hit.source.model_dump() for hit in source_context.retrieved_observations]
            != [item.observation.model_dump() for item in context.observations]):
        raise PipelineError("invalid_retrieval_scope")
    identifiers = [item.observation.id for item in context.observations]
    if len(set(identifiers)) != len(identifiers) or set(context.ranked_observation_ids) != set(identifiers):
        raise PipelineError("invalid_retrieval_references")
    records = {row.id: row for row in session.scalars(select(Observation).where(Observation.id.in_(identifiers)))}
    for item in context.observations:
        row = records.get(item.observation.id)
        if (row is None or row.patient_id != note.patient_id
                or row.observed_at >= note.observed_at or row.recorded_at >= note.observed_at
                or ObservationRead.model_validate(row) != item.observation
                or item.source_excerpt != row.text):
            raise PipelineError("invalid_retrieval_scope")
    return records


def verify_findings(findings, allowed):
    sources = tuple(SourceObservation.model_validate(row) for row in allowed.values())
    if findings and not sources:
        raise PipelineError("invalid_finding_evidence")
    for finding in findings:
        # Preserve API v1 error codes while sharing reference checks with new adapters.
        try:
            validate_evidence(sources[0].patient_id, finding.evidence, sources)
        except EvidenceValidationError as error:
            code = {"duplicate_evidence": "duplicate_finding_evidence", "missing_observation": "invalid_finding_evidence",
                    "cross_patient_evidence": "invalid_finding_evidence"}.get(error.code, error.code)
            raise PipelineError(code) from None
        identifiers = [ref.observation_id for ref in finding.evidence]
        if finding.numeric_value is not None and not any(
                allowed[identifier].numeric_value == finding.numeric_value
                and allowed[identifier].unit == finding.unit for identifier in identifiers):
            raise PipelineError("invalid_numeric_evidence")


def verify_qcancer_predictors(predictors: QCancerPredictors | None, allowed):
    if predictors is None:
        return
    references = predictors.evidence_references()
    if references and not allowed:
        raise PipelineError("invalid_qcancer_evidence")
    sources = tuple(SourceObservation.model_validate(row) for row in allowed.values())
    for reference in references:
        try:
            validate_evidence(sources[0].patient_id, (reference,), sources)
        except EvidenceValidationError:
            raise PipelineError("invalid_qcancer_evidence") from None


def create_analysis(session: Session, patient_id: UUID, payload: AnalysisRequest, pipeline: AnalysisPipeline):
    patient = get_patient(session, patient_id)
    if payload.note is not None:
        note_row = create_observation(session, patient_id, payload.note, commit=False)
    else:
        note_row = get_observation(session, payload.note_observation_id)
        if note_row.patient_id != patient_id:
            raise ServiceError(404, "Clinical note not found for this patient.")
    if note_row.observation_type != ObservationType.CLINICAL_NOTE or not note_row.text:
        raise ServiceError(422, "Analysis requires an existing clinical_note with source text.")
    note = ObservationRead.model_validate(note_row)
    patient_facts = {AGE_YEARS: age_in_years(patient.birth_date, note.observed_at)}
    metadata = AnalysisProvenance(input_observation_id=note.id, cutoff=note.observed_at,
                                  extraction_method=pipeline.extractor.name, patient_facts=patient_facts)
    run = AnalysisRun(patient_id=patient_id, status=AnalysisStatus.RUNNING, model_name=pipeline.extractor.name,
                      details=metadata.model_dump(mode="json"))
    session.add(run)
    session.flush()
    try:
        with session.begin_nested():
            context = RetrievedContext.model_validate(pipeline.retrieve(patient_id, note.text, session, before=note.observed_at))
            allowed = validate_context(session, context, note)
            allowed[note.id] = note_row  # Current note is explicit input, never retrieved history.
            metadata.context_observation_ids = [item.observation.id for item in context.observations]
            metadata.retrieval_method = context.retrieval_method
            extraction = ExtractionResult.model_validate(pipeline.extractor.extract(context, note))
            # Extractors may cite only the snapshots they received (plus the input note).
            verify_findings(extraction.findings, allowed)
            verify_qcancer_predictors(extraction.qcancer_predictors, allowed)
            # Numerical history is a separate, complete SQL branch. Semantic top-k,
            # lexical matching and prompt budgets must never select model inputs.
            numerical = PatientRepository(session).structured(
                scope=PatientScope(patient_id=patient_id, as_of=note.observed_at))
            numerical_context = RetrievedContext(patient_id=patient_id, cutoff=note.observed_at,
                observations=[ContextObservation(observation=ObservationRead.model_validate(row.model_dump()),
                                                source_excerpt=row.text) for row in numerical.observations],
                ranked_observation_ids=[row.id for row in numerical.observations])
            allowed.update(validate_context(session, numerical_context, note))
            metadata.context_observation_ids = list(dict.fromkeys(
                [*metadata.context_observation_ids, *numerical_context.ranked_observation_ids]))
            # Lab-derived findings (anaemia, iron deficiency anaemia, FIT) are computed in Python
            # and go through the same evidence checks as extracted findings.
            derived, derived_missing = derive_lab_findings(
                list(numerical.observations), sex=patient.sex)
            extraction.findings.extend(derived)
            extraction.missing_information.extend(derived_missing)
            verify_findings(extraction.findings, allowed)
            retrieval_missing = ([f"{gap.code}: {gap.description}" for gap in context.source_context.coverage.missing_information]
                                 if context.source_context is not None else [])
            metadata.missing_information = list(dict.fromkeys([*extraction.missing_information, *retrieval_missing]))
            qcancer_inputs = build_qcancer_input(
                patient_id=patient_id, as_of=note.observed_at, sex=patient.sex,
                age_years=patient_facts[AGE_YEARS], predictors=extraction.qcancer_predictors,
                observations=[ObservationRead.model_validate(row) for row in allowed.values()],
            )
            qcancer_result = qcancer_prediction(qcancer_inputs)
            metadata.predictions = [qcancer_result]
            rules = session.scalars(select(TriggerRule).where(TriggerRule.enabled.is_(True)).order_by(TriggerRule.id)).all()
            metadata.rule_snapshots = {str(rule.id): rule_snapshot(rule) for rule in rules}
            if not rules:
                metadata.missing_information.append("No enabled demonstration rules are configured.")
            evaluations = [TriggerEvaluation.model_validate(value) for value in run_evaluator(
                pipeline, patient_id, extraction.findings, [TriggerRuleRead.model_validate(rule) for rule in rules],
                patient_facts)]
            if {value.trigger_rule_id for value in evaluations} != {rule.id for rule in rules} or len(evaluations) != len(rules):
                raise PipelineError("invalid_trigger_rule_references")
            finding_sources = {ref.observation_id for finding in extraction.findings for ref in finding.evidence}
            for value in evaluations:
                if not set(value.evidence_observation_ids).issubset(finding_sources) or (
                        value.triggered and not value.evidence_observation_ids):
                    raise PipelineError("invalid_trigger_evidence")
            for finding in extraction.findings:
                stored = ClinicalFinding(patient_id=patient_id, analysis_run_id=run.id,
                    finding_type=finding.finding_type, description=finding.description,
                    status=finding.status, uncertainty=finding.uncertainty)
                session.add(stored)
                session.flush()
                session.add_all(FindingEvidence(finding_id=stored.id, patient_id=patient_id,
                    **ref.model_dump()) for ref in finding.evidence)
            for value in evaluations:
                stored = TriggerResult(patient_id=patient_id, analysis_run_id=run.id,
                    trigger_rule_id=value.trigger_rule_id, triggered=value.triggered,
                    explanation=value.explanation, requires_clinician_review=value.triggered)
                session.add(stored)
                session.flush()
                session.add_all(TriggerResultEvidence(trigger_result_id=stored.id, patient_id=patient_id,
                    observation_id=identifier) for identifier in set(value.evidence_observation_ids))
            session.flush()
    except SQLAlchemyError:
        raise  # Route handler returns a database error; request transaction rolls back.
    except Exception as error:
        run.status = AnalysisStatus.FAILED
        metadata.error_code = error.code if isinstance(error, PipelineError) else "pipeline_execution_failed"
        metadata.predictions = []
        metadata.missing_information.append("Analysis did not complete; no clinical conclusion is available.")
    else:
        run.status = AnalysisStatus.COMPLETED
    run.details = metadata.model_dump(mode="json")
    session.commit()
    return get_analysis(session, run.id)
