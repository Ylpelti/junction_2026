"""Build QCancer inputs from validated extraction output and source records."""
from decimal import Decimal
from uuid import UUID

from app.contracts.qcancer import QCancerPredictors
from app.models.enums import ObservationType
from app.reasoning.derived_findings import (
    HB_CODES,
    HB_LOWER_LIMIT_G_PER_L,
    latest,
    normalise_unit,
)
from app.risk_models.qcancer_2013 import (
    FEMALE_BINARY_INPUTS,
    MALE_BINARY_INPUTS,
    QCancer2013Input,
)
from app.schemas.records import ObservationRead


DEMO_TOWNSEND = 0.0


def _smoking_category(predictors: QCancerPredictors) -> int | None:
    smoking = predictors.smoking
    if smoking.status == "never":
        return 0
    if smoking.status == "former":
        return 1
    if smoking.status != "current" or smoking.cigarettes_per_day.value is None:
        return None
    cigarettes = smoking.cigarettes_per_day.value
    if cigarettes <= 0:
        return None
    if cigarettes < 10:
        return 2
    if cigarettes < 20:
        return 3
    return 4


def _alcohol_category(predictors: QCancerPredictors) -> int | None:
    units = predictors.alcohol_uk_units_per_day.value
    if units is None or units < 0:
        return None
    if units == 0:
        return 0
    if units < 1:
        return 1
    if units < 3:
        return 2
    return 3


def _bmi(predictors: QCancerPredictors) -> tuple[float | None, list[UUID]]:
    if predictors.bmi.value is not None:
        return float(predictors.bmi.value), [ref.observation_id for ref in predictors.bmi.evidence]
    height = predictors.height_cm.value
    weight = predictors.weight_kg.value
    if height is None or weight is None or height <= 0 or weight <= 0:
        return None, []
    height_m = height / Decimal(100)
    value = weight / (height_m * height_m)
    ids = [ref.observation_id for ref in (*predictors.height_cm.evidence, *predictors.weight_kg.evidence)]
    return float(value), ids


def _haemoglobin_factor(observations: list[ObservationRead], sex: str | None) -> tuple[bool | None, UUID | None]:
    """Derive c_hb only from the latest supported synthetic Hb measurement."""
    hb = latest((row for row in observations if row.observation_type == ObservationType.LABORATORY), HB_CODES)
    sex_key = str(sex) if sex is not None else ""
    lower = HB_LOWER_LIMIT_G_PER_L.get(sex_key)
    if hb is None or normalise_unit(hb.unit) != "g/l" or lower is None:
        return None, None
    return hb.numeric_value < lower, hb.id


def build_qcancer_input(*, patient_id: UUID, as_of, sex: str | None, age_years: int | None,
                        predictors: QCancerPredictors | None,
                        observations: list[ObservationRead]) -> QCancer2013Input:
    """Map only source-backed values; unknowns remain absent for strict validation."""
    values = predictors or QCancerPredictors()
    sex_key = str(sex) if sex is not None else None
    selected_factors = FEMALE_BINARY_INPUTS if sex_key == "female" else MALE_BINARY_INPUTS if sex_key == "male" else frozenset()
    binary = {
        str(factor.factor): factor.value
        for factor in values.binary_factors
        if str(factor.factor) in selected_factors and factor.value is not None
    }
    hb_value, hb_id = _haemoglobin_factor(observations, sex_key)
    if hb_value is not None:
        binary["c_hb"] = hb_value

    bmi, bmi_ids = _bmi(values)
    evidence_ids = {ref.observation_id for ref in values.evidence_references()}
    evidence_ids.update(bmi_ids)
    if hb_id is not None:
        evidence_ids.add(hb_id)
    return QCancer2013Input(
        patient_id=patient_id,
        as_of=as_of,
        sex=sex_key,
        age_years=age_years,
        bmi=bmi,
        town=DEMO_TOWNSEND,
        alcohol_cat4=_alcohol_category(values),
        smoke_cat=_smoking_category(values),
        binary_factors=binary,
        evidence_observation_ids=tuple(sorted(evidence_ids, key=str)),
    )
