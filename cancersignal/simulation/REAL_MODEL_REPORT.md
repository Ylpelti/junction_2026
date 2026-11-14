> Historical results: configurations are preserved in the corresponding result files. For the current location, priority scheduling and revised defaults, see README.md and PRIORITY_REVIEW_FINDINGS.md.

# Executed real-pipeline experiment — 14 November 2026

CancerSignal's actual LLM extraction and clinical rule outputs now drive the simulation. The approved one-line missing `validate_evidence` import was fixed in the isolated backend. Live inference used owned disposable databases; repeated simulations use exported predictions without further inference.

## What actually ran

Verda `kimi-k3-1-pro`, prompt `clinical-extraction-2`, `json_object`, reasoning `low`, maximum output 8,192 tokens. The original JSON-schema provider request was rejected; these explicit settings succeeded with the same model and local schema/evidence validation. Exact settings, prompt, schema, model configuration digest and backend source fingerprint are exported with the cache.

The backend API uses complete patient/time-eligible history with lexical ranking. Its separate hybrid RAG implementation is not wired into this route. The real numerical QCancer adapter ran, but all 33 cases returned `insufficient_data`; no risk values were invented. Routing uses actual triggered SUO rules requiring clinician review. Explanations use the existing deterministic fallback, not a second LLM. The main cache preserves exact structured clinical inputs; the auxiliary longitudinal cache additionally captures the actual LLM messages and retrieved context.

## Model evaluation and missing data

36 fictional cases were available, with separately authored reference labels. Coded extraction answers and labels were excluded from inference. 33 predictions passed validation (91.67% coverage). EVAL-014 and EVAL-031 failed source-offset validation; EVAL-035 failed extraction-output validation. They were preserved as failures, not negatives or random replacements. Full-cohort strict replay rejects missing predictions. A separately documented selection exports the 33 complete cases for simulation; excluding failures can bias pathway results.

| Split | Valid / planned | TP | FP | TN | FN | Recall | FPR | Precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All | 33 / 36 | 16 | 3 | 12 | 2 | 88.89% | 20.00% | 84.21% |
| Development | 17 / 19 | 8 | 2 | 6 | 1 | 88.89% | 25.00% | 80.00% |
| Test | 16 / 17 | 8 | 1 | 6 | 1 | 88.89% | 14.29% | 88.89% |

Recall/FPR/precision are conditional on a usable prediction. Positive-reference review yield including unavailable cases in the denominator is 16/20 = 80% overall and 8/10 = 80% on test. This is review-label agreement, not cancer sensitivity. The fixed cases count once; 30 replications do not increase the evaluation sample size.

Missed reference-positive cases: EVAL-006 and EVAL-007. Extra review recommendations: EVAL-017, EVAL-027 and EVAL-028. The source dataset already identifies EVAL-027 as clinically debatable and EVAL-028 as involving missing anemia reconciliation. Full patient-level classifications, urgency and recommended-action counts are in `model_evaluation.json`.

**Independent clinical evaluation remains unavailable.** The labels were authored separately but align with the same NICE/SUO rulebook used by the system. This demonstrates rule-aligned synthetic behavior, not independent diagnostic validity. A clinician-labeled external cohort is required to satisfy that part of the requested evaluation. Mapping a review-need label to simulation investigation relevance is itself a proxy assumption.

## All 33 validated cases

Each mode uses 30 paired replications, identical patients and arrivals, and models A/C/D. Intervals measure simulation Monte Carlo uncertainty, not clinical generalization.

| Endpoint | Baseline A | Real C | Real D | Hypothetical C | Hypothetical D |
|---|---:|---:|---:|---:|---:|
| Review-positive reference cases completing investigation within 30 days (%) | 71.48 | 86.67 | 82.59 | 85.74 | 79.44 |
| Within 60 days (%) | 71.48 | 86.67 | 82.59 | 85.74 | 79.44 |
| Capped days without completed investigation (positive reference cases) | 24.52 | 15.66 | 18.04 | 16.33 | 19.95 |
| Investigations per 1,000 reference-negative cases | 173.33 | 266.67 | 224.44 | 226.67 | 206.67 |
| GP service-days per 1,000 patients | 152.71 | 158.35 | 157.04 | 157.76 | 156.25 |
| Reviews per cohort | 0.00 | 8.73 | 6.10 | 6.80 | 4.17 |
| False-positive reviews per cohort | 0.00 | 2.47 | 1.60 | 1.17 | 0.83 |
| GP utilization (%) | 1.68 | 1.74 | 1.73 | 1.74 | 1.72 |
| Positive reference cases with longer capped wait than A (%) | 0.00 | 5.37 | 3.89 | 5.00 | 3.33 |

