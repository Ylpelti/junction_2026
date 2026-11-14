"""Source-linked, normalized fields used by the QCancer-2013 demo adapter.

These are extraction contracts only. They do not calculate a risk or decide
whether a patient should be referred.
"""
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.contracts.common import Contract
from app.contracts.evidence import SourceReference
from app.schemas.records import NonEmpty


FEMALE_BINARY_INPUTS = frozenset({
    "b_chronicpan", "b_copd", "b_endometrial", "b_type2", "c_hb",
    "fh_breastcancer", "fh_gicancer", "fh_ovariancancer", "new_abdodist",
    "new_abdopain", "new_appetiteloss", "new_breastlump", "new_breastpain",
    "new_breastskin", "new_dysphagia", "new_gibleed", "new_haematuria",
    "new_haemoptysis", "new_heartburn", "new_imb", "new_indigestion",
    "new_necklump", "new_nightsweats", "new_pmb", "new_postcoital",
    "new_rectalbleed", "new_vte", "new_weightloss", "s1_bowelchange",
    "s1_bruising", "s1_constipation", "s1_cough",
})
MALE_BINARY_INPUTS = frozenset({
    "b_chronicpan", "b_copd", "b_type2", "c_hb", "fh_gicancer",
    "fh_prostatecancer", "new_abdodist", "new_abdopain", "new_appetiteloss",
    "new_dysphagia", "new_gibleed", "new_haematuria", "new_haemoptysis",
    "new_heartburn", "new_indigestion", "new_necklump", "new_nightsweats",
    "new_rectalbleed", "new_testespain", "new_testicularlump", "new_vte",
    "new_weightloss", "s1_bowelchange", "s1_constipation", "s1_cough",
    "s1_impotence", "s1_nocturia", "s1_urinaryfreq", "s1_urinaryretention",
})
ALL_BINARY_INPUTS = FEMALE_BINARY_INPUTS | MALE_BINARY_INPUTS
EXTRACTABLE_BINARY_INPUTS = ALL_BINARY_INPUTS - {"c_hb"}  # Derived in Python from haemoglobin.


class QCancerFactorName(StrEnum):
    B_CHRONICPAN = "b_chronicpan"
    B_COPD = "b_copd"
    B_ENDOMETRIAL = "b_endometrial"
    B_TYPE2 = "b_type2"
    FH_BREASTCANCER = "fh_breastcancer"
    FH_GICANCER = "fh_gicancer"
    FH_OVARIANCANCER = "fh_ovariancancer"
    FH_PROSTATECANCER = "fh_prostatecancer"
    NEW_ABDODIST = "new_abdodist"
    NEW_ABDOPAIN = "new_abdopain"
    NEW_APPETITELOSS = "new_appetiteloss"
    NEW_BREASTLUMP = "new_breastlump"
    NEW_BREASTPAIN = "new_breastpain"
    NEW_BREASTSKIN = "new_breastskin"
    NEW_DYSPHAGIA = "new_dysphagia"
    NEW_GIBLEED = "new_gibleed"
    NEW_HAEMATURIA = "new_haematuria"
    NEW_HAEMOPTYSIS = "new_haemoptysis"
    NEW_HEARTBURN = "new_heartburn"
    NEW_IMB = "new_imb"
    NEW_INDIGESTION = "new_indigestion"
    NEW_NECKLUMP = "new_necklump"
    NEW_NIGHT_SWEATS = "new_nightsweats"
    NEW_PMB = "new_pmb"
    NEW_POSTCOITAL = "new_postcoital"
    NEW_RECTALBLEED = "new_rectalbleed"
    NEW_TESTESPAIN = "new_testespain"
    NEW_TESTICULARLUMP = "new_testicularlump"
    NEW_VTE = "new_vte"
    NEW_WEIGHTLOSS = "new_weightloss"
    S1_BOWELCHANGE = "s1_bowelchange"
    S1_BRUISING = "s1_bruising"
    S1_CONSTIPATION = "s1_constipation"
    S1_COUGH = "s1_cough"
    S1_IMPOTENCE = "s1_impotence"
    S1_NOCTURIA = "s1_nocturia"
    S1_URINARYFREQ = "s1_urinaryfreq"
    S1_URINARYRETENTION = "s1_urinaryretention"


class QCancerNumber(Contract):
    value: Decimal | None = Field(default=None, allow_inf_nan=False)
    evidence: tuple[SourceReference, ...] = ()
    uncertainty: NonEmpty | None = None

    @model_validator(mode="after")
    def source_backed_value(self):
        ids = [ref.observation_id for ref in self.evidence]
        if len(set(ids)) != len(ids):
            raise ValueError("QCancer input evidence IDs must be unique per value.")
        if self.value is not None and not self.evidence:
            raise ValueError("A known QCancer numeric input requires source evidence.")
        return self


class QCancerSmokingInput(Contract):
    status: Literal["never", "former", "current"] | None = None
    cigarettes_per_day: QCancerNumber = Field(default_factory=QCancerNumber)
    evidence: tuple[SourceReference, ...] = ()
    uncertainty: NonEmpty | None = None

    @model_validator(mode="after")
    def source_backed_status(self):
        ids = [ref.observation_id for ref in self.evidence]
        if len(set(ids)) != len(ids):
            raise ValueError("Smoking evidence IDs must be unique.")
        if self.status is not None and not self.evidence:
            raise ValueError("A known smoking status requires source evidence.")
        return self


class QCancerBinaryInput(Contract):
    factor: QCancerFactorName
    value: StrictBool | None = None
    evidence: tuple[SourceReference, ...] = ()
    uncertainty: NonEmpty | None = None

    @model_validator(mode="after")
    def source_backed_value(self):
        ids = [ref.observation_id for ref in self.evidence]
        if len(set(ids)) != len(ids):
            raise ValueError("QCancer factor evidence IDs must be unique per factor.")
        if self.value is not None and not self.evidence:
            raise ValueError("A known QCancer yes/no input requires source evidence.")
        return self


class QCancerPredictors(Contract):
    """LLM-extracted values; absent keys or null values remain unknown."""
    bmi: QCancerNumber = Field(default_factory=QCancerNumber)
    height_cm: QCancerNumber = Field(default_factory=QCancerNumber)
    weight_kg: QCancerNumber = Field(default_factory=QCancerNumber)
    smoking: QCancerSmokingInput = Field(default_factory=QCancerSmokingInput)
    alcohol_uk_units_per_day: QCancerNumber = Field(default_factory=QCancerNumber)
    binary_factors: tuple[QCancerBinaryInput, ...] = ()

    @model_validator(mode="after")
    def no_duplicate_or_python_derived_factors(self):
        names = [str(row.factor) for row in self.binary_factors]
        if len(set(names)) != len(names):
            raise ValueError("QCancer binary factors must be unique.")
        if "c_hb" in names:
            raise ValueError("c_hb is derived from haemoglobin in Python, not extracted by the LLM.")
        return self

    def evidence_references(self) -> tuple[SourceReference, ...]:
        refs = [*self.bmi.evidence, *self.height_cm.evidence, *self.weight_kg.evidence,
                *self.smoking.evidence, *self.smoking.cigarettes_per_day.evidence,
                *self.alcohol_uk_units_per_day.evidence]
        for factor in self.binary_factors:
            refs.extend(factor.evidence)
        return tuple(refs)
