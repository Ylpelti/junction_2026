# CancerSignal simulation

See [finalization and compatibility with main](FINALIZATION.md): 51 simulation tests pass; historical replay is supported, while a separate backend handoff check currently fails on main. No backend fix is included.

The implementation now lives in `cancersignal/simulation/`. Default demonstration settings use three effective GP capacity units, nonblocking review (C), and nonpreemptive priority for remote physician review. All review time consumes the same GP capacity as appointments. Actual urgent recommendations rank before other review requests; ordinary appointments follow. Active appointments are never interrupted. The capacity units model continuous effective service, not a validated staffing schedule.

## Run

From the feature worktree root:

```sh
cd cancersignal/simulation
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m cancersignal_sim run --out outputs/demo
.venv/bin/python -m cancersignal_sim.pitch_study --out outputs/pitch_review
.venv/bin/python -m unittest discover -s tests -q
```

The demo generates a hypothetical population. It does not automatically read the old seed or the application's demo patients. `adapt-seed --project ..` remains an optional legacy adapter. No clinical accuracy claim can be inferred from generated reference labels.

The pitch study runs **all four combinations** of GP capacity 2/3 and FIFO/priority, each with 30 paired replications. It exports A/B/C/D, including the unfavorable historical serial-review B arm. A and every assisted arm have identical capacity within a setting. Increasing capacity is an explicit system scenario, not an AI benefit. Original configs are preserved as `config/*_fifo_original.json`; the original A/B event regression still passes. `config/demo_fifo_original.json` reproduces the old `run` behavior.

`run` now compares A/C by default. Its `headline_metrics.csv` and `comparison.png` lead with investigation completion within 30/60 days and the fraction without completion at 30 days. Gained and lost completions against A are both exported. Observed P90 is conditional on completing; capped 60-day P90 includes noncompleters as 60 days. P90 is a time threshold, not the proportion with long waits. All cohort endpoints use arrivals in `[warmup, duration−60)` so every patient has the full follow-up window.

## Authentic predictions

[Real inference and offline replay instructions](REAL_MODEL_README.md) describe the existing CancerSignal pipeline and exported synthetic-case predictions. Run the historical replay command in FINALIZATION.md from this directory with its explicit pipeline fingerprint. `--backend ../backend` intentionally rejects these old predictions against the changed main source. There is no random fallback in real mode. The historical [real-model report](REAL_MODEL_REPORT.md) retains its original FIFO/two-capacity results; the new priority replay is separately exported under `results/priority_review/real_model/`.

The main real cohort contains 33 successful predictions of 36 planned cases. Those records are evaluation cases, not the application's newer demo cohort. Labels were authored separately but align with the same clinical rulebook; they do not supply independent clinical validation. No new model calls are needed for this change. Missing QCancer inputs remain unknown.

## Interpreting the pitch

Use [the new findings](PRIORITY_REVIEW_FINDINGS.md) and its linked machine-readable outputs. Say “synthetic reference-positive cases” or “cases assumed to need investigation”, not “cancer patients”. Every numerical operational result remains conditional on assumed routes, clinician escalation and service times. Priority can delay ordinary appointments and does not create capacity. Read GP utilization, queue growth, noncompletion, gained/lost completions and reference-negative investigations together.

`review_queue` accepts `fifo` or `priority`; omission retains FIFO for old configs. Hypothetical signals have no urgency and receive ordinary review priority. Actual cached `urgent` recommendations receive higher priority, including later clinical snapshots. Review priority never reads reference labels. Diagnostic and specialist queues remain FIFO.

The extended four-workflow and sensitivity commands remain available; see [historical methods](LEGACY_README.md) for their endpoint definitions, not current defaults. Earlier reports and source hashes describe their recorded configurations and have not been relabeled as new results.
