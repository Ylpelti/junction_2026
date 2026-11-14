"""Shared colorectal finding vocabulary (docs/rulebook-colorectal.md).

Extraction, derived lab findings, seeded rules and tests import these names so
that a rule can only refer to a finding type that some producer can emit.
"""

# From note text (extraction).
RECTAL_BLEEDING = "rectal_bleeding"
CHANGE_IN_BOWEL_HABIT = "change_in_bowel_habit"
ABDOMINAL_PAIN = "abdominal_pain"
WEIGHT_LOSS = "weight_loss"
ABDOMINAL_MASS = "abdominal_mass"
RECTAL_MASS = "rectal_mass"

# From laboratory observations, computed in Python (derived_findings.py).
ANAEMIA = "anaemia"
IRON_DEFICIENCY_ANAEMIA = "iron_deficiency_anaemia"
FIT_RESULT = "fit_result"

FIT_UNIT = "ug/g"

NOTE_FINDINGS = frozenset({RECTAL_BLEEDING, CHANGE_IN_BOWEL_HABIT, ABDOMINAL_PAIN, WEIGHT_LOSS, ABDOMINAL_MASS, RECTAL_MASS})
LAB_FINDINGS = frozenset({ANAEMIA, IRON_DEFICIENCY_ANAEMIA, FIT_RESULT})
ALL_FINDINGS = NOTE_FINDINGS | LAB_FINDINGS

# Patient-level facts usable in {"kind": "patient"} rule conditions. Not findings.
AGE_YEARS = "age_years"
PATIENT_FACTS = frozenset({AGE_YEARS})
