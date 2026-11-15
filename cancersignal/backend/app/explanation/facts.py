"""Pure presentation of input facts. No risk assessment or feature computation."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from app.contracts.analysis import AnalysisResult
from app.explanation.schemas import ExplanationStatement, Limitation, PredictionDisplaySpec, Quantity
from app.explanation.prediction_views import qcancer_statement

# Presentation labels only; unknown producer labels are not interpreted.
FINDING_LABELS = {
    "rectal_bleeding": "Rectal bleeding", "blood_in_stool": "Rectal bleeding",
    "change_in_bowel_habit": "Change in bowel habits", "abdominal_pain": "Abdominal pain",
    "abdominal_discomfort": "Abdominal discomfort", "weight_loss": "Unintentional weight loss",
    "abdominal_mass": "Abdominal mass", "rectal_mass": "Rectal mass",
    "fatigue": "Fatigue", "new_symptom": "Documented symptom",
    "investigation_planned": "Investigation planned", "investigation_completed": "Investigation completed",
    "completed_investigation": "Investigation completed", "investigation_status_unknown": "Investigation completion unknown",
    "follow_up": "Follow-up information", "documented_observation": "Documented observation",
    "anaemia": "Anaemia finding in the source analysis",
    "iron_deficiency_anaemia": "Iron-deficiency anaemia finding in the source analysis",
    "fit_result": "FIT result",
}
FEATURE_LABELS = {"hemoglobin_change": "Haemoglobin change"}
MEASUREMENT_LABELS = {"HB": "Haemoglobin", "B-HB": "Haemoglobin", "SYNTHETIC-HB": "Haemoglobin",
                      "FERRITIN": "Ferritin", "P-FERRITIN": "Ferritin", "S-FERRITIN": "Ferritin",
                      "SYNTHETIC-FERRITIN": "Ferritin", "FIT": "FIT result",
                      "F-HB-FIT": "FIT result", "SYNTHETIC-FIT": "FIT result"}
POLARITY = {"present": "documented as present", "absent": "explicitly absent", "uncertain": "uncertain finding"}
TIMING = {"current": "current", "historical": "historical", "resolved": "resolved", "unknown": "timing unknown"}
RULE_TEXT = {"matched": "Stored rule matched. Physician review required.",
             "not_matched": "Stored rule did not match the supplied information.",
             "indeterminate": "Insufficient information to evaluate the stored rule."}
SAFE_UNIT = re.compile(r"[A-Za-z0-9µμ²³%‰°/.*^()_+−\-]{1,32}\Z")


@dataclass(frozen=True)
class Catalog:
    statements: tuple[ExplanationStatement, ...]
    required: frozenset[str]
    finding_groups: tuple[frozenset[str], ...]
    limitations: tuple[Limitation, ...]
    summary_kind: str


def quantity(slot, value, unit) -> Quantity | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    if not isinstance(unit, str) or not SAFE_UNIT.fullmatch(unit):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or len(str(parsed)) > 80 or abs(parsed.adjusted()) > 40:
        return None
    return Quantity(slot=slot, value=parsed, unit=unit)


def formatted(number: Quantity) -> str:
    # Decimal punctuation only; no rounding, conversion, scaling or calculation.
    return f"{format(number.value, 'f')} {number.unit}"


def at_path(payload, path):
    for key in path:
        if not isinstance(payload, dict) or key not in payload:
            return None
        payload = payload[key]
    return payload


def build_catalog(result: AnalysisResult, prediction_specs: tuple[PredictionDisplaySpec, ...] = ()) -> Catalog:
    statements, required, limitations, groups = [], set(), [], {}
    limits = [Limitation(code="prototype", text_en="This explanation is a prototype summary, not a diagnosis or referral decision."),
              Limitation(code="validation_scope", text_en="Source reference integrity was checked. This explanation layer does not assess calculation correctness or clinical validity.")]
    for finding in result.findings:
        key = f"finding:{finding.id}"
        ids = tuple(ref.observation_id for ref in finding.evidence)
        label = FINDING_LABELS.get(finding.finding_type, "Other documented structured finding")
        statements.append(ExplanationStatement(key=key, kind="finding", text_en=f"{label}: {POLARITY[finding.polarity]}, {TIMING[finding.temporal_status]}.",
                                              observation_ids=ids, finding_ids=(finding.id,)))
        groups.setdefault(finding.finding_type, set()).add(key)
        if finding.polarity != "present" or finding.temporal_status in ("resolved", "unknown") or finding.uncertainty or finding.missing_information:
            required.add(key)
        if finding.uncertainty or finding.polarity == "uncertain" or finding.temporal_status == "unknown":
            limitations.append(Limitation(code="uncertain_finding", text_en="The source analysis contains uncertainty about the interpretation or timing of this finding.", observation_ids=ids, related_keys=(key,)))
        if finding.finding_type not in FINDING_LABELS:
            limitations.append(Limitation(code="unmapped_finding", text_en="No detailed English label is defined for this finding; review the source analysis.", observation_ids=ids, related_keys=(key,)))
    for source in result.source_observations:
        if source.numeric_value is None:
            continue
        key = f"measurement:{source.id}"
        number = quantity("numeric_value", source.numeric_value, source.unit)
        label = MEASUREMENT_LABELS.get((source.code or "").upper(), "Documented measurement")
        text = f"{label}: {formatted(number)}." if number else "The measurement value is omitted because its unit or number format is missing or unsupported."
        statements.append(ExplanationStatement(key=key, kind="measurement", text_en=text,
                                              observation_ids=(source.id,), quantities=(number,) if number else ()))
        if number is None:
            limitations.append(Limitation(code="measurement_value_omitted", text_en=text, observation_ids=(source.id,), related_keys=(key,)))
    for feature in result.computed_features:
        key = f"feature:{feature.id}"
        label = FEATURE_LABELS.get(feature.feature_type, "Computed feature")
        number = quantity("value", feature.value, feature.unit) if feature.status == "computed" else None
        if number:
            text = f"{label}: {formatted(number)}. The value is copied from the calculation output; it is not recalculated for this explanation."
        elif feature.status == "computed":
            text = f"{label}: the numeric value is omitted because its unit or number format is unsupported."
        else:
            text = f"{label}: no valid calculated result is available."
        statements.append(ExplanationStatement(key=key, kind="feature", text_en=text,
            observation_ids=feature.evidence_observation_ids, quantities=(number,) if number else (), feature_ids=(feature.id,)))
        required.add(key)
        required.update(f"measurement:{identifier}" for identifier in feature.evidence_observation_ids
                        if any(row.id == identifier and row.numeric_value is not None for row in result.source_observations))
        if number is None or feature.input_coverage.status != "complete" or feature.missing_information:
            limitations.append(Limitation(code="limited_feature", text_en="The calculated result has missing information, limitations or an omitted numeric value.",
                observation_ids=feature.evidence_observation_ids, related_keys=(key,)))
    identities = [(spec.model_name, spec.model_version, spec.prediction_type) for spec in prediction_specs]
    if len(set(identities)) != len(identities):
        raise ValueError("Prediction display mappings must have unique model/version/type identities.")
    for index, prediction in enumerate(result.predictions):
        key = f"prediction:{index}"
        known = qcancer_statement(prediction, index)
        if known is not None:
            statement, known_limits = known
            statements.append(statement)
            required.add(key)
            limitations.extend(known_limits)
            continue
        spec = next((spec for spec in prediction_specs if (spec.model_name, spec.model_version, spec.prediction_type) ==
                     (prediction.model_name, prediction.model_version, prediction.prediction_type)), None)
        number = quantity("value", at_path(prediction.value, spec.value_path), at_path(prediction.value, spec.unit_path)) if spec and prediction.evidence_observation_ids else None
        text = (f"Separate model prediction: {formatted(number)}. A prediction is not an established clinical finding."
                if number else "The source analysis includes a separate model prediction. Its numeric value is omitted without a valid value and unit contract.")
        statements.append(ExplanationStatement(key=key, kind="prediction", text_en=text,
            observation_ids=tuple(prediction.evidence_observation_ids), quantities=(number,) if number else (), prediction_index=index))
        required.add(key)
        limitations.append(Limitation(code="prediction_not_clinically_validated", text_en="This explanation does not establish clinical validation, calibration or the meaning of the prediction scale.",
            observation_ids=tuple(prediction.evidence_observation_ids), related_keys=(key,)))
        if prediction.uncertainty:
            limitations.append(Limitation(code="prediction_uncertainty", text_en="The model output includes uncertainty. Do not treat the prediction as a certain clinical finding.",
                observation_ids=tuple(prediction.evidence_observation_ids), related_keys=(key,)))
        if number is None:
            limitations.append(Limitation(code="prediction_value_omitted", text_en="The prediction value is omitted because its value and unit cannot be verified against the display contract.", related_keys=(key,)))
    rules = {row.trigger_rule_id: row for row in result.metadata.rules}
    for evaluation in result.trigger_evaluations:
        key = f"rule:{evaluation.trigger_rule_id}"
        text = RULE_TEXT[evaluation.evaluation_status]
        if evaluation.requires_clinician_review and evaluation.evaluation_status != "matched":
            text += " Physician review required for the source result."
        statements.append(ExplanationStatement(key=key, kind="rule", text_en=text,
            observation_ids=evaluation.supporting_observation_ids, finding_ids=evaluation.supporting_finding_ids,
            feature_ids=evaluation.supporting_feature_ids, rule_reference=rules[evaluation.trigger_rule_id],
            requires_clinician_review=evaluation.requires_clinician_review))
        if evaluation.evaluation_status != "not_matched" or evaluation.requires_clinician_review:
            required.add(key)
            required.update(f"finding:{identifier}" for identifier in evaluation.supporting_finding_ids)
            required.update(f"feature:{identifier}" for identifier in evaluation.supporting_feature_ids)
        if evaluation.evaluation_status == "indeterminate":
            limitations.append(Limitation(code="indeterminate_rule", text_en="Missing or uncertain information prevents rule evaluation.",
                observation_ids=evaluation.supporting_observation_ids, related_keys=(key,)))
    missing_groups = [result.missing_information]
    missing_groups += [row.missing_information for row in (*result.findings, *result.computed_features, *result.trigger_evaluations)]
    missing_groups += [row.input_coverage.missing_information for row in result.computed_features]
    for missing in (gap for group in missing_groups for gap in group):
        limitations.append(Limitation(code="missing_information", text_en="The source analysis has missing information; review it before clinical interpretation.", observation_ids=missing.observation_ids))
    if result.issues:
        limitations.append(Limitation(code="upstream_issues", text_en="The source analysis reports processing limitations; review the original notices."))
    for group in groups.values():
        if len(group) > 1:
            ids = tuple(sorted({identifier for row in statements if row.key in group for identifier in row.observation_ids}, key=str))
            limitations.append(Limitation(code="multiple_finding_states", text_en="Multiple records describe this finding type. This explanation does not resolve potential temporal or clinical conflicts.",
                observation_ids=ids, related_keys=tuple(sorted(group))))
    outcomes = {row.evaluation_status for row in result.trigger_evaluations}
    summary = ("review_signals" if "matched" in outcomes else "indeterminate" if "indeterminate" in outcomes
               else "no_signals" if outcomes else "observations_only")
    # Keep every limitation regardless of what the model chooses to emphasize.
    unique = {}
    for row in (*limits, *limitations):
        identity = (row.code, row.text_en)
        previous = unique.get(identity)
        if previous is not None:
            row = Limitation(code=row.code, text_en=row.text_en,
                observation_ids=tuple(sorted(set(previous.observation_ids) | set(row.observation_ids), key=str)),
                related_keys=tuple(sorted(set(previous.related_keys) | set(row.related_keys))))
        unique[identity] = row
    return Catalog(tuple(statements), frozenset(required), tuple(frozenset(group) for group in groups.values()), tuple(unique.values()), summary)
