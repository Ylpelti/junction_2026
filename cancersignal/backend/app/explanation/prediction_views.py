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
        text_fi="QCancer-2013 perustuu Ison-Britannian aineistoon. Mallia ei ole tässä prototyypissä kalibroitu tai kliinisesti validoitu Suomeen. Tarkista myös lähtömallin paikkamerkkisyötteet ja alkuperäinen vastuunrajaus.")]
    if notice is None:
        limits.append(Limitation(code="qcancer_source_notice_missing", text_fi="Alkuperäinen QCancer-vastuunrajaus puuttuu annetusta tuloksesta; sitä ei korvata keksityllä tekstillä.", related_keys=(key,)))
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
                Quantity(slot="horizon_years", value=Decimal(payload.horizon_years), unit="vuotta"),
            )
            # These source fields ALREADY contain percentages. Do not multiply,
            # round, sum cancer-site values, classify risk or change rule alerts.
            crc, overall, horizon = (format(row.value, "f").replace(".", ",") for row in quantities)
            text = (f"QCancer-2013-mallin ilmoittama paksu- ja peräsuolisyövän malliarvio: {crc} %. "
                    f"Mallin kattamien syöpien yhteisarvio: {overall} %. Mallin ennustejakso: {horizon} vuotta. "
                    "Kyse on malliennusteesta, ei todetusta sairaudesta.")
        else:
            reason = {"insufficient_data": "tarvittavia lähtötietoja puuttuu",
                      "invalid_input": "lähtömalli ilmoittaa virheellisiä syötetietoja",
                      "unsupported_input": "lähtötiedot eivät kuulu mallin tukemaan käyttöalueeseen"}[payload.status]
            text = f"QCancer-2013-malliarviota ei ole laskettu: {reason}. Puuttuvia tietoja ei tulkita kielteisiksi löydöksiksi."
            limits.append(Limitation(code="qcancer_estimate_unavailable", text_fi="QCancer ei ilmoita kelvollista laskettua arviota. Tarkista alkuperäiset puuttuvat tai virheelliset syötteet.", related_keys=(key,), observation_ids=ids))
    except (ValidationError, ValueError, TypeError):
        text = "QCancer-tuloksen numeroarvoja ei esitetä, koska niiden rakenne, yksikkömerkitys tai lähdeviitteet ovat puutteelliset tai ristiriitaiset."
        limits.append(Limitation(code="qcancer_invalid_display_payload", text_fi=text, related_keys=(key,), observation_ids=ids))
    return ExplanationStatement(key=key, kind="prediction", text_fi=text, observation_ids=ids,
                                quantities=quantities, prediction_index=index, source_notice=notice), tuple(limits)