## 16 validated test cases

Each mode uses 30 paired replications, identical patients and arrivals, and models A/C/D. Intervals measure simulation Monte Carlo uncertainty, not clinical generalization.

| Endpoint | Baseline A | Real C | Real D | Hypothetical C | Hypothetical D |
|---|---:|---:|---:|---:|---:|
| Review-positive reference cases completing investigation within 30 days (%) | 70.37 | 84.81 | 80.37 | 84.07 | 76.67 |
| Within 60 days (%) | 70.37 | 84.81 | 80.37 | 84.07 | 76.67 |
| Capped days without completed investigation (positive reference cases) | 25.00 | 16.53 | 19.02 | 17.02 | 21.18 |
| Investigations per 1,000 reference-negative cases | 161.90 | 214.29 | 190.48 | 195.24 | 176.19 |
| GP service-days per 1,000 patients | 150.20 | 155.20 | 153.79 | 155.11 | 152.94 |
| Reviews per cohort | 0.00 | 3.83 | 2.73 | 3.13 | 1.83 |
| False-positive reviews per cohort | 0.00 | 0.83 | 0.57 | 0.40 | 0.27 |
| GP utilization (%) | 0.80 | 0.83 | 0.82 | 0.83 | 0.82 |
| Positive reference cases with longer capped wait than A (%) | 0.00 | 4.07 | 2.22 | 3.70 | 2.22 |

## How the apparent benefit is calculated

Baseline probabilities decide which patients already receive investigation. For C, existing indications proceed without a serial AI review. An actual positive recommendation can cause a paid GP review for other patients; configured clinician acceptance and escalation can add an investigation. D additionally applies the configured urgency-dependent review-selection policy. An alert is never a confirmed diagnosis.

For each reference-positive case, completion by 60 days is measured from first contact. Capped time is `min(time to investigation completion, 60)`, with 60 for noncompletion. Identical seeds pair operational draws across pathways; differences are computed per replication and summarized with paired Student-t 95% intervals.

In the 33-case replay, C improves 60-day completion by 15.19 percentage points (95% Monte Carlo interval 12.11–18.26) and lowers capped time by 8.85 days (7.33–10.38 fewer). D improves completion by 11.11 points (7.93–14.29) and lowers capped time by 6.48 days (4.95–8.01 fewer). These gains arise under assumed care-routing probabilities and service times. C also increases investigations in reference-negative cases and GP work. Individual harms remain visible: some positive-reference patients have longer waits. All paired distributions, missed completions, queue and resource measures are exported.

Hypothetical mode uses assumed TPR 0.80 and FPR 0.12. Real mode never consults those rates. C is the cleaner prediction comparison: D also combines real urgency with clinician policy, whereas hypothetical D uses uniform selection. Neither mode gets fictional duplicate-test savings. The small fixed cohort creates near-zero GP queues and about 1.7% utilization; this experiment does not establish performance under realistic system congestion. Replicating these cases would not provide independent population evidence.

## Actual patient trace

EVAL-009's original note is “Kirkasta verta ulosteen pinnalla kahdesti tällä viikolla.” The real extractor reports current rectal bleeding with that exact source quote. Rule SUO06 matches age 50+ and rectal bleeding; its action is “Physician review: consider FIT”, urgency `review`.

In seed 1001, baseline GP routing does not investigate this patient. In C, GP review runs at simulation days 37.1551–37.1977, the clinician escalates, and investigation finishes at day 44.4115, 7.4115 days after contact. In D, the review-selection policy skips review. `study/patient_trace.json` contains the original records, precise pipeline input and output, separate reference label, and A/C/D event histories. This is a selected demonstration, not a representative efficacy estimate.

The separate EVAL-003 longitudinal trace uses only its old screening note at the early cutoff and the later available records at follow-up. Actual output changes from `none` to `urgent`. In the mechanics demonstration, a forced follow-up review consumes GP capacity and then leads to investigation; baseline does not investigate. Early inference receives no later labels or records. This forced-policy trace is excluded from the model-performance and 30-replication tables.

## Artifacts and validation

`results/real_model/` includes authentic predictions and failures, prompts/schema, selection provenance, full real/hypothetical replication results, CSV comparison, patient traces and model evaluation for both cohorts. `data/real_model/` contains clinical inputs, separately held labels and dataset provenance. See `REAL_MODEL_README.md` for offline replay and live inference commands.

45 simulation tests passed; 76 backend extraction tests and the backend handoff regression passed after the approved import fix. Every exported successful main and follow-up entry passed strict source/input/provenance validation. No changes were merged into main or pushed by this integration task.
