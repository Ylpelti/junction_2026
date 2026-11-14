# Historical simulation documentation

This describes earlier defaults; use README.md for current commands and scheduling.

# CancerSignal pathway simulation

Independent SimPy comparison of baseline care and clinician-reviewed CancerSignal signals under identical capacities. All default parameters are hypothetical operational assumptions, not Finnish healthcare statistics or clinical evidence.

## Location and isolation

Repository inspection found the reference project at `../cancersignal`. The requested `junction2026` development area did not exist, so this directory was created alongside CancerSignal in the existing `junction_2026` workspace. No backend modules are imported and no database, model, API, frontend or benchmark is changed. No live LLM calls are made.

## Exact execution instructions

From the workspace root:

```sh
cd cancersignal/simulation
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m cancersignal_sim run --config config/demo.json --out outputs/demo
.venv/bin/python -m cancersignal_sim sensitivity --config config/demo.json --out outputs/sensitivity
.venv/bin/python -m cancersignal_sim adapt-seed --project ../cancersignal --out outputs/seed_patients.json
```

Python 3.11+ is required. Tested with Python 3.14, SimPy 4.1.2 and Matplotlib 3.11.2. Module commands work directly from this directory with dependencies installed, even without editable installation. No FastAPI or PostgreSQL service is needed. `--no-plots` skips rendering.

## Configuration and pathway

`config/demo.json` sets horizon, warmup, Poisson arrivals, assumed relevant-case prevalence, parallel resource capacities, lognormal service means/CVs, review behavior, routing probabilities, inter-stage delays and seeds. The number of seeds is the replication count. CV zero gives deterministic service. Times are effective calendar days: calibrate service and capacity together to working hours before interpreting them.

Arrival → nurse → GP → optional review on the shared GP queue → investigation or one delayed GP follow-up → investigation → possible specialist referral → specialist evaluation → diagnostic completion → optional treatment milestone.

All services use FIFO queues. An alert adds a processing delay and can reduce initial GP service time by a bounded configurable amount. Review requires another GP queue entry and consumes GP capacity; escalation is probabilistic after review completes. It can avoid a follow-up visit but cannot bypass diagnostic/specialist queues or force referral. False negatives still receive ordinary care. All patients not initially investigated or escalated get one follow-up in this simplified model, including other/unknown cases. This is a strong operational assumption, especially for routine histories.

Diagnosis means operational completion of the specialist diagnostic pathway, not confirmed cancer. Treatment is an assumed milestone for reference-relevant cases only, with a probability and fixed delay; treatment capacity is not modeled. There is no priority scheduling, disease progression, mortality or survival benefit.

The finite horizon does not drain queues. Pre-warmup arrivals load resources; patient summaries include arrivals at/after warmup. Resource utilization and queue lengths integrate activity in `[warmup, duration)`. Resource wait distributions include services starting in that interval. Defaults intentionally remain unchanged after evaluation: the GP queue is overloaded and does not reach steady state.

## Existing data and model handoff

The adapter reads the literal `HISTORIES` assignment in `backend/app/db/seed.py` through AST, without executing the seed. It exports the eight original patient IDs, note/lab IDs, note text, haemoglobin values and timestamps. It selects note/lab history, not the entire relational fixture: duplicate symptom rows and separate investigation observations are omitted. All reference labels remain unknown. These examples are not population estimates.

`--patients` accepts a JSON array with this normalized shape:

```json
[{
  "patient_id": "synthetic-example",
  "arrival": 35,
  "relevant": true,
  "label_source": "independent scenario author: hypothetical",
  "cohort": "example",
  "region": "unspecified",
  "group": "unspecified",
  "as_of": "2026-02-12T10:00:00+00:00",
  "clinical_observations": [],
  "prediction": {
    "review_signal": true,
    "source": "evaluated-model:version",
    "as_of": "2026-02-12T10:00:00+00:00"
  }
}]
```

`relevant` is boolean or null: assumed need for the modeled investigation, not a cancer diagnosis. Non-null labels require independent `label_source`. Generated labels come from the explicitly hypothetical prevalence. No label is inferred from text or predictions.

`--predictions` accepts a JSON array of the existing shared `ModelPrediction` shape alongside `--patients`: `patient_id`, `model_name`, `model_version`, `as_of`, `prediction_type: "review_signal"`, and boolean `value`. Raw outputs are retained as provenance. Unknown/duplicate IDs, ambiguous numerical scores and future predictions are rejected. Prediction and patient cutoff timestamps must be timezone-aware. An upstream owner must explicitly map other outputs into a validated review signal; no risk model or threshold is implemented here. The `SignalProvider` protocol also permits a replacement Python implementation.

