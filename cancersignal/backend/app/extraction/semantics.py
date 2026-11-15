"""Conservative English assertion grammar, NOT general clinical entailment.

Only complete, unambiguous clauses in the original source may authorize a
clinical input. Uncovered language is quarantined, never guessed. Quoted
substrings cannot remove a negation or change the experiencer. This intentionally
trades recall for safety; coverage must be measured independently.
"""
import re
from decimal import Decimal
from app.contracts.common import PipelineIssue
from app.contracts.qcancer import QCancerPredictors
from app.extraction.narrative_semantics import symptom_states, investigation_state

VERSION = "english-semantic-4"
TERMS = {
    "rectal_bleeding": r"(?:rectal bleeding|blood in (?:the )?stool|visible blood in (?:the )?stool)",
    "abdominal_pain": r"(?:abdominal pain|lower abdominal pain|stomach pain)",
    "change_in_bowel_habit": r"(?:change in bowel habit|changes in bowel habits|altered bowel habits)",
    "weight_loss": r"(?:unintentional weight loss|weight loss)",
    "rectal_mass": r"(?:rectal mass)", "abdominal_mass": r"(?:abdominal mass)",
}
FACTOR_TERMS = {"new_rectalbleed": "rectal_bleeding", "new_abdopain": "abdominal_pain",
                "new_weightloss": "weight_loss", "s1_bowelchange": "change_in_bowel_habit"}


def clauses(text):
    return [s.strip().lower().removeprefix("synthetic — ") for s in re.split(r"(?<!\d)\.|\.(?!\d)|[!?;\n]+", text or "") if s.strip()]


def assertions(kind, source):
    term = TERMS.get(kind)
    if term is None:
        return set()
    patterns = {
        ("present", "current"): rf"(?:(?:patient (?:reports|has)|reports|has|ongoing|current) )?{term}(?: now| today| continues| persists)?",
        ("absent", "current"): rf"(?:(?:patient )?denies|no) {term}(?: now| today)?",
        ("uncertain", "unknown"): rf"(?:possible|uncertain) {term}",
        ("present", "resolved"): rf"(?:previous |prior )?{term} (?:has resolved|resolved|has stopped)",
        ("present", "historical"): rf"(?:history of|previous|prior) {term}",
    }
    basic = {state for state, pattern in patterns.items()
             if any(re.fullmatch(pattern, clause) for clause in clauses(source.text))}
    return basic | set().union(*(symptom_states(kind, c) for c in clauses(source.text)))


def finding_reason(finding, sources, note_id):
    states = set()
    for ref in finding.evidence:
        source = sources[ref.observation_id]
        # Use complete source clauses, and require the quote to cover the clause.
        supported = source.model_copy(update={"text": ". ".join(
            c for c in clauses(source.text) if c in (ref.source_excerpt or "").lower())})
        observed = assertions(finding.finding_type, supported)
        if source.id != note_id:
            observed = {(p, "historical" if t == "current" else t) for p, t in observed}
        states.update(observed)
    if finding.finding_type.startswith("investigation_"):
        state = finding.finding_type.removeprefix("investigation_")
        if state == "status_unknown" and finding.polarity == "uncertain" and finding.temporal_status == "unknown":
            if any(clause == "no colonoscopy result available" and clause in ref.source_excerpt.lower()
                   for ref in finding.evidence for clause in clauses(sources[ref.observation_id].text)):
                return None  # Missing results support uncertainty, never non-completion.
        phrases = {"planned": "planned", "referred": "referred", "scheduled": "scheduled",
                   "completed": "completed", "cancelled": "cancelled", "status_unknown": "completion unknown"}
        expected = phrases.get(state)
        matches = []
        for ref in finding.evidence:
            source = sources[ref.observation_id]
            for clause in clauses(source.text):
                if expected and (re.fullmatch(rf"colonoscopy (?:was |is )?{expected}", clause) or investigation_state(clause) == state) and clause in ref.source_excerpt.lower():
                    matches.append(source.id == note_id)
        if matches and finding.polarity == "uncertain" and finding.uncertainty:
            if finding.temporal_status == "unknown" or finding.temporal_status == ("current" if all(matches) else "historical"):
                return None
            return "polarity_or_temporality_mismatch"
        if matches and finding.polarity == "present" and finding.temporal_status == ("current" if all(matches) else "historical"):
            return None
        return "investigation_state_not_supported"
    if not states:
        return "outside_assertion_grammar"
    if finding.polarity == "uncertain" or finding.temporal_status == "unknown":
        return None  # Retained uncertainty cannot become a positive legacy rule input.
    if states == {("present", "resolved")} and (finding.polarity, finding.temporal_status) == ("absent", "resolved"):
        return None  # An explicitly resolved symptom can be represented as now absent.
    if len(states) > 1:
        return "conflicting_source_assertions"
    if (finding.polarity, finding.temporal_status) not in states:
        return "polarity_or_temporality_mismatch"
    # Other supplied current clauses may contradict a cherry-picked reference.
    current_states = set().union(*(assertions(finding.finding_type, s) for s in sources.values() if s.id == note_id))
    if finding.temporal_status == "current" and any(s != (finding.polarity, finding.temporal_status) for s in current_states):
        return "conflicting_current_assertions"
    return None


