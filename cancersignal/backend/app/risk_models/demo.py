"""Print both Junction model outputs for one fully synthetic example."""

from decimal import Decimal
import json
from uuid import UUID

from app.db.seed_rules import colorectal_rule_rows
from app.models.enums import FindingStatus
from app.reasoning import vocabulary as v
from app.reasoning.trigger_engine import evaluate_triggers
from app.risk_models.qcancer_2013 import (
    MALE_BINARY_INPUTS,
    QCancer2013Input,
    qcancer_prediction,
)
from app.contracts.evidence import EvidenceReference
from app.schemas.analysis import StructuredFinding
from app.schemas.records import TriggerRuleRead


PATIENT_ID = UUID("11111111-1111-4111-8111-111111111111")
NOTE_ID = UUID("22222222-2222-4222-8222-222222222222")
FIT_ID = UUID("33333333-3333-4333-8333-333333333333")
AS_OF = "2026-11-14T09:00:00+00:00"


def run_demo() -> dict:
    """Run the deterministic rules and QCancer independently on synthetic facts."""
    factors = {name: False for name in MALE_BINARY_INPUTS}
    factors.update({
        "c_hb": True,
        "new_abdopain": True,
        "new_rectalbleed": True,
        "new_weightloss": True,
    })
    q_input = QCancer2013Input(
        patient_id=PATIENT_ID,
        as_of=AS_OF,
        sex="male",
        age_years=67,
        bmi=25.7,
        # Synthetic UK Townsend score. This is not a Finnish deprivation measure.
        town=-0.3,
        alcohol_cat4=1,
        smoke_cat=0,
        binary_factors=factors,
        evidence_observation_ids=(NOTE_ID, FIT_ID),
    )

    findings = [
        StructuredFinding(
            finding_type=v.RECTAL_BLEEDING,
            status=FindingStatus.CURRENT,
            description="Synthetic demo: current rectal bleeding.",
            evidence=[EvidenceReference(observation_id=NOTE_ID,
                                        source_excerpt="Synthetic demo: current rectal bleeding.")],
        ),
        StructuredFinding(
            finding_type=v.ABDOMINAL_PAIN,
            status=FindingStatus.CURRENT,
            description="Synthetic demo: current abdominal pain.",
            evidence=[EvidenceReference(observation_id=NOTE_ID,
                                        source_excerpt="Synthetic demo: current abdominal pain.")],
        ),
        StructuredFinding(
            finding_type=v.FIT_RESULT,
            status=FindingStatus.CURRENT,
            description="Synthetic demo: positive FIT result.",
            numeric_value=Decimal("18"),
            unit=v.FIT_UNIT,
            evidence=[EvidenceReference(observation_id=FIT_ID)],
        ),
    ]

    rule_rows = colorectal_rule_rows()
    rule_records = [TriggerRuleRead.model_validate(row) for row in rule_rows]
    evaluations = evaluate_triggers(
        PATIENT_ID,
        findings,
        rule_records,
        patient_facts={v.AGE_YEARS: 67},
    )
    rows_by_id = {str(row["id"]): row for row in rule_rows}
    matched_rules = []
    for evaluation in evaluations:
        if not evaluation.triggered:
            continue
        row = rows_by_id[str(evaluation.trigger_rule_id)]
        matched_rules.append({
            "rule_id": row["name"].split(":", 1)[0],
            "priority": evaluation.priority,
            "recommendation": row["recommended_action"],
            "evidence_observation_ids": [str(value) for value in evaluation.evidence_observation_ids],
        })

    prediction = qcancer_prediction(q_input)
    return {
        "synthetic_data_only": True,
        "rule_table": {
            "result": "physician_review_suggested" if matched_rules else "no_signals_identified",
            "matched_rules": matched_rules,
            "interpretation": "Deterministic evidence-table output; not a diagnosis or referral decision.",
        },
        "qcancer": prediction.model_dump(mode="json"),
        "combination_note": "The two outputs are separate; a later explanation component may summarize them together.",
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, ensure_ascii=False))
