# Junction's two independent model outputs

Junction has two separate Python outputs. They answer different questions and
should remain separate until a later explanation step presents them together.

## 1. Evidence-table rules

The existing colorectal rule table is seeded in
`backend/app/db/seed_rules.py`; `backend/app/reasoning/trigger_engine.py`
evaluates it against structured findings and age. The rules cover the current
SUO-01…SUO-10 rows, carry their evidence source and section, and return a review
priority plus the source observation IDs. The existing analysis service already
calls this rule engine after extraction.

This output is a rule match, not a probability or diagnosis. For example, a
positive FIT at or above the table's value can produce an urgent physician-review
recommendation. A missing finding does not become evidence of absence.

## 2. QCancer-2013 numerical estimate

`backend/app/risk_models/qcancer_2013.py` implements the published QCancer-2013
multi-cancer equations. It calculates cancer-site estimates over the model's
two-year horizon, including colorectal cancer and an overall cancer estimate.
It returns the existing `ModelPrediction` contract so a future pipeline can place
it in `AnalysisResult.predictions`.

The equations use fractional-polynomial age and BMI terms, published coefficients,
and sex-specific symptom and history factors. Site scores are exponentiated and
normalized together with the model's implicit baseline. The baseline is used only
inside the calculation; the output does not expose a “no cancer” result. No
high/low cutoff is added, so QCancer alone does not flag or route a patient.

The model requires complete inputs for its selected equation. Input fields are:

- age 25–89, male/female model selection, BMI 20–40, and a Townsend score from −7
  to 11;
- smoking category: 0 never, 1 former, 2 current under 10 cigarettes/day, 3
  current 10–19/day, 4 current 20 or more/day;
- alcohol category: 0 none, 1 under 1 UK unit/day, 2 1–2 UK units/day, 3 at
  least 3 UK units/day;
- every sex-specific yes/no factor named in `FEMALE_BINARY_INPUTS` or
  `MALE_BINARY_INPUTS` in the module. `b_` fields are medical history,
  `fh_` fields are family history, `new_` fields are red-flag symptoms,
  `s1_` fields are recent general symptoms, and `c_hb` is anaemia.

If a value is absent or unknown, the calculator returns `insufficient_data` with
the missing field names. It never changes unknown values to `false`. Unsupported
or out-of-range inputs also return without a risk estimate. Each prediction
includes the ClinRisk disclaimer required by the published implementation.

### Finland limitation

QCancer-2013 was developed from UK primary-care records and its authors describe
the tools as intended for the UK. The equations use the UK Townsend deprivation
score; Junction cannot substitute a Finnish area-deprivation measure without
validating that change. The shipped example uses a clearly synthetic Townsend
value so the calculation can be demonstrated. The output is not calibrated or
clinically validated for Finnish patients and must not guide clinical care.

The colorectal rule engine and QCancer estimate should be reviewed side by side:
the rule engine can suggest physician review from documented evidence, while
QCancer provides a separate numerical estimate. A clinician remains responsible
for deciding what happens next.

## Running the synthetic example

From `cancersignal/backend/`, after installing the backend dependencies, run:

```sh
python -m app.risk_models.demo
```

The command prints the evidence-table matches and QCancer prediction separately
for one fully synthetic example. It makes no LLM or network call. It does not
change the current API or nurse dashboard.

## Future LLM handoff

The future extraction stage should populate `QCancer2013Input` from the patient
history, including explicit true/false/unknown values and source observation IDs.
It should not guess a negative from silence. The rule engine and QCancer
calculator can then run independently. QCancer returns the existing
`ModelPrediction` shape used by `AnalysisResult.predictions`. The current API's
legacy rule result still needs an adapter to the richer
`AnalysisResult.trigger_evaluations` contract. The API response and dashboard
have not yet been extended with the QCancer result, so that integration still
needs a coordinated response mapping.

## Source and license

QCancer-2013 equations are derived from ClinRisk's published open-source
implementation and its Python translation/reference code. The upstream source is
licensed under GNU AGPL version 3 or later; the license text is included in
`backend/app/risk_models/AGPL-3.0.txt`. Before distributing or hosting an
application that includes this implementation, the team should confirm it can
meet the license requirements.

References:

- [ClinRisk QCancer-2013 source modules](https://github.com/nhsland/clinrisk-modules/tree/master/qCancer)
- [Hippisley-Cox and Coupland, QCancer-2013 development paper](https://www.qresearch.org/Public_Documents/Hippisley-Cox%20BJGP%202012%20cancer%20men.pdf)
- [QCancer overview and intended population](https://www.qcancer.org/)
- [Python translation/reference implementation](https://huggingface.co/spaces/InstaDeepAI/sentinel/blob/main/src/sentinel/risk_models/qcancer.py)