Explicit predictions override hypothetical rates. Labeled patients without predictions use configured TPR/FPR. Unknown-label patients without predictions receive no signal; those with predictions can receive reviews but cannot be counted as true/false positives. Separate `*_unknown` routing probabilities apply to unknown labels. Clinical source observations, model predictions and simulation events remain distinct.

For the imported histories, set warmup to zero because arrivals are days 0–7:

```sh
.venv/bin/python -c 'import json; c=json.load(open("config/demo.json")); c["warmup"]=0; json.dump(c,open("outputs/seed_config.json","w"),indent=2)'
.venv/bin/python -m cancersignal_sim run --config outputs/seed_config.json --patients outputs/seed_patients.json --out outputs/seed_demo
```

Historical timestamps remain provenance; simulation event times are relative days. Historical visits are not automatically new arrivals. Supplied region/group labels create strata only, with no invented regional effects.

## Outputs and statistical interpretation

- `results.json`: configuration, assumptions, seeds, patient inputs/outcomes, events, resource states, metrics, paired differences and replication statistics.
- `patients.csv`, `events.csv`, `resource_states.csv`: detailed records with seed/scenario.
- `paired_statistics.csv`: mean assisted-minus-baseline difference, SD, Monte Carlo standard error, range and valid pair count.
- `comparison.png`: investigation delay distribution, GP queue, utilization and selected paired outcomes.
- `sensitivity.json`, `sensitivity.csv`, `false_positive_sensitivity.png`: one-factor sweeps of TPR/FPR, three resource capacities, review workload and GP time saving.

Negative delay differences favor assisted care. Capacity sweeps change both scenarios equally. Paired scenarios share arrivals, characteristics, capacities and hashed patient/stage random streams, so branching cannot shift subsequent random draws. Seeds create independent generated populations. Supplied cohorts stay fixed across seeds, so uncertainty then covers service/routing variation only.

Median/P90 times are conditional on reaching each milestone before the horizon. Read them alongside `not_observed`, `unfinished`, `relevant_no_route`, `relevant_without_investigation` and denominators. `not_observed` mixes non-routing, inapplicability and censoring; it is not a survival estimate. Changing routes can change the patients included in conditional medians. Empty times are null, not zero. Strata include relevance, region, group and cohort.

Baseline signal fields are unavailable, not classifier failures. Interpret assisted TP/FP/FN counts directly, not their baseline differences as accuracy improvements. Review starts and completions are separate. Monte Carlo error bars are not clinical confidence intervals and exclude parameter uncertainty. Increase replication count/horizon, check warmup stability and calibrate assumptions before substantive interpretation.

## Future calibration

New empirical parameters should carry source, population, setting, units, period and uncertainty. Independent reference labels must remain separate from predictions. Extraction F1/retrieval recall cannot supply detection sensitivity. No Finnish clinical estimates were claimed or substituted here. Published pathway data could later calibrate arrival patterns, opening hours, routing and delay distributions. JSON exports permit later frontend integration without running this simulation inside FastAPI. Optimization is deferred.

## Four-workflow study (incremental extension)

The original `run`, `sensitivity`, and `config/demo.json` remain available. The
original A/B event streams are checked against frozen SHA-256 regression fixtures.
`run` still exports the original JSON/CSV structure, with additive patient fields
and P95 values. `simulate(..., model="A" | "B" | "C" | "D")` selects a workflow;
existing `assisted=False/True` calls continue to select A/B.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m cancersignal_sim study --config config/workflows.json \
  --reference --drain --sensitivity --workers 4 --out outputs/workflow_study
