> Historical results: configurations are preserved in the corresponding result files. For the current location, priority scheduling and revised defaults, see README.md and PRIORITY_REVIEW_FINDINGS.md.

# Implementation and demonstration report

## Repository findings and integration boundary

The workspace is `/Users/joonavanska/junction_2026`; the reference project is its `cancersignal` subdirectory. Its `AGENTS.md`, API contracts, seed script, database session, Docker Compose, analysis response, reasoning interfaces and model prediction schema were inspected. The existing `cancersignal/simulation` directory contains only a placeholder and was left unchanged. This implementation lives in the requested separate `junction2026` development area.

CancerSignal uses FastAPI, SQLAlchemy, PostgreSQL/pgvector and patient/encounter/observation records. Seed histories contain eight fictional longitudinal scenarios, stable UUIDs, notes and haemoglobin measurements. They explicitly do not contain clinical reference labels. Analysis responses carry findings, trigger results, evidence and provenance; `ModelPrediction` carries versioned, timestamped values. The RAG example evaluation reports retrieval/context measures, not cancer detection sensitivity. None of those benchmark numbers is used as TPR/FPR. The seed-file fallback avoids requiring database access or importing application services.

## Architecture and assumptions

SimPy handles FIFO nurse, GP, diagnostic and specialist resources. Reviews and follow-ups share GP capacity. Service draws are lognormal with configurable CV, or deterministic at CV zero. Arrivals are Poisson. Stable hashed random streams pair each patient's characteristics, service durations, decisions and signal draws across scenarios. Independent seeds produce replications; sensitivity varies one assumption at a time using the same seeds. No risk models, optimization or shared contracts were implemented or changed.

All numeric defaults are demonstration assumptions. Reference relevance describes simulated need for investigation, not confirmed cancer. Clinician routing is probabilistic; review can expedite investigation but does not automatically refer or treat. In this simplified model, every patient not initially investigated/escalated receives one follow-up. Consequently escalation can replace follow-up work, including for false positives. The net workload can therefore fall even as unnecessary investigations rise; this is an assumption to calibrate, not a claimed benefit of false alarms.

Capacity is continuous effective capacity, without clinic calendars or background workload. Diagnosis is diagnostic-pathway completion; treatment is a delayed milestone without its own constrained resource. No progression, survival, stage shift, abandonment or mortality is modeled. Regions/groups only stratify results; they do not change service behavior.

## Executed evaluation

The demo uses seeds 101, 202, 303, 404 and 505, a 180-day horizon and 30-day warmup. The sensitivity sweep contains 22 one-factor settings, each with five paired replications. The default config was not tuned after observing results.

Selected assisted-minus-baseline outcomes (days; uncertainty is Monte Carlo SE across five paired runs):

| Assumption setting | Relevant investigation median | Other-patient GP median |
| --- | ---: | ---: |
| Default | +5.22 (SE 0.69) | −1.01 (SE 0.10) |
| GP capacity 1 in both arms | +23.54 | −0.83 |
| GP capacity 3 in both arms | +0.06 | +0.001 |
| Review mean 0.20 days | +15.13 | +5.68 |

Defaults yield an average 110.8 additional false-positive reviews started per post-warmup arrival cohort. GP utilization is 100% in both arms over the measurement window; queues continue to grow. These runs describe a finite overloaded system, not steady state. Adding capacity to both arms exposes a different regime: at GP capacity 3, the mean relevant-case investigation delay falls by 2.56 days (SE 0.17), while the median barely changes. The number of relevant cases without an observed investigation falls by 15.8 on average. This illustrates both potential benefit and the need to examine distributions and coverage rather than one summary statistic.

With an assumed FPR of 0.8, the observed relevant-case median decreases by 2.80 days. This counterintuitive result must not be interpreted as evidence favoring false positives. Escalations replace follow-up visits in this model and change who reaches an observed milestone; additional diagnostics and finite-horizon selection also change the measured population. With larger review service times, the intervention clearly worsens waiting for both groups. Specialist-capacity changes have no effect on upstream investigation delays, as expected for a pathway without downstream blocking.

## Interpretation and validation

The simulation stops at its horizon and retains unfinished patients. Observed median/P90 delays exclude unobserved milestones; `not_observed` combines non-routing, inapplicability and censoring. Per-patient timestamps, completion status, reference labels and denominators enable inspection. This is not survival analysis, and conditional differences can compare different subsets. Warmup excludes early arrivals from patient metrics but preserves their resource load. Utilization and queue lengths are integrated over the post-warmup time window.

Tests cover fixed-seed reproducibility, equal paired populations/capacities, zero-signal event equivalence, analytical FIFO timing, resource bounds, queue-before-service ordering, transitions/counts, false-positive workload and spillover delays, false negatives receiving usual care, finite-horizon/warmup accounting, seed adaptation, prediction provenance/cutoff validation and input round trips. Demo and sensitivity CLI exports were executed and their plots visually checked.

JSON/CSV outputs and plots are under `outputs/demo` and `outputs/sensitivity` (ignored generated artifacts). The README provides exact commands to reproduce them. No commit, merge or push was performed. Future empirical calibration must separately validate population assumptions, routing behavior, reference outcomes and measured model predictions; retrieval or extraction benchmark quality alone cannot calibrate this pathway model.

## Subsequent workflow extension

The original findings above describe the initial serial-review implementation.
The added `study` command compares A/B/C/D with configurable follow-up routing,
nonblocking review and clinician-controlled repeat avoidance. The companion
`WORKFLOW_COMPARISON.md` reports the new 30-replication experiments; it does not
replace or retrospectively tune the original configuration. Read its safety,
cohort and workload qualifications before interpreting Model D as an improvement.
