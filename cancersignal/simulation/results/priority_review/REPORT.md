# Priority and capacity comparison

All operational parameters and signals in this population stress experiment are hypothetical. The separate real-model replay retains authentic predictions. Relevant is an assumed need for investigation, not confirmed cancer. Thirty paired replications per setting; identical arrivals, random streams and capacity across arms. All four settings are reported.

A: standard care. B: historical serial review. C: nonblocking review. D is also exported, but has the same selection behavior as C when the legacy configuration has no workflow block. Priority consumes the same GP capacity, does not interrupt active work, and can delay ordinary visits. Hypothetical signals have no actual urgency category.

Primary outcomes count first investigation completions with full 60-day observation, not all tests or selected completers. P90 is a time quantile, not a fraction; the fraction still waiting at 30 days is reported separately. Capped P90 counts noncompletion as 60 days.

## GP capacity 2, fifo

| Endpoint | A | B | C |
|---|---:|---:|---:|
| Relevant cohort size | 162.433 | 162.433 | 162.433 |
| Investigations completed within 30 days (patients) | 82.400 | 56.967 | 97.900 |
| Investigations completed within 60 days (patients) | 123.267 | 137.567 | 138.800 |
| 60-day completion fraction | 0.761 | 0.848 | 0.855 |
| Gained 60-day completions versus A | 0.000 | 19.400 | 19.867 |
| Lost 60-day completions versus A | 0.000 | 5.100 | 4.333 |
| No completed investigation at 30 days (fraction) | 0.491 | 0.648 | 0.396 |
| Capped 60-day completion P90 (days) | 60.000 | 59.966 | 59.889 |
| Observed completion P90 (days; completers only) | 50.046 | 51.990 | 48.486 |
| GP utilization (fraction) | 1.000 | 1.000 | 1.000 |
| GP queue growth per day | 3.502 | 3.485 | 3.330 |
| Mean GP queue length | 338.983 | 339.118 | 324.171 |
| All-patient GP P90 (days; observed) | 21.674 | 20.280 | 19.934 |
| Reference-negative investigations per 1,000 | 162.458 | 224.640 | 226.362 |

C−A 60-day completion difference: 9.42 percentage points; paired 95% Monte Carlo interval [7.79, 11.04]. This is not clinical confidence or parameter uncertainty.

## GP capacity 2, priority

| Endpoint | A | B | C |
|---|---:|---:|---:|
| Relevant cohort size | 162.433 | 162.433 | 162.433 |
| Investigations completed within 30 days (patients) | 82.400 | 113.800 | 117.200 |
| Investigations completed within 60 days (patients) | 123.267 | 142.367 | 143.267 |
| 60-day completion fraction | 0.761 | 0.877 | 0.883 |
| Gained 60-day completions versus A | 0.000 | 19.133 | 20.000 |
| Lost 60-day completions versus A | 0.000 | 0.033 | 0.000 |
| No completed investigation at 30 days (fraction) | 0.491 | 0.298 | 0.278 |
| Capped 60-day completion P90 (days) | 60.000 | 58.715 | 58.306 |
| Observed completion P90 (days; completers only) | 50.046 | 39.534 | 39.887 |
| GP utilization (fraction) | 1.000 | 1.000 | 1.000 |
| GP queue growth per day | 3.502 | 3.309 | 3.233 |
| Mean GP queue length | 338.983 | 320.763 | 313.943 |
| All-patient GP P90 (days; observed) | 21.674 | 21.366 | 20.771 |
| Reference-negative investigations per 1,000 | 162.458 | 222.615 | 224.904 |

C−A 60-day completion difference: 12.18 percentage points; paired 95% Monte Carlo interval [10.81, 13.54]. This is not clinical confidence or parameter uncertainty.

## GP capacity 3, fifo

| Endpoint | A | B | C |
|---|---:|---:|---:|
| Relevant cohort size | 162.433 | 162.433 | 162.433 |
| Investigations completed within 30 days (patients) | 146.600 | 154.200 | 154.200 |
| Investigations completed within 60 days (patients) | 146.600 | 154.200 | 154.200 |
| 60-day completion fraction | 0.903 | 0.949 | 0.949 |
| Gained 60-day completions versus A | 0.000 | 7.600 | 7.600 |
| Lost 60-day completions versus A | 0.000 | 0.000 | 0.000 |
| No completed investigation at 30 days (fraction) | 0.097 | 0.051 | 0.051 |
| Capped 60-day completion P90 (days) | 34.171 | 22.036 | 22.021 |
| Observed completion P90 (days; completers only) | 21.891 | 21.768 | 21.759 |
| GP utilization (fraction) | 0.876 | 0.866 | 0.861 |
| GP queue growth per day | 0.011 | 0.015 | 0.013 |
| Mean GP queue length | 2.909 | 2.826 | 2.629 |
| All-patient GP P90 (days; observed) | 0.386 | 0.373 | 0.351 |
| Reference-negative investigations per 1,000 | 190.006 | 247.120 | 247.120 |

C−A 60-day completion difference: 4.65 percentage points; paired 95% Monte Carlo interval [4.02, 5.29]. This is not clinical confidence or parameter uncertainty.

## GP capacity 3, priority

| Endpoint | A | B | C |
|---|---:|---:|---:|
| Relevant cohort size | 162.433 | 162.433 | 162.433 |
| Investigations completed within 30 days (patients) | 146.600 | 154.200 | 154.200 |
| Investigations completed within 60 days (patients) | 146.600 | 154.200 | 154.200 |
| 60-day completion fraction | 0.903 | 0.949 | 0.949 |
| Gained 60-day completions versus A | 0.000 | 7.600 | 7.600 |
| Lost 60-day completions versus A | 0.000 | 0.000 | 0.000 |
| No completed investigation at 30 days (fraction) | 0.097 | 0.051 | 0.051 |
| Capped 60-day completion P90 (days) | 34.171 | 21.950 | 21.939 |
| Observed completion P90 (days; completers only) | 21.891 | 21.748 | 21.739 |
| GP utilization (fraction) | 0.876 | 0.866 | 0.861 |
| GP queue growth per day | 0.011 | 0.014 | 0.012 |
| Mean GP queue length | 2.909 | 2.670 | 2.534 |
| All-patient GP P90 (days; observed) | 0.386 | 0.388 | 0.360 |
| Reference-negative investigations per 1,000 | 190.006 | 247.120 | 247.120 |

C−A 60-day completion difference: 4.65 percentage points; paired 95% Monte Carlo interval [4.02, 5.29]. This is not clinical confidence or parameter uncertainty.
