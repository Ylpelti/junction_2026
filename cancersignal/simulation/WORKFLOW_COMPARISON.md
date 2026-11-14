> Historical results: configurations are preserved in the corresponding result files. For the current location, priority scheduling and revised defaults, see README.md and PRIORITY_REVIEW_FINDINGS.md.

# Models A–D: controlled comparison

All parameters are hypothetical. All settings use 30 paired replications unless their exported valid-pair count states otherwise. Brackets are 95% paired Student-t Monte Carlo confidence intervals for changes, not clinical validation or parameter uncertainty. No multiple-comparison correction is applied.

A = baseline; B = serial review; C = nonblocking review; D = selective review plus clinician-controlled repeat cancellation. Main settings use the same revised routing assumptions in all arms. The separate original-routing setting preserves the original behavior.

## Main endpoints

Cohort: identical arrivals from warmup through horizon−60, with a guaranteed 60-day observation window. Completion means the first investigation service has ended. Noncompletion contributes 60 days to capped time. Investigation counts include explicit repeats. Values are means of per-replication statistics.

| GP slots / horizon | Model | Relevant completion by 60d (%) | Change vs A (percentage points, 95% CI) | Capped time (days) | Change vs A (days, 95% CI) | Other-patient tests per 1,000 other patients |
| --- | --- | ---: | --- | ---: | --- | ---: |
| gp2_180 | A | 77.76 | 0.00 [0.00, 0.00] | 25.39 | 0.00 [0.00, 0.00] | 186.16 |
| gp2_180 | B | 88.72 | 10.95 [9.91, 12.00] | 19.69 | -5.70 [-6.30, -5.09] | 257.27 |
| gp2_180 | C | 88.76 | 10.99 [9.96, 12.03] | 18.40 | -6.99 [-7.54, -6.44] | 257.38 |
| gp2_180 | D | 84.67 | 6.91 [6.07, 7.74] | 21.09 | -4.30 [-4.74, -3.86] | 217.67 |
| gp3_180 | A | 77.97 | 0.00 [0.00, 0.00] | 23.52 | 0.00 [0.00, 0.00] | 186.94 |
| gp3_180 | B | 88.98 | 11.00 [10.02, 11.99] | 15.72 | -7.81 [-8.33, -7.28] | 258.24 |
| gp3_180 | C | 88.98 | 11.00 [10.02, 11.99] | 15.67 | -7.85 [-8.38, -7.33] | 258.24 |
| gp3_180 | D | 84.95 | 6.97 [6.14, 7.80] | 18.57 | -4.96 [-5.40, -4.51] | 218.35 |
| gp2_365 | A | 77.59 | 0.00 [0.00, 0.00] | 26.47 | 0.00 [0.00, 0.00] | 185.41 |
| gp2_365 | B | 88.52 | 10.93 [10.43, 11.42] | 22.70 | -3.76 [-4.42, -3.11] | 257.30 |
| gp2_365 | C | 88.73 | 11.14 [10.65, 11.62] | 20.20 | -6.26 [-6.62, -5.91] | 257.50 |
| gp2_365 | D | 84.73 | 7.14 [6.67, 7.60] | 22.72 | -3.74 [-4.04, -3.44] | 216.84 |
| gp3_365 | A | 78.11 | 0.00 [0.00, 0.00] | 23.50 | 0.00 [0.00, 0.00] | 186.72 |
| gp3_365 | B | 89.19 | 11.09 [10.63, 11.54] | 15.74 | -7.77 [-8.02, -7.51] | 258.90 |
| gp3_365 | C | 89.19 | 11.09 [10.63, 11.54] | 15.69 | -7.82 [-8.07, -7.56] | 258.90 |
| gp3_365 | D | 85.31 | 7.20 [6.76, 7.64] | 18.45 | -5.05 [-5.28, -4.83] | 218.11 |

## Direct serial delay versus indirect queue effects

Among relevant patients initially indicated by the GP and investigated in both arms, this table compares **post-GP** investigation delay against A. It separates serial review from changed initial GP queues; residual diagnostic contention can still change post-GP waiting. It is selected on both-arm observation.

