"""Presentation of the published QCancer payload only; no calculator imports."""
from decimal import Decimal
from typing import Literal

from pydantic import Field, StrictInt, ValidationError

from app.contracts.common import Contract
from app.explanation.schemas import ExplanationStatement, Limitation, Quantity

QCANCER_ID = ("QCancer-2013", "QCancer-2013-open-source", "current_undiagnosed_cancer_risk")


class QCancerDisplayPayload(Contract):
    # Other source fields (site details, source notice, population) remain in the
    # original prediction. They are not interpreted or copied into LLM prose.
    model_config = {"extra": "ignore"}
    status: Literal["calculated", "insufficient_data", "invalid_input", "unsupported_input"]
    horizon_years: StrictInt | None = Field(default=None, ge=1, le=100)
    any_cancer_risk_percent: Decimal | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    colorectal_cancer_risk_percent: Decimal | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    missing_inputs: tuple[str, ...] = ()
    invalid_inputs: tuple[str, ...] = ()


def qcancer_statement(prediction, index):
    if (prediction.model_name, prediction.model_version, prediction.prediction_type) != QCANCER_ID:
        return None
    key = f"prediction:{index}"
    ids = tuple(prediction.evidence_observation_ids)
    notice = prediction.value.get("source_notice") if isinstance(prediction.value, dict) else None
    notice = notice if isinstance(notice, str) and notice.strip() else None
    limits = [Limitation(code="qcancer_finland_limitation", related_keys=(key,), observation_ids=ids,
        text_en="QCancer-2013 uses UK data. This prototype is not calibrated or clinically validated for Finland. Review the model placeholder inputs and original source notice.")]
    if notice is None:
        limits.append(Limitation(code="qcancer_source_notice_missing", text_en="The original QCancer source notice is missing; it is not replaced with invented text.", related_keys=(key,)))
    quantities = ()
    try:
        payload = QCancerDisplayPayload.model_validate(prediction.value)
        if payload.status == "calculated":
            if (not ids or payload.horizon_years is None or payload.any_cancer_risk_percent is None
                    or payload.colorectal_cancer_risk_percent is None or payload.missing_inputs or payload.invalid_inputs):
                raise ValueError("Calculated prediction lacks complete source-linked display fields")
            if any(abs(number.adjusted()) > 40 or len(str(number)) > 80 for number in
                   (payload.colorectal_cancer_risk_percent, payload.any_cancer_risk_percent)):
                raise ValueError("Unsupported numeric display width")
            quantities = (
                Quantity(slot="colorectal_cancer_risk_percent", value=payload.colorectal_cancer_risk_percent, unit="%"),
                Quantity(slot="any_cancer_risk_percent", value=payload.any_cancer_risk_percent, unit="%"),
                Quantity(slot="horizon_years", value=Decimal(payload.horizon_years), unit="years"),
            )
            # These source fields ALREADY contain percentages. Do not multiply,
            # round, sum cancer-site values, classify risk or change rule alerts.
            crc, overall, horizon = (format(row.value, "f") for row in quantities)
            text = (f"QCancer-2013 colorectal cancer model estimate: {crc} %. "
                    f"Combined estimate for cancers covered by the model: {overall} %. Model prediction horizon: {horizon} years. "
                    "This is a model prediction, not an established disease.")
        else:
            reason = {"insufficient_data": "required inputs are missing",
                      "invalid_input": "the source model reports invalid inputs",
                      "unsupported_input": "the inputs are outside the supported model scope"}[payload.status]
            text = f"QCancer-2013 estimate not calculated: {reason}. Missing information is not interpreted as negative findings."
            limits.append(Limitation(code="qcancer_estimate_unavailable", text_en="QCancer has no valid calculated estimate. Review the original missing or invalid inputs.", related_keys=(key,), observation_ids=ids))
    except (ValidationError, ValueError, TypeError):
        text = "QCancer numeric values are omitted because their structure, units or source references are incomplete or inconsistent."
        limits.append(Limitation(code="qcancer_invalid_display_payload", text_en=text, related_keys=(key,), observation_ids=ids))
    return ExplanationStatement(key=key, kind="prediction", text_en=text, observation_ids=ids,
                                quantities=quantities, prediction_index=index, source_notice=notice), tuple(limits)