```

`workflows.json` specifies 30 independent seeds. `--replications N` explicitly
replaces that seed list; use at least 30 for the main comparison. `--workers` runs
independent settings in separate processes without changing their random streams.
The full command runs 46 settings: four capacity/horizon combinations, an original
routing reference, five closed-arrival workload experiments, and 36 one-factor
sensitivity settings (18 at each GP capacity). Each setting compares all four arms
on the same population. The four principal experiments use GP capacity 2/3 and
horizon 180/365. No arm receives extra resources within a setting.

| Model | Workflow |
| --- | --- |
| A | Ordinary care with no review signal |
| B | Preserved serial alert review, including original pre-GP processing delay and assumed initial assessment saving |
| C | Initial GP decision first; already-indicated investigation proceeds directly; additional review only when an alert could change the plan |
| D | C plus configurable selection of alert reviews and clinician-reviewed cancellation of flagged repeat tests |

C/D obtain the signal after initial GP assessment and do not claim B's pre-GP
service saving. In C/D a positive signal on an already-indicated pathway cannot
add a review or processing wait. Shared queues can still change its waiting time
indirectly. Original GP decisions and ordinary-care follow-up/referral decisions
are stored unchanged in every arm. Reference relevance supplies the hypothetical
generative distributions; the intervention policy receives the signal and
observable clinical decisions, never reference relevance. A test holds those
observations constant while changing the reference label.

New follow-up routing is common to all arms: 45% follow-up, 35% monitoring and
20% discharge in the illustrative configuration, conditional on no initial
investigation. Monitoring/discharge include modeled safety-net instructions at
initial assessment, not a separate free appointment. A subsequent symptom change
can trigger a new GP assessment and investigation; probabilities differ by
reference scenario only in the common generative model. Non-escalating review can
retain the plan or request follow-up. The `workflow` block may be omitted to
restore automatic follow-up, no symptom-change visits and no planned repeats.

Repeat tests are explicitly separate stages, at most one per patient. The common
population includes a hypothetical planned-repeat flag and reference avoidability.
An imperfect observable duplicate-evidence flag has configurable TPR/FPR; D can
request a clinician audit using **the same GP resource**. Cancellation occurs
only after that audit and a configurable clinician decision. First investigations
are never cancelled. Every incorrect cancellation is counted, including necessary
repeats for relevant patients. Diagnostic completion after such cancellation is
still only an operational milestone; the model does not establish diagnostic
accuracy or harmlessness. No low AI score can cancel an indicated first test.

Selective alert review uses a configurable selection probability independent of
reference labels; it is **not a validated clinical triage or scoring algorithm**.
Model D is a candidate workflow, not the output of mathematical optimization.
The review, selection and repeat-evidence assumptions can all be unfavorable.

### Study outputs and denominators

Each setting exports JSON containing configuration, per-seed metrics and summaries,
plus a CSV of means, paired differences from A, two-sided 95% Student-t intervals,
and paired relative-percent changes where baseline values are nonzero. Relative
statistics report their own valid-pair counts and are null for zero denominators.
Intervals describe Monte Carlo variation, exclude parameter uncertainty, and are
not adjusted for multiple exploratory comparisons. Degenerate zero-event intervals
are not proof that a rare safety event cannot occur. Proportions may have t-based
intervals outside natural bounds; they are not silently clipped.

- `cohort.*`: identical arrivals in `[warmup, horizon−60)` for all arms. All have
  60 observable days; completion endpoints use **service end**. The same cohort
  supplies 30/60-day rates. Capped time counts noncompletion as 60 days. Observed
  P50/P90/P95 retain their observed-only limitation and include denominators.
- `paired.*`: individual outcomes against A, including capped benefits/harms,
  lost/gained 60-day completions and initially-indicated patient delays. Separate
  post-GP comparisons isolate direct serial review from shared queue effects;
  these post-GP comparisons require investigation in both arms.
- `event.*`: all resource activity during `[warmup, horizon)`, including patients
  arriving before warmup. Time-weighted queues, utilization, queue growth and
  review service are not confused with cohort-based resource use.
- `lifecycle.*`: for the **closed_arrivals_drain** experiment, the same 180-day
  arrival population is observed to day 1500. Verify zero unfinished patients
  before interpreting complete workload totals. These measures distinguish work
  avoided from work merely left in queues. In other settings they are truncated
  delivered work and must not be presented as eventual workload.

Total service-days sum effective service time across nurse/GP/diagnostic/specialist
resources. They are not staffing-equivalent costs or monetary savings. Model D can
move work between resources, and low utilization alone does not establish improved
access. Nonrelevant tests are defined against the synthetic reference label; only
`correctly_avoided_repeat` has a separate explicit avoidability reference.

The first seed of each main/reference setting exports full patient inputs, events
and resource states under `sample_runs/`. All 30 seeds export per-run KPI data.
`comparison.csv` combines every setting, and `manifest.json` states methodology.
No regional fairness conclusion is possible for generated records with unspecified
region/group; the original generic export still supports stratification of supplied
records. The study CLI currently generates synthetic populations, while the original
`run --patients --predictions` and Python provider interface remain available.


After experiments complete, regenerate the report and comparison figure without
rerunning simulations:

```sh
.venv/bin/python -m cancersignal_sim.study_report --input outputs/workflow_study --out WORKFLOW_COMPARISON.md
```

The manually written `WORKFLOW_FINDINGS.md` interprets those generated tables and
answers the seven evaluation questions. Compact review artifacts in `results/`
retain the principal KPI summaries and exact configurations; full per-replication
metrics and sample event traces remain in the generated output directory.


## Executed real CancerSignal integration

See [replay instructions](REAL_MODEL_README.md) and [measured results and limitations](REAL_MODEL_REPORT.md). Authentic synthetic-case predictions and results are in `results/real_model/`.