| Setting | B change in days | C change in days | D change in days |
| --- | --- | --- | --- |
| original_routing | 11.21 [10.63, 11.79] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |
| gp2_180 | 1.75 [1.46, 2.04] | 0.01 [0.01, 0.01] | 0.00 [0.00, 0.00] |
| gp3_180 | 0.08 [0.07, 0.08] | 0.01 [0.01, 0.02] | 0.00 [0.00, 0.01] |
| gp2_365 | 3.06 [2.55, 3.56] | 0.01 [0.01, 0.01] | 0.00 [0.00, 0.00] |
| gp3_365 | 0.08 [0.07, 0.08] | 0.01 [0.01, 0.01] | 0.00 [0.00, 0.00] |

The historical 9.37-day estimate used five seeds, investigation start and a selected observed subset. It is not numerically comparable to the new 30-seed fixed-window study. Legacy event-trace regression tests verify unchanged A/B behavior; the original-routing row isolates C’s workflow effect.

## Complete workload, not just delivered work

Closed 180-day arrivals are followed to day 1500. All arms must have zero unfinished patients in every replication. Service-days sum resource-specific effective service time; they are not interchangeable staffing costs.

| Setting | Model | GP service-days / 1,000 arrivals | GP change vs A (95% CI) | Total service-days / 1,000 arrivals | Total change vs A (95% CI) |
| --- | --- | ---: | --- | ---: | --- |
| closed_arrivals_drain | A | 168.01 | 0.00 [0.00, 0.00] | 285.85 | 0.00 [0.00, 0.00] |
| closed_arrivals_drain | B | 170.57 | 2.56 [2.27, 2.85] | 307.94 | 22.08 [21.42, 22.74] |
| closed_arrivals_drain | C | 169.27 | 1.26 [0.98, 1.53] | 306.63 | 20.78 [20.13, 21.43] |
| closed_arrivals_drain | D | 169.40 | 1.39 [1.19, 1.59] | 295.26 | 9.41 [8.84, 9.98] |
| drain_prevalence_0.05 | A | 169.54 | 0.00 [0.00, 0.00] | 261.53 | 0.00 [0.00, 0.00] |
| drain_prevalence_0.05 | B | 170.92 | 1.38 [1.12, 1.63] | 279.77 | 18.25 [17.71, 18.79] |
| drain_prevalence_0.05 | C | 170.85 | 1.32 [1.09, 1.54] | 279.71 | 18.19 [17.65, 18.72] |
| drain_prevalence_0.05 | D | 170.83 | 1.29 [1.12, 1.47] | 270.26 | 8.73 [8.25, 9.22] |
| drain_prevalence_0.3 | A | 165.54 | 0.00 [0.00, 0.00] | 323.08 | 0.00 [0.00, 0.00] |
| drain_prevalence_0.3 | B | 169.93 | 4.39 [4.08, 4.69] | 350.73 | 27.65 [26.90, 28.40] |
| drain_prevalence_0.3 | C | 166.75 | 1.21 [0.94, 1.48] | 347.56 | 24.48 [23.72, 25.24] |
| drain_prevalence_0.3 | D | 167.10 | 1.56 [1.37, 1.76] | 333.48 | 10.40 [9.70, 11.10] |
| drain_signal_fpr_0.0 | A | 168.01 | 0.00 [0.00, 0.00] | 285.85 | 0.00 [0.00, 0.00] |
| drain_signal_fpr_0.0 | B | 169.93 | 1.92 [1.73, 2.10] | 294.11 | 8.25 [7.76, 8.74] |
| drain_signal_fpr_0.0 | C | 168.15 | 0.13 [-0.01, 0.28] | 292.32 | 6.47 [6.02, 6.92] |
| drain_signal_fpr_0.0 | D | 168.63 | 0.61 [0.50, 0.73] | 286.37 | 0.51 [0.02, 1.01] |
| drain_signal_fpr_0.4 | A | 168.01 | 0.00 [0.00, 0.00] | 285.85 | 0.00 [0.00, 0.00] |
| drain_signal_fpr_0.4 | B | 172.68 | 4.66 [4.27, 5.05] | 340.04 | 54.19 [53.26, 55.12] |
| drain_signal_fpr_0.4 | C | 172.50 | 4.49 [4.11, 4.87] | 339.87 | 54.01 [53.09, 54.94] |
| drain_signal_fpr_0.4 | D | 171.66 | 3.64 [3.34, 3.95] | 315.73 | 29.88 [28.96, 30.80] |

