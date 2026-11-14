"""QCancer-2013 equations and a strict adapter to Junction's prediction contract.

The published equations are a UK model for the chance of a currently undiagnosed
cancer being diagnosed over the following two years. They are reproduced here
for synthetic demonstration only. See docs/risk-models.md and AGPL-3.0.txt.
"""

# Copyright 2013 ClinRisk Ltd. The formula implementation is licensed under
# GNU AGPL version 3 or later; see AGPL-3.0.txt.
# Python translation based on the open QCancer-2013 equations and ClinRisk's
# published reference C modules. Reference Python port inspected:
# https://huggingface.co/spaces/InstaDeepAI/sentinel/blob/main/src/sentinel/risk_models/qcancer.py
# Original C references:
# https://github.com/nhsland/clinrisk-modules/tree/master/qCancer

import math
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.contracts.common import Contract
from app.contracts.qcancer import (
    ALL_BINARY_INPUTS, FEMALE_BINARY_INPUTS, MALE_BINARY_INPUTS,
)
from app.contracts.predictions import ModelPrediction

QCANCER_NOTICE = (
    "The initial version of this file, to be found at http://svn.clinrisk.co.uk/opensource/qcancer, "
    "faithfully implements QCancer-2013. We have released this code under the GNU Affero General Public "
    "License to enable others to implement the algorithm faithfully. However, the nature of the GNU Affero "
    "Public License is such that we cannot prevent, for example, someone accidentally altering the coefficients, "
    "getting the inputs wrong, or just poor programming. We stress, therefore, that it is the responsibility of "
    "the end user to check that the source that they receive produces the same results as the original code posted "
    "at http://svn.clinrisk.co.uk/opensource/qcancer. Inaccurate implementations of risk scores can lead to wrong "
    "patients being given the wrong treatment."
)

MODEL_NAME = "QCancer-2013"
MODEL_VERSION = "QCancer-2013-open-source"

FEMALE_CANCER_TYPES = (
    "blood_cancer", "breast_cancer", "cervical_cancer", "colorectal_cancer",
    "gastro_oesophageal_cancer", "lung_cancer", "other_cancer", "ovarian_cancer",
    "pancreatic_cancer", "renal_tract_cancer", "uterine_cancer",
)
MALE_CANCER_TYPES = (
    "blood_cancer", "colorectal_cancer", "gastro_oesophageal_cancer", "lung_cancer",
    "other_cancer", "pancreatic_cancer", "prostate_cancer", "renal_tract_cancer",
    "testicular_cancer",
)

class QCancer2013Input(Contract):
    """Structured, time-scoped inputs. Unknown facts stay None; they are never false."""

    patient_id: UUID
    as_of: AwareDatetime
    sex: str | None = None
    age_years: StrictInt | None = None
    bmi: float | None = Field(default=None, allow_inf_nan=False)
    town: float | None = Field(default=None, allow_inf_nan=False)
    alcohol_cat4: StrictInt | None = None
    smoke_cat: StrictInt | None = None
    binary_factors: dict[str, StrictBool | None] = Field(default_factory=dict)
    evidence_observation_ids: tuple[UUID, ...] = ()

    @field_validator("bmi", "town", mode="before")
    @classmethod
    def numeric_inputs_are_json_numbers(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("BMI and Townsend score must be JSON numbers")
        return float(value)

    @model_validator(mode="after")
    def known_factor_names_and_unique_sources(self):
        if set(self.binary_factors) - ALL_BINARY_INPUTS:
            raise ValueError("binary_factors contains a key not used by QCancer-2013")
        if len(set(self.evidence_observation_ids)) != len(self.evidence_observation_ids):
            raise ValueError("evidence_observation_ids must be unique")
        return self


class QCancer2013Output(Contract):
    status: Literal["calculated", "insufficient_data", "invalid_input", "unsupported_input"]
    horizon_years: int = 2
    any_cancer_risk_percent: float | None = None
    colorectal_cancer_risk_percent: float | None = None
    cancer_site_risks_percent: dict[str, float] | None = None
    missing_inputs: tuple[str, ...] = ()
    invalid_inputs: tuple[str, ...] = ()
    population: str = "UK primary care; model ages 25–89"
    limitations: tuple[str, ...] = (
        "QCancer-2013 was developed for UK primary care; it has not been calibrated or clinically validated for Finland.",
        "The Junction synthetic demo uses Townsend score 0 as a placeholder, not a Finnish deprivation score.",
        "This is a prototype estimate, not a diagnosis, referral decision, or Finnish clinical recommendation.",
    )
    source_notice: str = QCANCER_NOTICE


def blood_cancer_female_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_haematuria: int,
    new_necklump: int,
    new_nightsweats: int,
    new_pmb: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_bruising: int,
) -> float:
    """Blood Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    a = 0.0
    a += age_1 * 35.94056668962831
    a += age_2 * -68.84963759779045
    a += bmi_1 * 0.0785171223057502
    a += bmi_2 * -5.373062778868142
    a += c_hb * 1.703586650229763
    a += new_abdopain * 0.3779206239385798
    a += new_haematuria * 0.40866629745988947
    a += new_necklump * 2.9539029476671903
    a += new_nightsweats * 1.3792892192392403
    a += new_pmb * 0.46892163134409925
    a += new_vte * 0.6036630662990674
    a += new_weightloss * 0.8963398932306316
    a += s1_bowelchange * 0.729137961246862
    a += s1_bruising * 1.0255003552753392
    return a + -7.420784948256575

def breast_cancer_female_score(
    age: int,
    alcohol_cat4: int,
    bmi: float,
    fh_breastcancer: int,
    new_breastlump: int,
    new_breastpain: int,
    new_breastskin: int,
    new_pmb: int,
    new_vte: int,
    town: float,
) -> float:
    """Breast Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529
    town -= -0.383295059204102

    Ialcohol = [0.0, 0.054381307594513456, 0.12457099729838178, 0.18551986792615147]

    a = 0.0
    a += Ialcohol[alcohol_cat4]
    a += age_1 * -14.30294840678985
    a += age_2 * -25.930181137736426
    a += bmi_1 * -1.75409838256809
    a += bmi_2 * 2.0601979121740364
    a += town * -0.016076697263223444
    a += fh_breastcancer * 0.3863899675953914
    a += new_breastlump * 3.9278533274888368
    a += new_breastpain * 0.8779616078329102
    a += new_breastskin * 2.232029623398788
    a += new_pmb * 0.44650530022483
    a += new_vte * 0.27286102972131654
    return a + -6.1261694200869234

