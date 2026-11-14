# Colorectal rulebook (demonstration)

> **Demonstration, not clinically validated for Finland.** These rules translate
> NICE guidance into deterministic demo rules for the CancerSignal prototype. They
> are not Finnish Current Care Guidelines (Käypä hoito), and they are not a
> diagnostic tool.

The full human-readable rulebook is the shared doc "CancerSignal – Suolistosyövän
sääntökirja (NICE)". This page is the version implemented in the backend.

## How the rules run

- **The rules decide; the LLM does not.** Rules are deterministic Python (`app/reasoning/trigger_engine.py`). The LLM only extracts facts into the vocabulary below and writes explanations.
- **Where the rules live:** seeded as enabled `trigger_rules` by `python -m app.db.seed` (`seed_rules()` in `app/db/seed_rules.py`, kept out of `seed.py` so RAG stays independent of `app.reasoning`), version `nice-2023-demo-1`, with stable IDs.
- **Statuses:** a finding leaf matches only `current` findings. `negated`, `resolved` and `uncertain` findings never trigger. Whether an anaemia is "unexplained" or a FIT is "not acted on" is decided upstream by extraction and reconciliation (an investigated anaemia is `resolved`), not by the rules.
- **Age** is a patient-level condition (`{"kind": "patient", "field": "age_years", ...}`), not a finding. It is computed in whole years from `birth_date` at the note time (time *t*). If age is missing, the condition is false.
- **Priority** comes from the rule: `urgent` or `review`. The overall alert level is the highest priority among the triggered rules.
- **Evidence:** every triggered rule cites the source observations of its findings. Age adds no evidence.

## Finding vocabulary

Defined once in `app/reasoning/vocabulary.py`.

| finding_type | Meaning | Comes from |
| --- | --- | --- |
| `rectal_bleeding` | Rectal bleeding / blood in stool | Note text (extraction) |
| `change_in_bowel_habit` | Change in bowel habit | Note text |
| `abdominal_pain` | Abdominal pain | Note text |
| `weight_loss` | Unintentional weight loss | Note text |
| `abdominal_mass` | Abdominal mass | Note text (usually physician) |
| `rectal_mass` | Rectal mass | Note text (usually physician) |
| `anaemia` | Hb below the reference range | Lab, computed in Python |
| `iron_deficiency_anaemia` | Anaemia + ferritin below the reference range | Lab, computed in Python |
| `fit_result` | Faecal immunochemical test, numeric, unit `ug/g` | Lab |

### Lab-derived findings

These are computed in `app/reasoning/derived_findings.py` from the **latest** value
of each lab before time *t*.

| Analyte | Mapped codes (case-insensitive) | Demo rule |
| --- | --- | --- |
| Haemoglobin | `SYNTHETIC-HB`, `B-Hb`, `Hb`, `HGB` (unit g/l) | Below 117 g/l (female) or 134 g/l (male) → `anaemia` |
| Ferritin | `SYNTHETIC-FERRITIN`, `P-Ferritin`, `S-Ferritin`, `Ferritin` (unit ug/l) | Anaemia + ferritin < 15 ug/l → `iron_deficiency_anaemia` |
| FIT | `SYNTHETIC-FIT`, `F-Hb-FIT`, `FIT` (unit ug/g) | Always → `fit_result`, with the source value and unit unchanged |

The reference ranges are **demo constants, not clinically validated** (Hb female
117–155 g/l, male 134–167 g/l; ferritin low < 15 ug/l). They apply until labs store
their own ranges.

Other things to know:
- The seed data only contains `SYNTHETIC-HB`.
- Lab codes that are not mapped are listed in the analysis `missing_information`.
- If the patient's sex is not female or male, anaemia is not assessed.

## Rules

| ID | Expression | Priority | Recommended action | lahde / lahde_kohta |
| --- | --- | --- | --- | --- |
| SUO-01 | `abdominal_mass` | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-02 | `change_in_bowel_habit` | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-03 | `iron_deficiency_anaemia` | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-04 | age ≥ 40 AND `weight_loss` AND `abdominal_pain` | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-05 | age < 50 AND `rectal_bleeding` AND (`abdominal_pain` OR `weight_loss`) | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-06 | age ≥ 50 AND (`rectal_bleeding` OR `abdominal_pain` OR `weight_loss`) | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-07 | age ≥ 60 AND `anaemia` | review | Physician review: consider FIT | NICE DG56/HTG690 / 1.1 |
| SUO-08 | `fit_result` ≥ 10 ug/g | urgent | Urgent physician review: suspected cancer pathway referral | NICE DG56/HTG690 / 1.2 |
| SUO-09 | `rectal_mass` | urgent | Urgent physician review: consider suspected cancer referral without FIT | NICE NG12 / 1.3 |
| SUO-10 | `fit_result` < 10 ug/g AND (`rectal_bleeding` OR `change_in_bowel_habit` OR `abdominal_pain` OR `weight_loss`) | review | Physician review: safety netting, consider further investigation | NICE DG56/HTG690 / 1.3–1.4 |

## Sources

- NICE NG12, *Suspected cancer: recognition and referral*, recommendations organised by site of cancer (lower gastrointestinal tract cancers, §1.3): https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer
- NICE HTG690 (formerly DG56), *Quantitative faecal immunochemical testing to guide colorectal cancer pathway referral in primary care*: https://www.nice.org.uk/guidance/HTG690/chapter/recommendations

## Not done yet

- **Free-text extraction:** LLM extraction of the note-text findings (`rectal_bleeding`, `change_in_bowel_habit`, `abdominal_pain`, `weight_loss`, `abdominal_mass`, `rectal_mass`). Without it, rules that need these can only match coded records.
- **Reference ranges:** real ranges stored with each lab result, replacing the demo constants.
- **Reconciliation:** marking investigated anaemia or acted-on FIT as `resolved`.
- **Frontend:** using `priority` to show the red `urgent` alert.
