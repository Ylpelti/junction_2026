> Historical results: configurations are preserved in the corresponding result files. For the current location, priority scheduling and revised defaults, see README.md and PRIORITY_REVIEW_FINDINGS.md.

# Nonblocking review and resource optimization: findings

## Result

Model C is the strongest access workflow under the main hypothetical settings.
Model D reduces testing relative to C, but gives up some access benefit and does
not reduce complete workload below baseline. **No main setting demonstrates the
combined objective of faster appropriate access, fewer nonrelevant investigations,
and no added overall workload.** D is a candidate policy, not a mathematically
optimized or clinically validated algorithm.

The study extends the existing engine rather than replacing it. The original
`config/demo.json` and A/B event traces remain reproducible. New common routing
assumptions permit follow-up, monitoring, discharge with safety-net instructions,
and reassessment after symptom change. C/D never hold a GP-indicated first
investigation for a separate alert review. D can cancel only an explicit repeat,
after a paid GP audit of an imperfect duplicate-evidence flag. Selection uses a
hypothetical probability independent of true relevance.

## Design and endpoints

The full study has 46 settings, each with 30 paired replications of four models:
5,520 individual simulations. Four principal settings cross GP capacities 2/3
with 180/365-day horizons; 36 one-factor sensitivity settings cover the requested
signal, review, follow-up, avoidability and prevalence assumptions, plus review
selection and false duplicate evidence, at both capacities. An original-routing
reference and five closed-arrival workload studies complete the design.

All comparisons share patient arrivals, clinical-plan draws, resources and service
random streams. Primary cohort endpoints use identical arrivals from day 30 to
horizon−60. All have 60 observable days, including non-routed patients. First
investigation **completion**, rather than start, defines the 30/60-day endpoint.
Capped time assigns 60 days to noncompletion. Resource event measures separately
include all work after warmup. Same-patient comparisons distinguish direct review
waiting from shared-queue spillover. Observed percentiles still have selection
limitations and are accompanied by counts.

Confidence intervals are paired Student-t 95% Monte Carlo intervals across seeds,
not clinical CIs or estimates of parameter uncertainty. The explorations are not
multiplicity-adjusted. Configurations, complete per-replication KPI records,
relative changes, valid-pair counts and sample patient event traces are exported.

## Main comparison

For two GP slots over 180 days, with revised routing in **all** arms:

| Measure | A baseline | B serial | C nonblocking | D selective/repeat audit |
| --- | ---: | ---: | ---: | ---: |
| Relevant investigation completion within 60 days | 77.76% | 88.72% | 88.76% | 84.67% |
| Relevant capped time without completed investigation | 25.39 d | 19.69 d | 18.40 d | 21.09 d |
| Tests per 1,000 reference-other patients, including repeats | 186.16 | 257.27 | 257.38 | 217.67 |
| Mean GP queue (event-based) | 36.18 | 52.86 | 44.70 | 45.01 |

C reduces capped delay by **6.99 days [6.44, 7.54 days saved]**, increases 60-day
coverage by **10.99 percentage points [9.96, 12.03]**, but adds **71.22 tests
[67.49, 74.95] per 1,000 reference-other patients**. D saves **4.30 days
[3.86, 4.74]**, improves coverage by **6.91 points [6.07, 7.74]**, and still adds
**31.51 tests [28.76, 34.26]** per 1,000 reference-other patients.

The revised baseline is different from the original automatic-follow-up baseline.
Do not attribute that change in baseline congestion to CancerSignal. At three GP
slots, utilization is approximately 68% and queues are small; C still has the
largest mean access benefit. At two slots, near-full utilization and positive queue
growth persist into the 365-day experiment. Warmup trimming does not make these
queues steady-state estimates.

## Answers to the seven evaluation questions

1. **Does nonblocking review remove unnecessary serial approval delay?** Yes,
   directly. In the original-routing reference, B adds 11.21 post-GP days
   [10.63, 11.79] for relevant initially-indicated cases observed in both arms.
   C's corresponding difference is approximately 0.0025 days, attributable to
   downstream queue effects. The older 9.37-day number used five different seeds,
   different cohort selection and a different summary; it should not be expected
   to recur exactly. Frozen original event traces verify backward compatibility.
   Nonblocking does not eliminate indirect delays: with revised routing at two
   GP slots, initially-indicated relevant patients still experience about 0.28
   additional capped days through shared-capacity effects.