def cervical_cancer_female_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_haematuria: int,
    new_imb: int,
    new_pmb: int,
    new_postcoital: int,
    new_vte: int,
    smoke_cat: int,
    town: float,
) -> float:
    """Cervical Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529
    town -= -0.383295059204102

    Ismoke = [
        0.0,
        0.32478752770957153,
        0.7541211259076739,
        0.744834303513966,
        0.6328348533913807,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 10.16633931075058
    a += age_2 * -16.91189024911
    a += bmi_1 * -0.5675143308052615
    a += bmi_2 * -2.6377586334504044
    a += town * 0.0573200669650633
    a += c_hb * 1.2205973555195053
    a += new_abdopain * 0.7229870191773574
    a += new_haematuria * 1.6126499968790107
    a += new_imb * 1.9527008812518938
    a += new_pmb * 3.3618997560756485
    a += new_postcoital * 3.1391568551730864
    a += new_vte * 1.1276327958138455
    return a + -8.830909844440193

def colorectal_cancer_female_score(
    age: int,
    alcohol_cat4: int,
    bmi: float,
    c_hb: int,
    fh_gicancer: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_rectalbleed: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_constipation: int,
) -> float:
    """Colorectal Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    Ialcohol = [0.0, 0.24290142628846959, 0.2359224520197608, 0.4606605934539446]

    a = 0.0
    a += Ialcohol[alcohol_cat4]
    a += age_1 * -11.617560661639077
    a += age_2 * -42.90980576868702
    a += bmi_1 * -0.5344237822753053
    a += bmi_2 * 2.6900552265408226
    a += c_hb * 1.4759238359186861
    a += fh_gicancer * 0.4044501048847998
    a += new_abdodist * 0.663007428785656
    a += new_abdopain * 1.4990872468711913
    a += new_appetiteloss * 0.5068020107261922
    a += new_rectalbleed * 2.7491673095810105
    a += new_vte * 0.7072816884002933
    a += new_weightloss * 1.0288860866585736
    a += s1_bowelchange * 0.7664414123199643
    a += s1_constipation * 0.33751581231211736
    return a + -7.546694878967094