## Safety, unintended work and crowding

Rates of longer waits compare each patient’s 60-day capped completion time with their own baseline. This counts queue spillover and routing effects. Zero measured repeat harm does not prove safety; the repeat-avoidability reference is itself hypothetical.

| Setting / model | Relevant longer-wait fraction (%) | Lost relevant 60d completions (count) | Necessary repeats cancelled in relevant patients (count) | Mean GP queue | Queue growth / day |
| --- | ---: | ---: | ---: | ---: | ---: |
| gp2_180/A | 0.000 | 0.000 | 0.000 | 36.178 | 0.273 |
| gp2_180/B | 64.762 | 0.300 | 0.000 | 52.857 | 0.436 |
| gp2_180/C | 54.044 | 0.233 | 0.000 | 44.698 | 0.345 |
| gp2_180/D | 59.950 | 0.267 | 0.367 | 45.012 | 0.350 |
| gp3_180/A | 0.000 | 0.000 | 0.000 | 0.542 | 0.002 |
| gp3_180/B | 54.878 | 0.000 | 0.000 | 0.641 | 0.006 |
| gp3_180/C | 23.893 | 0.000 | 0.000 | 0.597 | 0.005 |
| gp3_180/D | 19.747 | 0.000 | 0.433 | 0.596 | 0.005 |
| gp2_365/A | 0.000 | 0.000 | 0.000 | 53.648 | 0.225 |
| gp2_365/B | 65.530 | 2.033 | 0.000 | 85.472 | 0.395 |
| gp2_365/C | 58.087 | 1.000 | 0.000 | 68.886 | 0.302 |
| gp2_365/D | 64.407 | 1.100 | 1.167 | 70.503 | 0.313 |
| gp3_365/A | 0.000 | 0.000 | 0.000 | 0.537 | 0.002 |
| gp3_365/B | 55.269 | 0.000 | 0.000 | 0.638 | 0.001 |
| gp3_365/C | 23.732 | 0.000 | 0.000 | 0.595 | 0.002 |
| gp3_365/D | 19.793 | 0.000 | 1.267 | 0.592 | 0.002 |

## Selective workflow D versus C

These are paired differences across the same seeds, not differences between independent confidence intervals.

| Setting | Capped relevant time D−C (days, 95% CI) | Other-patient tests D−C per 1,000 (95% CI) | GP workload D−C per 1,000 arrivals (95% CI; complete lifecycle for drain) |
| --- | --- | --- | --- |
| gp2_180 | 2.69 [2.37, 3.01] | -39.71 [-42.76, -36.66] | 0.04 [-0.17, 0.24] |
| gp3_180 | 2.90 [2.57, 3.23] | -39.89 [-42.97, -36.81] | 0.05 [-0.16, 0.25] |
| gp2_365 | 2.52 [2.33, 2.71] | -40.66 [-42.37, -38.95] | 0.12 [0.01, 0.24] |
| gp3_365 | 2.76 [2.59, 2.93] | -40.79 [-42.50, -39.08] | 0.16 [0.03, 0.29] |
| closed_arrivals_drain | 2.54 [2.29, 2.79] | -40.12 [-42.65, -37.59] | 0.13 [-0.02, 0.29] |

## Sensitivity summary

All settings below change one parameter, hold the same 30 seeds, and retain the paired A–D populations. GP capacity is varied in the main grid and each sensitivity is repeated at capacities 2 and 3. Changes below are against A. CIs and every KPI are available in comparison.csv.