2. **Does selective review reduce total GP workload?** It reduces alert-review
   workload, but not total GP workload below baseline. In the 180-day cohort,
   C uses 6.51 alert-review service-days per 1,000 arrivals; D uses 4.16 plus 0.58
   repeat-audit days. Avoided escalation can retain follow-up work. In the fully
   drained workload experiment, total GP service-days per 1,000 arrivals are
   A 168.01, B 170.57, C 169.27 and D 169.40. C adds 1.26 days [0.98, 1.53]
   versus A; D adds 1.39 [1.19, 1.59]. D−C is +0.13 [−0.02, 0.29], so the
   small difference between C and D is not resolved by these runs.

3. **Does D decrease nonrelevant investigations?** Relative to C, yes; relative
   to A, not under default assumptions. D performs about 40 fewer tests per
   1,000 reference-other patients than C, but remains about 31–32 above A.
   At assumed zero signal FPR, D can reduce such tests below A, but this requires
   that idealized specificity assumption and is not established model performance.
   Reference-other tests are a proxy; only the separately labeled avoidable-repeat
   variable explicitly represents unnecessary duplication.

4. **Does access improve for relevant patients?** Yes on average in the four
   main settings. C improves 60-day completion by approximately 11 percentage
   points; D improves it by approximately 7 points. However, individual effects
   differ: at two slots/180 days, 54.0% of relevant patients have some increase in
   capped time under C, while fewer patients receive much larger benefits. This
   fraction includes arbitrarily small positive delays; it is not a clinical
   harm threshold. D additionally cancels necessary repeats in relevant patients:
   0.37 such cases per eligible cohort on average at two slots/180 days, increasing
   to 1.17 with the longer cohort at 365 days. These are actual modeled safety
   failures, not discarded outliers. Diagnostic milestones following a mistaken
   cancellation do not prove diagnostic completeness or correctness.

5. **Are results robust across capacity and prevalence?** The main access gain
   persists at both capacities and across the tested prevalence assumptions, but
   efficiency does not become workload-neutral. Closed-arrival tests at prevalence
   5% and 30% show D still adding approximately 8.73 and 10.40 total service-days
   per 1,000 arrivals. Capacity 3 avoids the pronounced GP overload seen at 2;
   this is an illustrative comparison, not a calibrated staffing prescription.
   One-factor experiments cannot establish robustness to every joint parameter
   combination.

6. **Is efficiency improved or are waits redistributed?** Both mechanisms occur,
   but no net workload reduction is demonstrated at defaults. The fully drained
   totals (all resources) are A 285.85, B 307.94, C 306.63 and D 295.26 effective
   service-days per 1,000 arrivals. C adds **20.78 [20.13, 21.43]**; D adds
   **9.41 [8.84, 9.98]**. All drain runs finish all patients, so these increases
   cannot be dismissed as horizon censoring. D reduces work compared with C,
   while expanding access compared with A. That may be a useful tradeoff, but it
   is not the requested no-extra-workload result. Adding service-days across
   resources does not establish financial or staffing equivalence.

7. **Which assumptions most influence conclusions?** GP capacity and ordinary
   follow-up routing determine congestion; FPR and prevalence determine false
   review/test burden; review duration determines whether gains survive added
   GP work. Duplicate avoidability and evidence accuracy determine D's potential
   savings and safety. With FPR 0.4, D's complete added workload rises to about
   29.88 days per 1,000 arrivals. With FPR zero, D's added workload shrinks to
   0.51 [0.02, 1.01] but GP work still rises by 0.61 [0.50, 0.73]. Thus even the
   zero-FPR stress case does not demonstrate the combined objective. The detailed
   sensitivity tables expose unfavorable settings rather than selecting a favorable
   parameter combination for the headline. With mean review service 0.20 days and
   two GP slots, C's capped-time difference is −0.56 days [−1.31, +0.19] and
   D's is −0.55 [−1.21, +0.11]: neither establishes an access improvement.
   At three GP slots, the same review-duration setting retains substantial gains.

## Practical interpretation

Choose C as the main workflow candidate when prioritizing timely access; keep D
as a transparently labeled efficiency/safety experiment. Do not describe D as
universally best, workload-saving or safe. Validate the actual review-selection
logic, ordinary-care follow-up rates and duplicate-evidence quality before using
these estimates in any operational decision. No cancer survival, stage-shift,
clinical diagnostic accuracy, real Finnish performance or regional equity benefit
is modeled or claimed.

See `WORKFLOW_COMPARISON.md` for generated tables and confidence intervals,
`results/workflow_summary.csv` for compact machine-readable KPIs, and
`outputs/workflow_study/` for all per-replication metrics and sample traces.
