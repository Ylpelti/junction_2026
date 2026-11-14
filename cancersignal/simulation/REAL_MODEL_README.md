# Real CancerSignal replay

For the final PR based on main `9718db3`, see [FINALIZATION.md](FINALIZATION.md). The predictions below are historical; current main has a different backend fingerprint and an unresolved optional handoff-test failure.

Implemented and executed in branch `feat/simulation-real-model`, based on backend commit `84409a6`, with the approved missing `validate_evidence` import fixed. Work is in the isolated `/private/tmp/cancersignal-real-integration` worktree. See [results and limitations](REAL_MODEL_REPORT.md).

From this `cancersignal/simulation` directory, install this package (`python -m pip install -e .`) into a simulation environment. Replay requires no provider credentials or database:

```sh
python -m cancersignal_sim.real_study --cohort results/real_model/validated_cohort.json --evaluation-cohort data/real_model/cohort.json --labels data/real_model/labels.json --cache results/real_model/cache --expected-pipeline-sha256 d93db13173a7c74323ceea84ac77fe891064232082cbb5e576404ae490bf6d0b --out outputs/replayed_real
```

The default now uses priority review and GP capacity 3. Add `--config config/real_model_fifo_original.json` to reproduce the historical report exactly. Add `--split test` to replay only the held-out split. The full 36-case cohort intentionally fails strict replay: three authentic extraction failures have no usable prediction. `validated_cohort.selection.json` records the explicit 33-case selection; evaluation still reports all 36 and the missing predictions. No failed extraction is called a negative. `select_validated_cohort.py --help` documents the separate selection operation.

The following live-inference command describes the historical interface; fresh inference on main is not validated and the documented missing-import failure remains unresolved in this simulation-only PR. For new inference after addressing backend compatibility separately, use the backend environment with its installed dependencies and a PostgreSQL account allowed to create disposable databases. From this directory:

```sh
EXTRACTION_RESPONSE_FORMAT=json_object EXTRACTION_REASONING_EFFORT=low EXTRACTION_MAX_OUTPUT_TOKENS=8192 /path/to/backend/python -m cancersignal_sim.real_inference --backend ../backend --cohort data/real_model/cohort.json --cache outputs/new_real_cache --env-file /path/to/.env.extraction --database-env-file /path/to/database.env --workers 3 --allow-live
```

This calls the existing `create_analysis` orchestrator with the real LLM extractor, actual retrieval, lab derivation, evidence validators, QCancer adapter and SUO rules. It creates, migrates, seeds and drops its own randomly named database. Never use cached unit-test provider outputs as authentic predictions. Live inference can incur provider charges; the exported synthetic predictions avoid repeated calls during experiments. Three failures caused the executed inference command to exit nonzero, while preserving successes and failure artifacts.

A cache entry binds patient, decision point, clinical input hash, backend Python source fingerprint, provider/model/configuration and response hash. Replay validates source ownership, exact quotes/offsets, timestamps and mapped recommendations. Source changes fail the backend fingerprint check; rerun inference or use the original pinned backend. Hashes detect accidental stale/tampered data; they are not cryptographic proof of provider origin.

Clinical payloads allow only patient demographics and available observations. Evaluation labels and coded extraction answers stay separate. Both observed and recorded timestamps constrain history. Later decision snapshots must use their true time offset; premature replay raises an error. `followup_cache` and `followup_trace.json` demonstrate actual inference at two times using existing records; forced review/escalation policy makes this a mechanics demonstration only.

The ordinary simulator remains the hypothetical benchmark. Real mode never uses TPR/FPR to generate alerts or hypothetical duplicate cancellation. Clinician acceptance/escalation, capacity, service times and review selection are explicitly operational assumptions. An AI alert consumes GP review capacity and does not itself establish a diagnosis.

Verification:

```sh
python -m unittest discover -s tests -q
/path/to/backend/python -m pytest integration_tests/test_actual_backend_handoff.py -q
```

The handoff test uses an explicitly labeled fixture provider only to test the backend contract; experimental exports come from the actual Verda model. Backend extraction tests run from the backend directory with `python -m pytest tests/extraction tests/test_llm_extraction.py -q`.
