"""Colorectal demonstration rules (docs/rulebook-colorectal.md).

Kept out of app/db/seed.py on purpose: seed.py is imported by the RAG benchmark
and CLI, and RAG must not import downstream reasoning code (see
tests/rag/test_independence.py). This module depends on app.reasoning.vocabulary.
"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.seed import synthetic_id
from app.models import TriggerRule
from app.reasoning import vocabulary as v

# Demonstration only, not clinically validated for Finland. Kept separate from
# seed() so tests that expect no enabled rules keep their fixture.

RULE_VERSION = "nice-2023-demo-1"
FIT_ACTION = "Physician review: consider FIT"
DG56_11 = ("NICE DG56/HTG690", "1.1")


def finding(finding_type: str, **numeric) -> dict:
    leaf = {"kind": "finding", "finding_type": finding_type, "statuses": ["current"]}
    if numeric:
        leaf["numeric"] = numeric
    return leaf


def age(operator: str, years: int) -> dict:
    return {"kind": "patient", "field": v.AGE_YEARS, "numeric": {"operator": operator, "value": years, "unit": "years"}}


def all_of(*conditions) -> dict:
    return {"kind": "group", "operator": "ALL", "conditions": list(conditions)}


def any_of(*conditions) -> dict:
    return {"kind": "group", "operator": "ANY", "conditions": list(conditions)}


# (id, title, expression, priority, recommended_action, (lahde, lahde_kohta))
COLORECTAL_RULES = [
    ("SUO-01", "Abdominal mass", all_of(finding(v.ABDOMINAL_MASS)), "review", FIT_ACTION, DG56_11),
    ("SUO-02", "Change in bowel habit", all_of(finding(v.CHANGE_IN_BOWEL_HABIT)), "review", FIT_ACTION, DG56_11),
    ("SUO-03", "Iron-deficiency anaemia", all_of(finding(v.IRON_DEFICIENCY_ANAEMIA)), "review", FIT_ACTION, DG56_11),
    ("SUO-04", "Age 40+ with weight loss and abdominal pain",
     all_of(age("gte", 40), finding(v.WEIGHT_LOSS), finding(v.ABDOMINAL_PAIN)), "review", FIT_ACTION, DG56_11),
    ("SUO-05", "Age under 50 with rectal bleeding and abdominal pain or weight loss",
     all_of(age("lt", 50), finding(v.RECTAL_BLEEDING), any_of(finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", FIT_ACTION, DG56_11),
    ("SUO-06", "Age 50+ with rectal bleeding, abdominal pain or weight loss",
     all_of(age("gte", 50), any_of(finding(v.RECTAL_BLEEDING), finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", FIT_ACTION, DG56_11),
    ("SUO-07", "Age 60+ with anaemia", all_of(age("gte", 60), finding(v.ANAEMIA)), "review", FIT_ACTION, DG56_11),
    ("SUO-08", "Positive FIT (10 ug/g or more)",
     all_of(finding(v.FIT_RESULT, operator="gte", value=10, unit=v.FIT_UNIT)), "urgent",
     "Urgent physician review: suspected cancer pathway referral", ("NICE DG56/HTG690", "1.2")),
    ("SUO-09", "Rectal mass", all_of(finding(v.RECTAL_MASS)), "urgent",
     "Urgent physician review: consider suspected cancer referral without FIT", ("NICE NG12", "1.3")),
    ("SUO-10", "Negative FIT with ongoing symptoms",
     all_of(finding(v.FIT_RESULT, operator="lt", value=10, unit=v.FIT_UNIT),
            any_of(finding(v.RECTAL_BLEEDING), finding(v.CHANGE_IN_BOWEL_HABIT),
                   finding(v.ABDOMINAL_PAIN), finding(v.WEIGHT_LOSS))),
     "review", "Physician review: safety netting, consider further investigation", ("NICE DG56/HTG690", "1.3–1.4")),
]


def colorectal_rule_rows() -> list[dict]:
    rows = []
    for rule_id, title, expression, priority, action, (lahde, lahde_kohta) in COLORECTAL_RULES:
        rows.append(dict(
            id=synthetic_id(f"rule/colorectal/{rule_id}"),
            name=f"{rule_id}: {title}",
            description=f"{title}. Demonstration rule based on {lahde} {lahde_kohta}; not clinically validated for Finland.",
            conditions={"demonstration": True, "priority": priority, "lahde": lahde, "lahde_kohta": lahde_kohta,
                        "expression": expression},
            recommended_action=action,
            version=RULE_VERSION,
            enabled=True,
        ))
    return rows


def seed_rules(session: Session) -> dict[str, int]:
    """Insert the enabled colorectal demonstration rules; insert-only and idempotent."""
    rows = colorectal_rule_rows()
    for row in rows:
        session.execute(insert(TriggerRule).values(**row).on_conflict_do_nothing())
    return {TriggerRule.__tablename__: len(rows)}