def gastro_oesophageal_cancer_female_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_heartburn: int,
    new_indigestion: int,
    new_vte: int,
    new_weightloss: int,
    smoke_cat: int,
) -> float:
    """Gastro Oesophageal Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    Ismoke = [
        0.0,
        0.21088353859940934,
        0.4020914846651602,
        0.8497119766959212,
        1.102058546972454,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 5.512793295816083
    a += age_2 * -70.27340629161618
    a += bmi_1 * 2.6063377632938987
    a += bmi_2 * -1.2389834515079798
    a += c_hb * 1.2479756970482034
    a += new_abdopain * 0.7825304005124729
    a += new_appetiteloss * 0.6514592236889244
    a += new_dysphagia * 3.775171491065686
    a += new_gibleed * 1.4264472204617833
    a += new_heartburn * 0.8178746069193373
    a += new_indigestion * 1.4998439683677578
    a += new_vte * 0.7199894658172599
    a += new_weightloss * 1.2287925630053846
    return a + -8.874603161025076

def lung_cancer_female_score(
    age: int,
    b_copd: int,
    bmi: float,
    c_hb: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_haemoptysis: int,
    new_indigestion: int,
    new_necklump: int,
    new_vte: int,
    new_weightloss: int,
    s1_cough: int,
    smoke_cat: int,
    town: float,
) -> float:
    """Lung Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529
    town -= -0.383295059204102

    Ismoke = [
        0.0,
        1.3397416191950409,
        1.9500839456663224,
        2.1881694694325233,
        2.4828660433307768,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * -117.24057375029625
    a += age_2 * 25.17022547412681
    a += bmi_1 * 2.584548813392435
    a += bmi_2 * -0.6083523966762799
    a += town * 0.040692046183056746
    a += b_copd * 0.7942901962671365
    a += c_hb * 0.8627980324401628
    a += new_appetiteloss * 0.7170232121379446
    a += new_dysphagia * 0.6718426806077323
    a += new_haemoptysis * 2.9286439157734474
    a += new_indigestion * 0.36348937301142736
    a += new_necklump * 1.209724038009159
    a += new_vte * 0.8907072670032341
    a += new_weightloss * 1.1384524885073082
    a += s1_cough * 0.6439917053275602
    return a + -8.64490029717897

def other_cancer_female_score(
    age: int,
    alcohol_cat4: int,
    b_copd: int,
    bmi: float,
    c_hb: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_breastlump: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_haematuria: int,
    new_indigestion: int,
    new_necklump: int,
    new_pmb: int,
    new_vte: int,
    new_weightloss: int,
    s1_constipation: int,
    smoke_cat: int,
) -> float:
    """Other Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    Ialcohol = [0.0, 0.11292925170889954, 0.13891832056179676, 0.3428114766789586]

    Ismoke = [
        0.0,
        0.06438397925516476,
        0.18750681016606915,
        0.3754052152821668,
        0.5007337952210844,
    ]

    a = 0.0
    a += Ialcohol[alcohol_cat4]
    a += Ismoke[smoke_cat]
    a += age_1 * 35.82089873022048
    a += age_2 * -68.32947410377191
    a += bmi_1 * 1.8969796480108396
    a += bmi_2 * -3.7755945945329574
    a += b_copd * 0.28230214291079436
    a += c_hb * 1.0476364795173587
    a += new_abdodist * 0.9628688090459262
    a += new_abdopain * 0.833571006671561
    a += new_appetiteloss * 0.8450972438476546
    a += new_breastlump * 1.0400807427059522
    a += new_dysphagia * 0.8905342895684596
    a += new_gibleed * 0.38396322651340786
    a += new_haematuria * 0.6143184647549448
    a += new_indigestion * 0.24570160029924543
    a += new_necklump * 2.1666504706191545
    a += new_pmb * 0.4219383252623541
    a += new_vte * 1.063078486173392
    a += new_weightloss * 1.1058752771736007
    a += s1_constipation * 0.37801436412994915
    return a + -6.786450166859431

def ovarian_cancer_female_score(
    age: int,
    bmi: float,
    c_hb: int,
    fh_ovariancancer: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_haematuria: int,
    new_indigestion: int,
    new_pmb: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
) -> float:
    """Ovarian Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    a = 0.0
    a += age_1 * -61.083181446256894
    a += age_2 * 20.30286127011069
    a += bmi_1 * -2.1261135335028407
    a += bmi_2 * 3.216820040877247
    a += c_hb * 1.3625636791018674
    a += fh_ovariancancer * 1.995177480995183
    a += new_abdodist * 2.9381020883363806
    a += new_abdopain * 1.7307824546132513
    a += new_appetiteloss * 1.0606947909647773
    a += new_haematuria * 0.4958835997468108
    a += new_indigestion * 0.38437310274939984
    a += new_pmb * 1.5869592940878865
    a += new_vte * 1.6839747529852673
    a += new_weightloss * 0.4774332393821721
    a += s1_bowelchange * 0.6849850007182314
    return a + -7.560992964449132

def pancreatic_cancer_female_score(
    age: int,
    b_chronicpan: int,
    b_type2: int,
    bmi: float,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_indigestion: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    smoke_cat: int,
) -> float:
    """Pancreatic Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    Ismoke = [
        0.0,
        -0.06313018481520442,
        0.35236959505289345,
        0.7146003670327157,
        0.8073207410335441,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * -6.8219654517231225
    a += age_2 * -65.64048973051887
    a += bmi_1 * 3.971555945899573
    a += bmi_2 * -3.11611079991305
    a += b_chronicpan * 1.1948138830441282
    a += b_type2 * 0.7951745325664703
    a += new_abdopain * 1.9230379689782926
    a += new_appetiteloss * 1.520956825988857
    a += new_dysphagia * 1.0107551560302726
    a += new_gibleed * 0.9324059153254259
    a += new_indigestion * 1.113401261663144
    a += new_vte * 1.4485586969016084
    a += new_weightloss * 1.5791912580663912
    a += s1_bowelchange * 0.9361738611941445
    return a + -9.27821296786576

def renal_tract_cancer_female_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_haematuria: int,
    new_indigestion: int,
    new_pmb: int,
    new_weightloss: int,
    smoke_cat: int,
) -> float:
    """Renal Tract Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    Ismoke = [
        0.0,
        0.27521757277393727,
        0.5498656631475861,
        0.653624218213668,
        0.905376366178588,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * -0.03232265696266175
    a += age_2 * -56.35514107866358
    a += bmi_1 * 1.210391053577933
    a += bmi_2 * -4.7221299079939785
    a += c_hb * 1.2666531852544143
    a += new_abdopain * 0.6155954984707595
    a += new_appetiteloss * 0.684218459467602
    a += new_haematuria * 4.179144453724154
    a += new_indigestion * 0.5694329224821875
    a += new_pmb * 1.2541097882792864
    a += new_weightloss * 0.7711610560290518
    return a + -8.944077555377625

def uterine_cancer_female_score(
    age: int,
    b_endometrial: int,
    b_type2: int,
    bmi: float,
    new_abdopain: int,
    new_haematuria: int,
    new_imb: int,
    new_pmb: int,
    new_vte: int,
) -> float:
    """Uterine Cancer log-hazard score."""
    dage = age / 10.0
    age_1 = math.pow(dage, -2)
    age_2 = math.pow(dage, -2) * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = math.pow(dbmi, -2) * math.log(dbmi)

    age_1 -= 0.039541322737932
    age_2 -= 0.063867323100567
    bmi_1 -= 0.151021569967270
    bmi_2 -= 0.142740502953529

    a = 0.0
    a += age_1 * 2.7778124257317254
    a += age_2 * -59.53335145666333
    a += bmi_1 * 3.7623897936404322
    a += bmi_2 * -26.804545007465432
    a += b_endometrial * 0.8742311851235286
    a += b_type2 * 0.2655181024063556
    a += new_abdopain * 0.689195383673558
    a += new_haematuria * 1.6798617740998527
    a += new_imb * 1.7853122923827887
    a += new_pmb * 4.47701998760674
    a += new_vte * 1.036205861676167
    return a + -8.993139082256404

def blood_cancer_male_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_haematuria: int,
    new_haemoptysis: int,
    new_indigestion: int,
    new_necklump: int,
    new_nightsweats: int,
    new_testicularlump: int,
    new_vte: int,
    new_weightloss: int,
    town: float,
) -> float:
    """Blood Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620
    town -= -0.264977723360062

    a = 0.0
    a += age_1 * 3.497017935455661
    a += age_2 * -1.0806801421562633
    a += bmi_1 * 0.9519259479511792
    a += bmi_2 * 0.17146693584100858
    a += town * -0.02770624267524916
    a += c_hb * 1.8905802113004144
    a += new_abdodist * 0.8430432197211394
    a += new_abdopain * 0.6226473288294992
    a += new_appetiteloss * 1.067215038075376
    a += new_dysphagia * 0.5419443056595199
    a += new_haematuria * 0.46075380853635217
    a += new_haemoptysis * 0.9501446899241837
    a += new_indigestion * 0.5635686569331337
    a += new_necklump * 3.1567783466839603
    a += new_nightsweats * 1.5201300180753576
    a += new_testicularlump * 0.9957524928245107
    a += new_vte * 0.6142589726132867
    a += new_weightloss * 1.2233663263194712
    return a + -7.259128946685028

def colorectal_cancer_male_score(
    age: int,
    alcohol_cat4: int,
    bmi: float,
    c_hb: int,
    fh_gicancer: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_rectalbleed: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_constipation: int,
) -> float:
    """Colorectal Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620

    Ialcohol = [0.0, 0.06744317002685918, 0.2894952197787854, 0.44195399849740974]

    a = 0.0
    a += Ialcohol[alcohol_cat4]
    a += age_1 * 7.265284251403637
    a += age_2 * -2.3119103657424414
    a += bmi_1 * 0.4591530847132721
    a += bmi_2 * 0.14026516690905994
    a += c_hb * 1.4066322376473517
    a += fh_gicancer * 0.40572853210100446
    a += new_abdodist * 1.3572627165452165
    a += new_abdopain * 1.5179997924486877
    a += new_appetiteloss * 0.5421335457752113
    a += new_rectalbleed * 2.8846500840638964
    a += new_weightloss * 1.1082218896963933
    a += s1_bowelchange * 1.2962496832506105
    a += s1_constipation * 0.2284256115498967
    return a + -7.687634276522626

def gastro_oesophageal_cancer_male_score(
    age: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_heartburn: int,
    new_indigestion: int,
    new_necklump: int,
    new_weightloss: int,
    smoke_cat: int,
) -> float:
    """Gastro Oesophageal Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620

    Ismoke = [
        0.0,
        0.3532685922239948,
        0.6343201557712291,
        0.6500819736904159,
        0.6273413010559953,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 8.584150931291562
    a += age_2 * -2.765040945011636
    a += bmi_1 * 4.181675283107032
    a += bmi_2 * 0.624710628895496
    a += c_hb * 1.106554304945946
    a += new_abdopain * 1.0280133043080188
    a += new_appetiteloss * 1.1868017500634926
    a += new_dysphagia * 3.825319942864257
    a += new_gibleed * 1.8454733322333583
    a += new_heartburn * 1.172767916931312
    a += new_indigestion * 1.8843639195644077
    a += new_necklump * 0.8414696385393358
    a += new_weightloss * 1.4698638306735652
    return a + -8.420870027030062

def lung_cancer_male_score(
    age: int,
    b_copd: int,
    bmi: float,
    c_hb: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_haemoptysis: int,
    new_indigestion: int,
    new_necklump: int,
    new_nightsweats: int,
    new_vte: int,
    new_weightloss: int,
    s1_cough: int,
    smoke_cat: int,
    town: float,
) -> float:
    """Lung Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620
    town -= -0.264977723360062

    Ismoke = [
        0.0,
        0.8408574737524465,
        1.4966499028172435,
        1.7072509513243501,
        1.8882615411851338,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 11.917808960225496
    a += age_2 * -3.8503786390624457
    a += bmi_1 * 1.860558422294992
    a += bmi_2 * -0.11327500388008699
    a += town * 0.028574570361074178
    a += b_copd * 0.5526127629694074
    a += c_hb * 0.8243789117069311
    a += new_abdopain * 0.39964248791030577
    a += new_appetiteloss * 0.7487413720163385
    a += new_dysphagia * 1.0410482089004374
    a += new_haemoptysis * 2.8241680746676243
    a += new_indigestion * 0.2689673675929089
    a += new_necklump * 1.1065323833644807
    a += new_nightsweats * 0.7890696583845964
    a += new_vte * 0.7991150296038755
    a += new_weightloss * 1.3738119234931856
    a += s1_cough * 0.5154179003437486
    return a + -8.716691809801928

def other_cancer_male_score(
    age: int,
    b_copd: int,
    b_type2: int,
    bmi: float,
    c_hb: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_haematuria: int,
    new_haemoptysis: int,
    new_indigestion: int,
    new_necklump: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_constipation: int,
    smoke_cat: int,
) -> float:
    """Other Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620

    Ismoke = [
        0.0,
        0.1306282330648658,
        0.41568246125931085,
        0.40341603935413767,
        0.529038332306518,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 4.115641517087567
    a += age_2 * -1.2786588534988286
    a += bmi_1 * 2.406769125753325
    a += bmi_2 * 0.2566799616335219
    a += b_copd * 0.2364397443316423
    a += b_type2 * 0.23902124891032553
    a += c_hb * 0.9765525865177193
    a += new_abdodist * 0.7203822227648433
    a += new_abdopain * 0.8372159579979499
    a += new_appetiteloss * 1.16476106594546
    a += new_dysphagia * 1.0747326525064285
    a += new_gibleed * 0.4468867932306167
    a += new_haematuria * 0.5276884520139836
    a += new_haemoptysis * 0.6465976131208517
    a += new_indigestion * 0.3156125379576864
    a += new_necklump * 2.947244878727457
    a += new_vte * 1.0954486585194212
    a += new_weightloss * 1.0550815022699203
    a += s1_bowelchange * 0.5059485944682163
    a += s1_constipation * 0.6035170412091727
    return a + -6.713287568285854

def pancreatic_cancer_male_score(
    age: int,
    b_chronicpan: int,
    b_type2: int,
    bmi: float,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_indigestion: int,
    new_vte: int,
    new_weightloss: int,
    s1_constipation: int,
    smoke_cat: int,
    town: float,
) -> float:
    """Pancreatic Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620
    town -= -0.264977723360062

    Ismoke = [
        0.0,
        0.27832981720899735,
        0.3079418928917603,
        0.5647359394991128,
        0.7765125427126867,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 8.02757787091059
    a += age_2 * -2.60824291309828
    a += bmi_1 * 1.781957499473682
    a += bmi_2 * -0.024960006489569975
    a += town * -0.03522881406170505
    a += b_chronicpan * 0.9913246347991823
    a += b_type2 * 0.7396905098202541
    a += new_abdopain * 2.150698401172158
    a += new_appetiteloss * 1.427232600996066
    a += new_dysphagia * 0.9168689207526066
    a += new_gibleed * 0.988106103308115
    a += new_indigestion * 1.2837402377092237
    a += new_vte * 1.174180534610472
    a += new_weightloss * 2.0466064239967046
    a += s1_constipation * 0.6240548033048214
    return a + -9.227572951200996

def prostate_cancer_male_score(
    age: int,
    bmi: float,
    fh_prostatecancer: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_haematuria: int,
    new_rectalbleed: int,
    new_testespain: int,
    new_testicularlump: int,
    new_vte: int,
    new_weightloss: int,
    s1_impotence: int,
    s1_nocturia: int,
    s1_urinaryfreq: int,
    s1_urinaryretention: int,
    town: float,
) -> float:
    """Prostate Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620
    town -= -0.264977723360062

    a = 0.0
    a += age_1 * 14.839101042656692
    a += age_2 * -4.805134105440884
    a += bmi_1 * -2.8369035324107057
    a += bmi_2 * -0.36349842659000514
    a += town * -0.021427865307187672
    a += fh_prostatecancer * 1.2892957682128878
    a += new_abdopain * 0.4445588372860774
    a += new_appetiteloss * 0.3425581971534915
    a += new_haematuria * 1.4890866073593347
    a += new_rectalbleed * 0.34786129520339637
    a += new_testespain * 0.6387609350076408
    a += new_testicularlump * 0.6338177436853567
    a += new_vte * 0.5758190804196262
    a += new_weightloss * 0.7528736226665873
    a += s1_impotence * 0.36921800415342415
    a += s1_nocturia * 1.0381560026453696
    a += s1_urinaryfreq * 0.7036410253080365
    a += s1_urinaryretention * 0.8525703399435587
    return a + -7.88710126972987

def renal_tract_cancer_male_score(
    age: int,
    bmi: float,
    new_abdopain: int,
    new_haematuria: int,
    new_nightsweats: int,
    new_weightloss: int,
    smoke_cat: int,
) -> float:
    """Renal Tract Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620

    Ismoke = [
        0.0,
        0.4183007995792849,
        0.6335162368278743,
        0.7847230879322206,
        0.9631091411295212,
    ]

    a = 0.0
    a += Ismoke[smoke_cat]
    a += age_1 * 6.211380346111106
    a += age_2 * -1.983566150695387
    a += bmi_1 * -1.5995682550089132
    a += bmi_2 * -0.07776968369307531
    a += new_abdopain * 0.6089465678909585
    a += new_haematuria * 4.159645338955679
    a += new_nightsweats * 1.0520790556587876
    a += new_weightloss * 0.6824635274408537
    return a + -8.300655539894251

def testicular_cancer_male_score(
    age: int, bmi: float, new_testespain: int, new_testicularlump: int, new_vte: int
) -> float:
    """Testicular Cancer log-hazard score for males."""
    dage = age / 10.0
    age_1 = dage
    age_2 = dage * math.log(dage)
    dbmi = bmi / 10.0
    bmi_1 = math.pow(dbmi, -2)
    bmi_2 = dbmi

    age_1 -= 4.800777912139893
    age_2 -= 7.531354427337647
    bmi_1 -= 0.146067067980766
    bmi_2 -= 2.616518735885620

    a = 0.0
    a += age_1 * 3.985418448247634
    a += age_2 * -1.7426970576325218
    a += bmi_1 * 2.016079679827681
    a += bmi_2 * -0.042734043745477374
    a += new_testespain * 2.7411880902787775
    a += new_testicularlump * 5.220088614932327
    a += new_vte * 2.2416746922896493
    return a + -8.75922098878959

def compute_female_probabilities(
    age: int,
    alcohol_cat4: int,
    b_chronicpan: int,
    b_copd: int,
    b_endometrial: int,
    b_type2: int,
    bmi: float,
    c_hb: int,
    fh_breastcancer: int,
    fh_gicancer: int,
    fh_ovariancancer: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_breastlump: int,
    new_breastpain: int,
    new_breastskin: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_haematuria: int,
    new_haemoptysis: int,
    new_heartburn: int,
    new_imb: int,
    new_indigestion: int,
    new_necklump: int,
    new_nightsweats: int,
    new_pmb: int,
    new_postcoital: int,
    new_rectalbleed: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_bruising: int,
    s1_constipation: int,
    s1_cough: int,
    smoke_cat: int,
    town: float,
) -> dict[str, float]:
    """Compute all female cancer probabilities matching C binary output.

    Args:
        age: Age in years.
        alcohol_cat4: Alcohol category (0-3).
        b_chronicpan: Chronic pancreatitis flag.
        b_copd: COPD flag.
        b_endometrial: Endometrial polyps flag.
        b_type2: Type 2 diabetes flag.
        bmi: Body mass index.
        c_hb: Anaemia flag.
        fh_breastcancer: Breast cancer family history flag.
        fh_gicancer: GI cancer family history flag.
        fh_ovariancancer: Ovarian cancer family history flag.
        new_abdodist: Abdominal distension symptom.
        new_abdopain: Abdominal pain symptom.
        new_appetiteloss: Appetite loss symptom.
        new_breastlump: Breast lump symptom.
        new_breastpain: Breast pain symptom.
        new_breastskin: Breast skin changes symptom.
        new_dysphagia: Dysphagia symptom.
        new_gibleed: GI bleeding symptom.
        new_haematuria: Haematuria symptom.
        new_haemoptysis: Haemoptysis symptom.
        new_heartburn: Heartburn symptom.
        new_imb: Intermenstrual bleeding symptom.
        new_indigestion: Indigestion symptom.
        new_necklump: Neck lump symptom.
        new_nightsweats: Night sweats symptom.
        new_pmb: Postmenopausal bleeding symptom.
        new_postcoital: Postcoital bleeding symptom.
        new_rectalbleed: Rectal bleeding symptom.
        new_vte: Venous thromboembolism symptom.
        new_weightloss: Weight loss symptom.
        s1_bowelchange: Bowel habit change.
        s1_bruising: Easy bruising.
        s1_constipation: Constipation.
        s1_cough: Persistent cough.
        smoke_cat: Smoking category (0-4).
        town: Townsend deprivation index.

    Returns:
        Dictionary mapping cancer sites to percentage probability (0-100).
        The implicit baseline remains in the denominator and is not exposed.
    """
    # Compute all log-hazard scores
    scores = {
        "blood_cancer": blood_cancer_female_score(
            age,
            bmi,
            c_hb,
            new_abdopain,
            new_haematuria,
            new_necklump,
            new_nightsweats,
            new_pmb,
            new_vte,
            new_weightloss,
            s1_bowelchange,
            s1_bruising,
        ),
        "breast_cancer": breast_cancer_female_score(
            age,
            alcohol_cat4,
            bmi,
            fh_breastcancer,
            new_breastlump,
            new_breastpain,
            new_breastskin,
            new_pmb,
            new_vte,
            town,
        ),
        "cervical_cancer": cervical_cancer_female_score(
            age,
            bmi,
            c_hb,
            new_abdopain,
            new_haematuria,
            new_imb,
            new_pmb,
            new_postcoital,
            new_vte,
            smoke_cat,
            town,
        ),
        "colorectal_cancer": colorectal_cancer_female_score(
            age,
            alcohol_cat4,
            bmi,
            c_hb,
            fh_gicancer,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_rectalbleed,
            new_vte,
            new_weightloss,
            s1_bowelchange,
            s1_constipation,
        ),
        "gastro_oesophageal_cancer": gastro_oesophageal_cancer_female_score(
            age,
            bmi,
            c_hb,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_gibleed,
            new_heartburn,
            new_indigestion,
            new_vte,
            new_weightloss,
            smoke_cat,
        ),
        "lung_cancer": lung_cancer_female_score(
            age,
            b_copd,
            bmi,
            c_hb,
            new_appetiteloss,
            new_dysphagia,
            new_haemoptysis,
            new_indigestion,
            new_necklump,
            new_vte,
            new_weightloss,
            s1_cough,
            smoke_cat,
            town,
        ),
        "other_cancer": other_cancer_female_score(
            age,
            alcohol_cat4,
            b_copd,
            bmi,
            c_hb,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_breastlump,
            new_dysphagia,
            new_gibleed,
            new_haematuria,
            new_indigestion,
            new_necklump,
            new_pmb,
            new_vte,
            new_weightloss,
            s1_constipation,
            smoke_cat,
        ),
        "ovarian_cancer": ovarian_cancer_female_score(
            age,
            bmi,
            c_hb,
            fh_ovariancancer,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_haematuria,
            new_indigestion,
            new_pmb,
            new_vte,
            new_weightloss,
            s1_bowelchange,
        ),
        "pancreatic_cancer": pancreatic_cancer_female_score(
            age,
            b_chronicpan,
            b_type2,
            bmi,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_gibleed,
            new_indigestion,
            new_vte,
            new_weightloss,
            s1_bowelchange,
            smoke_cat,
        ),
        "renal_tract_cancer": renal_tract_cancer_female_score(
            age,
            bmi,
            c_hb,
            new_abdopain,
            new_appetiteloss,
            new_haematuria,
            new_indigestion,
            new_pmb,
            new_weightloss,
            smoke_cat,
        ),
        "uterine_cancer": uterine_cancer_female_score(
            age,
            b_endometrial,
            b_type2,
            bmi,
            new_abdopain,
            new_haematuria,
            new_imb,
            new_pmb,
            new_vte,
        ),
    }

    # Convert log-hazards to hazards
    hazards = {name: math.exp(score) for name, score in scores.items()}

    # Normalize to percentages (sum of all hazards + 1 for "no cancer")
    total = 1.0 + sum(hazards.values())
    probabilities = {name: (hazard * 100.0 / total) for name, hazard in hazards.items()}

    return probabilities

def compute_male_probabilities(
    age: int,
    alcohol_cat4: int,
    b_chronicpan: int,
    b_copd: int,
    b_type2: int,
    bmi: float,
    c_hb: int,
    fh_gicancer: int,
    fh_prostatecancer: int,
    new_abdodist: int,
    new_abdopain: int,
    new_appetiteloss: int,
    new_dysphagia: int,
    new_gibleed: int,
    new_haematuria: int,
    new_haemoptysis: int,
    new_heartburn: int,
    new_indigestion: int,
    new_necklump: int,
    new_nightsweats: int,
    new_rectalbleed: int,
    new_testespain: int,
    new_testicularlump: int,
    new_vte: int,
    new_weightloss: int,
    s1_bowelchange: int,
    s1_constipation: int,
    s1_cough: int,
    s1_impotence: int,
    s1_nocturia: int,
    s1_urinaryfreq: int,
    s1_urinaryretention: int,
    smoke_cat: int,
    town: float,
) -> dict[str, float]:
    """Compute all male cancer probabilities matching C binary output.

    Args:
        age: Age in years.
        alcohol_cat4: Alcohol category (0-3).
        b_chronicpan: Chronic pancreatitis flag.
        b_copd: COPD flag.
        b_type2: Type 2 diabetes flag.
        bmi: Body mass index.
        c_hb: Anaemia flag.
        fh_gicancer: GI cancer family history flag.
        fh_prostatecancer: Prostate cancer family history flag.
        new_abdodist: Abdominal distension symptom.
        new_abdopain: Abdominal pain symptom.
        new_appetiteloss: Appetite loss symptom.
        new_dysphagia: Dysphagia symptom.
        new_gibleed: GI bleeding symptom.
        new_haematuria: Haematuria symptom.
        new_haemoptysis: Haemoptysis symptom.
        new_heartburn: Heartburn symptom.
        new_indigestion: Indigestion symptom.
        new_necklump: Neck lump symptom.
        new_nightsweats: Night sweats symptom.
        new_rectalbleed: Rectal bleeding symptom.
        new_testespain: Testicular pain symptom.
        new_testicularlump: Testicular lump symptom.
        new_vte: Venous thromboembolism symptom.
        new_weightloss: Weight loss symptom.
        s1_bowelchange: Bowel habit change.
        s1_constipation: Constipation.
        s1_cough: Persistent cough.
        s1_impotence: Erectile dysfunction.
        s1_nocturia: Nocturia.
        s1_urinaryfreq: Urinary frequency.
        s1_urinaryretention: Urinary retention.
        smoke_cat: Smoking category (0-4).
        town: Townsend deprivation index.

    Returns:
        Dictionary mapping cancer sites to percentage probability (0-100).
        The implicit baseline remains in the denominator and is not exposed.
    """
    # Compute all log-hazard scores
    scores = {
        "blood_cancer": blood_cancer_male_score(
            age,
            bmi,
            c_hb,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_haematuria,
            new_haemoptysis,
            new_indigestion,
            new_necklump,
            new_nightsweats,
            new_testicularlump,
            new_vte,
            new_weightloss,
            town,
        ),
        "colorectal_cancer": colorectal_cancer_male_score(
            age,
            alcohol_cat4,
            bmi,
            c_hb,
            fh_gicancer,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_rectalbleed,
            new_weightloss,
            s1_bowelchange,
            s1_constipation,
        ),
        "gastro_oesophageal_cancer": gastro_oesophageal_cancer_male_score(
            age,
            bmi,
            c_hb,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_gibleed,
            new_heartburn,
            new_indigestion,
            new_necklump,
            new_weightloss,
            smoke_cat,
        ),
        "lung_cancer": lung_cancer_male_score(
            age,
            b_copd,
            bmi,
            c_hb,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_haemoptysis,
            new_indigestion,
            new_necklump,
            new_nightsweats,
            new_vte,
            new_weightloss,
            s1_cough,
            smoke_cat,
            town,
        ),
        "other_cancer": other_cancer_male_score(
            age,
            b_copd,
            b_type2,
            bmi,
            c_hb,
            new_abdodist,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_gibleed,
            new_haematuria,
            new_haemoptysis,
            new_indigestion,
            new_necklump,
            new_vte,
            new_weightloss,
            s1_bowelchange,
            s1_constipation,
            smoke_cat,
        ),
        "pancreatic_cancer": pancreatic_cancer_male_score(
            age,
            b_chronicpan,
            b_type2,
            bmi,
            new_abdopain,
            new_appetiteloss,
            new_dysphagia,
            new_gibleed,
            new_indigestion,
            new_vte,
            new_weightloss,
            s1_constipation,
            smoke_cat,
            town,
        ),
        "prostate_cancer": prostate_cancer_male_score(
            age,
            bmi,
            fh_prostatecancer,
            new_abdopain,
            new_appetiteloss,
            new_haematuria,
            new_rectalbleed,
            new_testespain,
            new_testicularlump,
            new_vte,
            new_weightloss,
            s1_impotence,
            s1_nocturia,
            s1_urinaryfreq,
            s1_urinaryretention,
            town,
        ),
        "renal_tract_cancer": renal_tract_cancer_male_score(
            age,
            bmi,
            new_abdopain,
            new_haematuria,
            new_nightsweats,
            new_weightloss,
            smoke_cat,
        ),
        "testicular_cancer": testicular_cancer_male_score(
            age, bmi, new_testespain, new_testicularlump, new_vte
        ),
    }

    # Convert log-hazards to hazards
    hazards = {name: math.exp(score) for name, score in scores.items()}

    # Normalize to percentages (sum of all hazards + 1 for "no cancer")
    total = 1.0 + sum(hazards.values())
    probabilities = {name: (hazard * 100.0 / total) for name, hazard in hazards.items()}

    return probabilities

def _input_problems(inputs: QCancer2013Input) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Return (status, missing, invalid) without converting unknowns to negatives."""
    missing: list[str] = []
    invalid: list[str] = []
    if inputs.sex is None:
        missing.append("sex")
    elif inputs.sex not in ("female", "male"):
        return "unsupported_input", (), ("sex: the published equation supports only female or male inputs",)

    numeric = {
        "age_years": inputs.age_years,
        "bmi": inputs.bmi,
        "town": inputs.town,
        "alcohol_cat4": inputs.alcohol_cat4,
        "smoke_cat": inputs.smoke_cat,
    }
    missing.extend(name for name, value in numeric.items() if value is None)
    if inputs.age_years is not None and not 25 <= inputs.age_years <= 89:
        invalid.append("age_years: QCancer-2013 accepts ages 25 through 89")
    if inputs.bmi is not None and not 20 <= inputs.bmi <= 40:
        invalid.append("bmi: QCancer-2013 accepts BMI values from 20 through 40")
    if inputs.town is not None and not -7 <= inputs.town <= 11:
        invalid.append("town: QCancer-2013 accepts Townsend scores from -7 through 11")
    if inputs.alcohol_cat4 is not None and not 0 <= inputs.alcohol_cat4 <= 3:
        invalid.append("alcohol_cat4: expected a QCancer category from 0 through 3")
    if inputs.smoke_cat is not None and not 0 <= inputs.smoke_cat <= 4:
        invalid.append("smoke_cat: expected a QCancer category from 0 through 4")

    if inputs.sex in ("female", "male"):
        required = FEMALE_BINARY_INPUTS if inputs.sex == "female" else MALE_BINARY_INPUTS
        extra = sorted(set(inputs.binary_factors) - required)
        if extra:
            invalid.append("binary_factors: not used by the selected sex-specific equation: " + ", ".join(extra))
        for name in sorted(required):
            if inputs.binary_factors.get(name) is None:
                missing.append(f"binary_factors.{name}")
    return ("invalid_input" if invalid else "insufficient_data" if missing else "calculated",
            tuple(missing), tuple(invalid))


def _calculate_site_risks(inputs: QCancer2013Input) -> dict[str, float]:
    factors = {name: int(value) for name, value in inputs.binary_factors.items() if value is not None}
    common = {
        "age": inputs.age_years,
        "alcohol_cat4": inputs.alcohol_cat4,
        "bmi": inputs.bmi,
        "smoke_cat": inputs.smoke_cat,
        "town": inputs.town,
        **factors,
    }
    raw = (compute_female_probabilities(**common) if inputs.sex == "female"
           else compute_male_probabilities(**common))
    return {name: round(float(value), 6) for name, value in raw.items()}


def qcancer_prediction(inputs: QCancer2013Input) -> ModelPrediction:
    """Build the ModelPrediction consumed by AnalysisResult.predictions."""
    status, missing, invalid = _input_problems(inputs)
    if status == "calculated":
        site_risks = _calculate_site_risks(inputs)
        colorectal = site_risks["colorectal_cancer"]
        any_cancer = round(sum(site_risks.values()), 6)
        output = QCancer2013Output(
            status="calculated",
            any_cancer_risk_percent=any_cancer,
            colorectal_cancer_risk_percent=colorectal,
            cancer_site_risks_percent=site_risks,
        )
        uncertainty = (
            "UK-developed QCancer-2013 estimate; not calibrated or clinically validated for Finland. "
            "Do not use as a diagnosis or autonomous referral decision."
        )
    else:
        output = QCancer2013Output(status=status, missing_inputs=missing, invalid_inputs=invalid)
        reasons = list(invalid or missing)
        uncertainty = "QCancer-2013 did not calculate a risk because required inputs are " + (
            "outside the model's supported range: " if invalid else "missing: "
        ) + ", ".join(reasons)

    return ModelPrediction(
        patient_id=inputs.patient_id,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        as_of=inputs.as_of,
        prediction_type="current_undiagnosed_cancer_risk",
        value=output.model_dump(mode="json"),
        evidence_observation_ids=list(inputs.evidence_observation_ids),
        uncertainty=uncertainty,
    )