| Setting | C capped-day change | D capped-day change | D other-test change / 1,000 |
| --- | ---: | ---: | ---: |
| gp2_prevalence_0.05 | -6.88 | -4.27 | 31.43 |
| gp2_prevalence_0.3 | -7.16 | -4.40 | 31.17 |
| gp2_service_review_mean_0.02 | -7.91 | -4.89 | 31.73 |
| gp2_service_review_mean_0.2 | -0.56 | -0.55 | 30.73 |
| gp2_signal_fpr_0.0 | -7.31 | -4.50 | -12.97 |
| gp2_signal_fpr_0.4 | -6.14 | -3.75 | 130.61 |
| gp2_signal_review_probability_0.5 | -3.83 | -2.32 | 12.60 |
| gp2_signal_review_probability_1.0 | -7.83 | -4.85 | 36.55 |
| gp2_signal_tpr_0.4 | -3.54 | -2.10 | 31.51 |
| gp2_signal_tpr_1.0 | -8.71 | -5.37 | 31.51 |
| gp2_workflow_avoidable_repeat_rate_0.0 | -6.99 | -4.42 | 45.54 |
| gp2_workflow_avoidable_repeat_rate_1.0 | -6.99 | -4.22 | 22.34 |
| gp2_workflow_duplicate_flag_fpr_0.0 | -6.99 | -4.31 | 32.17 |
| gp2_workflow_duplicate_flag_fpr_0.2 | -6.99 | -4.28 | 30.13 |
| gp2_workflow_followup_probability_0.2 | -9.27 | -5.92 | 33.97 |
| gp2_workflow_followup_probability_0.65 | -5.51 | -3.29 | 29.96 |
| gp2_workflow_selective_review_probability_0.3 | -6.99 | -1.97 | 6.35 |
| gp2_workflow_selective_review_probability_1.0 | -6.99 | -6.84 | 53.65 |
| gp3_prevalence_0.05 | -7.91 | -5.04 | 31.30 |
| gp3_prevalence_0.3 | -7.81 | -4.91 | 31.20 |
| gp3_service_review_mean_0.02 | -7.87 | -4.96 | 31.41 |
| gp3_service_review_mean_0.2 | -7.78 | -4.91 | 31.41 |
| gp3_signal_fpr_0.0 | -7.87 | -4.96 | -13.04 |
| gp3_signal_fpr_0.4 | -7.82 | -4.94 | 130.69 |
| gp3_signal_review_probability_0.5 | -4.29 | -2.73 | 12.49 |
| gp3_signal_review_probability_1.0 | -8.80 | -5.56 | 36.48 |
| gp3_signal_tpr_0.4 | -4.06 | -2.53 | 31.41 |
| gp3_signal_tpr_1.0 | -9.74 | -6.12 | 31.41 |
| gp3_workflow_avoidable_repeat_rate_0.0 | -7.85 | -4.95 | 45.61 |
| gp3_workflow_avoidable_repeat_rate_1.0 | -7.85 | -4.96 | 22.16 |
| gp3_workflow_duplicate_flag_fpr_0.0 | -7.85 | -4.96 | 32.06 |
| gp3_workflow_duplicate_flag_fpr_0.2 | -7.85 | -4.96 | 30.02 |
| gp3_workflow_followup_probability_0.2 | -9.41 | -6.01 | 33.97 |
| gp3_workflow_followup_probability_0.65 | -6.68 | -4.24 | 29.76 |
| gp3_workflow_selective_review_probability_0.3 | -7.85 | -2.30 | 6.31 |
| gp3_workflow_selective_review_probability_1.0 | -7.85 | -7.86 | 53.54 |

## Boundaries

The newer follow-up model changes baseline care as well as assisted care. Do not attribute the improvement relative to the old overloaded baseline entirely to AI. The common synthetic clinical-plan generator may use reference labels; intervention decisions see only its observable outputs and model signals. D’s selection is probabilistic, not a validated clinical prioritization model. First tests cannot be cancelled; false duplicate evidence can still cause incorrect repeat cancellations after paid clinician review.

A growing GP queue with near-full utilization indicates finite-horizon overload; these are not steady-state estimates. Cohort workload is truncated at 60 days. Complete workload claims come only from the closed-arrival drain settings. Waiting-time percentiles are observed-only, while completion rates and capped times retain all eligible patients. The two horizons contain different arrival cohorts. No survival, stage-shift, cost-effectiveness or regional-equity claim is supported.