def validate_semantics(findings, predictors, sources, note_id):
    index = {s.id: s for s in sources}
    retained, issues, rejected = [], [], []
    def reject(path, reason):
        rejected.append({"path": path, "reason": reason})
        issues.append(PipelineIssue(code="semantic_rejection", component=VERSION, severity="warning",
                                    message=f"{path}: {reason}; no conclusion may be drawn from the rejected value."))
    for i, finding in enumerate(findings):
        reason = finding_reason(finding, index, note_id)
        if reason:
            reject(f"findings[{i}]", reason)
        else:
            # Never publish unchecked model prose as a clinical assertion.
            retained.append(finding.model_copy(update={"description":
                f"{finding.finding_type}: {finding.polarity}, {finding.temporal_status}."}))
    data = predictors.model_dump()
    # Numbers require typed structured measurement support; prose conversions and
    # historical lifestyle values are deliberately outside this grammar.
    for key in ("bmi", "height_cm", "weight_kg", "alcohol_uk_units_per_day"):
        row = getattr(predictors, key)
        if row.value is not None:
            units = {"bmi": r"bmi ([0-9]+(?:\.[0-9]+)?) kg/m[²2]", "height_cm": r"height ([0-9]+(?:\.[0-9]+)?) cm",
                     "weight_kg": r"weight ([0-9]+(?:\.[0-9]+)?) kg",
                     "alcohol_uk_units_per_day": r"alcohol ([0-9]+(?:\.[0-9]+)?) uk units per day"}
            values = {Decimal(m.group(1)) for ref in row.evidence if ref.observation_id == note_id
                      for clause in clauses(index[ref.observation_id].text)
                      if clause in ref.source_excerpt.lower() and (m := re.fullmatch(units[key], clause))}
            all_values = {Decimal(m.group(1)) for source in sources if source.id == note_id
                          for clause in clauses(source.text) if (m := re.fullmatch(units[key], clause))}
            if values == {row.value} and all_values == {row.value} and all(ref.observation_id == note_id for ref in row.evidence):
                continue
            reject(f"qcancer.{key}", "numeric_semantics_not_verified")
            data[key] = {"uncertainty": "Numeric semantics not verified."}
    smoking = predictors.smoking
    if smoking.status is not None or smoking.cigarettes_per_day.value is not None:
        patterns = {"never": r"patient has never smoked", "former": r"patient is a former smoker",
                    "current": r"patient currently smokes"}
        refs = smoking.evidence
        ok = bool(refs) and all(r.observation_id == note_id for r in refs)
        observed = {state for state, pattern in patterns.items() for r in refs
                    for clause in clauses(index[r.observation_id].text)
                    if re.fullmatch(pattern, clause) and clause in r.source_excerpt.lower()}
        current_clauses = [c for s in sources if s.id == note_id for c in clauses(s.text)]
        contradicted = any(re.fullmatch(r"(?:patient )?does not (?:currently )?smoke", c) for c in current_clauses)
        all_states = {state for state, pattern in patterns.items() for c in current_clauses if re.fullmatch(pattern, c)}
        if not ok or contradicted or all_states != {smoking.status} or observed != {smoking.status} or smoking.cigarettes_per_day.value is not None:
            reject("qcancer.smoking", "smoking_status_or_amount_not_supported")
            data["smoking"] = {"uncertainty": "Current smoking status or amount is not established."}
    factors = []
    for factor in predictors.binary_factors:
        if factor.value is None:
            factors.append(factor.model_dump()); continue
        kind = FACTOR_TERMS.get(str(factor.factor))
        observed = set()
        if kind:
            for ref in factor.evidence:
                if ref.observation_id == note_id:
                    source = index[ref.observation_id]
                    supported = source.model_copy(update={"text": ". ".join(c for c in clauses(source.text) if c in ref.source_excerpt.lower())})
                    observed.update(assertions(kind, supported))
        expected = ("present" if factor.value else "absent", "current")
        all_current = set().union(*(assertions(kind, source) for source in sources if source.id == note_id)) if kind else set()
        if observed != {expected} or all_current != {expected} or any(r.observation_id != note_id for r in factor.evidence):
            reject(f"qcancer.{factor.factor}", "current_predictor_not_supported")
            factors.append({"factor": factor.factor, "value": None, "uncertainty": "Current predictor not established."})
        else:
            factors.append(factor.model_dump())
    data["binary_factors"] = factors
    # Validation of supplied assertions cannot establish extraction completeness.
    # In particular, [] is not evidence that the source contains no findings.
    issues.append(PipelineIssue(code="extraction_coverage_incomplete", component=VERSION,
        severity="warning", message="Extraction coverage is incomplete or unverified. Omitted or rejected findings are unknown, not confirmed clinical negatives."))
    diagnostics = {"version": VERSION, "finding_count": len(findings), "retained_findings": len(retained),
                   "rejected": rejected, "coverage": "bounded_assertion_grammar",
                   "coverage_status": "incomplete", "omission_detection": "not_assessed",
                   "clinical_validation": "not_assessed"}
    return tuple(retained), QCancerPredictors.model_validate(data), tuple(issues), diagnostics
