# Simulation PR finalization

Base: `origin/main` at `9718db3d448d6ff9aac7dd1b33ff360f81afc49b` (checked by fetching origin). Work remains in the original `/private/tmp/cancersignal-real-integration` worktree, branch `feat/simulation-real-model`. Main contained only `cancersignal/simulation/.gitkeep`; neither the simulator nor its results were already merged. The simulation branch was fast-forwarded to that base before preparing the simulation-only commit.

No backend, clinical model, demo seed, frontend or shared schema change is included. The earlier local backend import fix was preserved outside the repository, then removed from the branch. The PR is draft because fresh live inference against the merged backend has a known upstream handoff failure. This does not prevent offline historical replay. Do not merge automatically.

## Validation executed

- `python -m unittest discover -s tests -v`: **51 passed**. Includes original A/B event hashes, shared GP accounting, nonblocking indication handling, nonpreemptive review priority, ordinary-visit delay, label/time isolation, authentic cache validation, tamper/stale-source rejection and explicit historical fingerprint pins.
- `PYTHONPATH=/path/to/historical/backend <backend-python> -m pytest integration_tests -q`: **1 passed** against the inference backend (`84409a6` plus the previously approved import fix).
- `PYTHONPATH=../backend <backend-python> -m pytest integration_tests -q`: **1 failed** against main `9718db3`, with `NameError: validate_evidence is not defined` at `app/extraction/service.py:59`. This is an unmodified upstream backend failure, not an expected-pass simulation test. It remains visible; the test was not skipped or weakened.
- Full pinned replay: 30 paired replications of A/C/D with 33 authentic predictions, plus their explicitly hypothetical benchmark (180 scenario runs), without provider calls. Results equal the preserved priority-review results exactly apart from the added cache-validation provenance field.
- All **368 existing result/output files** were checked by SHA-256 and remain byte-identical. `results/finalization/preserved_files_sha256.json` records the inventory. Committed `results/` contains portable predictions, traces and experiment summaries; the larger ignored `outputs/` files remain intact in the original worktree.

## Historical replay from main

From `cancersignal/simulation/`, with the simulation dependencies installed:

```sh
python -m cancersignal_sim.real_study \
  --cohort results/real_model/validated_cohort.json \
  --evaluation-cohort data/real_model/cohort.json \
  --labels data/real_model/labels.json \
  --cache results/real_model/cache \
  --expected-pipeline-sha256 d93db13173a7c74323ceea84ac77fe891064232082cbb5e576404ae490bf6d0b \
  --out outputs/finalization_replay
```

The explicit pin identifies **historical predictions**, not outputs from the current main backend. It must match the cache manifest; patient/input/response hashes and evidence checks still run. `--backend` remains available and rejects changed backend source. The two CLI modes are mutually exclusive and one is required. Hashes check consistency, not cryptographic provider authenticity.

The archived pipeline used complete/lexically ranked history and deterministic fallback explanations. Main now has integrated hybrid retrieval and persisted explanations; the archived results do **not** evaluate those new components. No new model inference or evaluation on main is claimed.

To reconstruct the historical backend for the optional handoff test, export tracked `cancersignal/backend/` from `84409a6` into a separate temporary directory with `git archive`, and apply only the recorded historical import addition: add `validate_evidence` to the `from app.contracts.validation import ...` line in `app/extraction/service.py`. Before use, verify `cancersignal_sim.real_cache.backend_fingerprint(exported_backend)` equals the explicit fingerprint above. Never apply that patch to main as part of this PR.

## Preserved artifacts

- `results/real_model/cache/`: 33 validated initial predictions, three failure records, provider configuration, prompt/schema, manifest and authentic extraction responses.
- `results/real_model/study/` and `test_study/`: historical real/hypothetical results, confusion matrices and full example pathways.
- `results/real_model/followup_cache/` and `followup_trace.json`: authentic two-timepoint demonstration, excluded from accuracy claims.
- `results/priority_review/`: all four capacity/queue comparisons, per-replication metrics, priority real replay and demo visualization.
- `data/real_model/`: clinical-only input cohorts and separately held labels/provenance; these are simulation fixtures, not application demo seeds.
- `PRIORITY_REVIEW_FINDINGS.md`, `REAL_MODEL_REPORT.md`, `WORKFLOW_FINDINGS.md`: preserved experimental interpretations. Earlier “not committed/pushed” statements describe their historical writing time; the PR state is authoritative.

## Methodological limitations

The hypothetical population experiment assumes TPR 0.80 and FPR 0.12. These do not drive real-mode alerts. Real-mode inputs are 33 successful synthetic predictions from 36 attempts; three failures remain unavailable, never silently negative. Selecting successful cases can bias pathway comparisons. Reference labels were authored separately but align with the same rulebook: this is not independent clinical validation or cancer sensitivity. Review-need labels serve as a proxy for investigation relevance.

Operational routing, clinician escalation, service times, capacity and review priority remain assumptions. GP capacity is shared and active visits are never interrupted; priority can delay others. Thirty replications quantify Monte Carlo variability, not parameter uncertainty or a larger clinical sample. The real cohort is lightly loaded, so it does not demonstrate congestion benefits. QCancer was insufficient-data for all 33 records and supplies no routing risk threshold. The main backend handoff defect must be resolved separately before claiming fresh end-to-end compatibility.
