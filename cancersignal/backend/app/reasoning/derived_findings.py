"""Turn laboratory observations into colorectal vocabulary findings, in Python.

Each derived finding cites the lab observation(s) it came from, so it passes the
same evidence checks as extracted findings (analysis_service.verify_findings).
Only the latest value of each lab before time t is used; the caller passes
history that is already limited to the patient and to before t.

Derived findings are `current`: the latest value describes the patient at time t.
Whether an anaemia was already investigated (and is therefore `resolved`) is a
reconciliation decision that is not implemented yet.
"""

from collections.abc import Iterable
from decimal import Decimal

from app.models.enums import FindingStatus, ObservationType
from app.reasoning.vocabulary import ANAEMIA, FIT_RESULT, FIT_UNIT, IRON_DEFICIENCY_ANAEMIA
from app.schemas.analysis import EvidenceReference, StructuredFinding
from app.schemas.records import ObservationRead

# Lab codes mapped to an analyte. Compared case-insensitively.
# LOINC 718-7 "Hemoglobin [Mass/volume] in Blood"; 2276-4 "Ferritin [Mass/volume] in Serum or Plasma".
# FIT has no verified LOINC code in ug Hb/g faeces (58453-2 is Mass/volume), so it stays local.
HB_CODES = frozenset({"SYNTHETIC-HB", "B-HB", "HB", "HGB", "718-7"})
FERRITIN_CODES = frozenset({"SYNTHETIC-FERRITIN", "P-FERRITIN", "S-FERRITIN", "FERRITIN", "2276-4"})
FIT_CODES = frozenset({"SYNTHETIC-FIT", "F-HB-FIT", "FIT"})

# DEMO reference range, not clinically validated. Replace when labs store their own ranges.
HB_LOWER_LIMIT_G_PER_L = {"female": Decimal("117"), "male": Decimal("134")}
HB_RANGE_TEXT = {"female": "117–155 g/l", "male": "134–167 g/l"}
# DEMO reference range, not clinically validated.
FERRITIN_LOW_UG_PER_L = Decimal("15")


def normalise_unit(unit: str | None) -> str:
    """Comparison key only; findings keep the source unit unchanged."""
    return (unit or "").strip().lower().replace("µ", "u").replace("μ", "u")


def evidence_for(record: ObservationRead) -> EvidenceReference:
    if record.text:
        return EvidenceReference(observation_id=record.id, source_excerpt=record.text,
                                 start_offset=0, end_offset=len(record.text))
    # Measurements without text are allowed as evidence without a quote.
    return EvidenceReference(observation_id=record.id)


def latest(records: Iterable[ObservationRead], codes: frozenset[str]) -> ObservationRead | None:
    matching = [r for r in records if r.code and r.code.upper() in codes and r.numeric_value is not None]
    if not matching:
        return None
    return max(matching, key=lambda r: (r.observed_at, r.recorded_at, str(r.id)))


def derive_lab_findings(history: Iterable[ObservationRead], *, sex: str | None) -> tuple[list[StructuredFinding], list[str]]:
    """Return (findings, missing_information) derived from laboratory history before time t."""
    labs = [r for r in history if r.observation_type == ObservationType.LABORATORY]
    findings: list[StructuredFinding] = []
    missing: list[str] = []

    known = HB_CODES | FERRITIN_CODES | FIT_CODES
    for code in sorted({r.code for r in labs if r.code and r.code.upper() not in known}):
        missing.append(f"Laboratory code {code} is not mapped to a colorectal finding.")

    hb = latest(labs, HB_CODES)
    ferritin = latest(labs, FERRITIN_CODES)
    if hb is not None:
        sex_key = str(sex) if sex is not None else ""
        lower = HB_LOWER_LIMIT_G_PER_L.get(sex_key)
        if normalise_unit(hb.unit) != "g/l":
            missing.append(f"Haemoglobin {hb.id} has unit {hb.unit!r}; only g/l is supported, so anaemia was not assessed.")
        elif lower is None:
            missing.append("Patient sex is not female or male; no demo haemoglobin reference range applies, so anaemia was not assessed.")
        elif hb.numeric_value < lower:
            day = hb.observed_at.date().isoformat()
            findings.append(StructuredFinding(
                finding_type=ANAEMIA, status=FindingStatus.CURRENT, evidence=[evidence_for(hb)],
                description=(f"Latest haemoglobin {hb.numeric_value.normalize():f} {hb.unit} on {day} is below the "
                             f"demo reference range for {sex_key} patients ({HB_RANGE_TEXT[sex_key]})."),
            ))
            if ferritin is None:
                missing.append("No ferritin result before this note; iron deficiency could not be assessed.")
            elif normalise_unit(ferritin.unit) != "ug/l":
                missing.append(f"Ferritin {ferritin.id} has unit {ferritin.unit!r}; only ug/l is supported.")
            elif ferritin.numeric_value < FERRITIN_LOW_UG_PER_L:
                findings.append(StructuredFinding(
                    finding_type=IRON_DEFICIENCY_ANAEMIA, status=FindingStatus.CURRENT,
                    evidence=[evidence_for(hb), evidence_for(ferritin)],
                    description=(f"Anaemia with latest ferritin {ferritin.numeric_value.normalize():f} {ferritin.unit} "
                                 f"on {ferritin.observed_at.date().isoformat()}, below the demo limit of 15 ug/l."),
                ))
    else:
        missing.append("No haemoglobin result before this note.")

    fit = latest(labs, FIT_CODES)
    if fit is not None:
        if fit.unit != FIT_UNIT:
            missing.append(f"FIT result {fit.id} has unit {fit.unit!r}; rules expect {FIT_UNIT}.")
        # numeric_value and unit are copied unchanged so the source-value check passes.
        findings.append(StructuredFinding(
            finding_type=FIT_RESULT, status=FindingStatus.CURRENT, evidence=[evidence_for(fit)],
            numeric_value=fit.numeric_value, unit=fit.unit,
            description=f"Latest FIT {fit.numeric_value.normalize():f} {fit.unit} on {fit.observed_at.date().isoformat()}.",
        ))

    return findings, missing
