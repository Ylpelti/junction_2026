# Analysis integration verification — 2026-11-14

Agent B integration work on branch `integration/analysis-end-to-end`.
Demo seeding, evaluation/simulation and model internals are maintained separately.

## Execution path

The frontend lists PostgreSQL patients, pages through their observations, and
posts a `clinical_note` to `/api/v1/patients/{id}/analyses`. The service persists
the note, validates the retrieval scope and extraction references, derives lab
findings, runs deterministic SUO rules and the existing QCancer adapter, then
persists findings, evidence, predictions and rule snapshots. The note cutoff
filters both observed and recorded times; the input note is supplied explicitly.

`get_analysis_pipeline` already selected `services/history_retrieval.py` in this
checkout. It calls the existing advanced retrieval engine, with auto, lexical,
hybrid and baseline modes. Complete numerical history is fetched independently
via `PatientRepository.structured`; top-k never chooses the lab model inputs.
See [RAG configuration](rag-analysis-integration.md). Existing tests cover strict
time cutoffs, isolation, negation/resolution, contradictory states, index refresh,
new observations, missing/stale vectors and lexical fallback.

`CANCERSIGNAL_EXTRACTION=llm` already selects the existing `LlmNoteExtractor` and
`ClinicalExtractor`. Configuration, evidence and provider errors produce explicit
failed analyses, never negative clinical conclusions. `off` remains the reliable
structured-only mode: it does **not** understand arbitrary clinical note prose.
See `backend/app/extraction/README.md` for separate provider credentials and cache.

No mathematical, extraction, explanation-engine, benchmark or seed internals were
changed. QCancer remains separate from rule priorities, returns insufficient data
for missing predictors, and preserves units, original evidence and its producer
notice. The owned model adapter still uses the documented synthetic Townsend=0
placeholder; this is not a measured predictor or a Finnish-calibrated estimate.
Additional mathematical modules outside the published pipeline contracts are not
silently imported. Their owner must expose supported outputs/provenance before
integration.

## English explanation integration

`services/clinical_explanation.py` calls the existing
`ExplanationEngine.explain_api(response, input_note=note)` after the validated
analysis graph is flushed and before committing the transaction. No competing
renderer or model is introduced. The validated `ExplanationResult` is saved in
`AnalysisRun.details.clinical_explanation`, exposed in the additive response field
`clinical_explanation`, and its English summary populates the existing
`explanation` string. Existing analyses return null for the new field and retain
the legacy summary; GET does not backfill or make provider calls. Stored explanation-v1 payloads use
the read-only English adapter described in [contracts](contracts.md).

The structured object includes evidence IDs, exact model quantities, English
statements, limitations, generation mode and issues. The frontend exposes this
object in nurse and physician views, alongside a separate QCancer card. It never
uses explanation text to determine urgency. The digest binds the pre-explanation
input snapshot, not a recursively embedded final response.

Settings (restart the API after changing them):

| Setting | Default |
| --- | --- |
| `CANCERSIGNAL_EXPLANATION` | `deterministic` (`llm` optional) |
| `CANCERSIGNAL_EXPLANATION_ENV_FILE` | unset; explicit EXPLANATION_* settings file |
| `CANCERSIGNAL_EXPLANATION_ALLOW_LIVE` | `false` |
| `CANCERSIGNAL_EXPLANATION_CACHE_DIR` | unset |

The existing engine handles provider failures with its validated deterministic
English output and explicit issue codes. Invalid configuration falls back through
the same engine and records `clinical_explanation_provider_unavailable`. If both
paths reject the input, the analysis stays saved with null explanation details and
`clinical_explanation_unavailable`; clinical results are not changed. Failed
analyses are not explained. Reads, queue retrieval and repeated handoff never
regenerate explanations.

## Frontend and persistence

Patient history now loads all observation pages rather than silently stopping at
200. Saving locks the button in both analysis and current-practice modes; patient
selection is blocked during save/send. A lost save response says the outcome is
unconfirmed and asks the user to inspect saved history before retrying. Backend
review submission failure remains an error with retry available; it no longer
becomes a browser-only successful send. Explicit prototype mode stays labelled.

Physician requests are persisted by the existing unique analysis key and
transactional idempotent insertion. A refreshed client can read the identical
analysis, source evidence and explanation. Dismissals and physician decisions
still remain labelled browser-only state. Appointment/demo queue fillers remain
labelled synthetic UI data. Nurse analyses are not automatically restored into
the active visit after refresh, but saved notes and the physician queue persist.
New note POSTs are not idempotent across a lost response and manual resubmission;
retry by saved `note_observation_id` when the note already exists. Repeating an
analysis of the same note creates another analysis run by the existing contract.

## Repeatable verification

From `cancersignal/backend`:

```sh
.venv/bin/python -m pytest -q
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_pipeline.py --hybrid
```

Database checks create and remove only their own uniquely named databases; the
configured role needs CREATEDB. The smoke starts actual Uvicorn servers and sends
network HTTP requests for lexical and real E5 hybrid analysis, GET readback and
idempotent physician handoff. `--hybrid` asserts the effective retrieval mode,
so fallback cannot masquerade as hybrid success. It requires already-cached pinned
E5 weights and installed optional dependencies. Without it, smoke is lexical only.
It seeds only its disposable database with existing fixtures, without modifying
Agent A's seed/reset work. Fixture identifiers use `synthetic_id("patient/0")` and
`synthetic_id("note/0/3")`; no new production patient IDs are assumed.

Opt-in external inference smoke (sends the repository synthetic example and may
incur provider charges):

```sh
RUN_LIVE_EXTRACTION=1 CANCERSIGNAL_EXTRACTION_ENV_FILE=.env.extraction \
  .venv/bin/python -m pytest tests/test_live_extraction_smoke.py -q
```

This uses no replay cache and fails on missing credentials or invalid provider
output. Ordinary tests never opt in. For a full live note workflow, configure
`CANCERSIGNAL_EXTRACTION=llm`, provider settings, the cache directory and
`CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=true`, then run the regular API. Turn live
permission off to replay validated identical cached snapshots. New UUIDs/timestamps
change cache inputs; reuse a saved note ID for reproducibility. Provider model
semantic quality and clinical usefulness require independent evaluation.

From `cancersignal/frontend`:

```sh
npm run typecheck
npm run build -- --webpack
```

## Verification record and limits

- Final full PostgreSQL suite: 490 passed, 1 skipped (external inference requires
  explicit opt-in).
- Final default suite: 380 passed, 111 skipped (110 PostgreSQL tests and one
  explicitly opt-in external inference test).
- Frontend type checking and webpack production build passed. `pip check` found
  no broken requirements; `alembic check` found no upgrade operations.
- Interactive browser clicks were not exercised; frontend verification here is
  type checking/build plus inspection of API mapping and component data flow.
- Real network HTTP smoke: lexical and real cached multilingual E5 hybrid passed;
  English explanation persistence, GET equality and duplicate handoff passed.
- Database tests exercise real PostgreSQL full-text/pgvector mechanics. Ordinary
  hybrid tests use a deterministic fake embedder; the HTTP smoke uses real E5.
- LLM schema, negation, uncertainty, provider errors and grounding are tested with
  synthetic fixture responses/mock transports. No real external LLM call was run.
- Demo seed and mathematical-model ownership are unchanged. Agent A's separate
  checkout is not merged here; validate its new patient IDs after integration.
- This is synthetic integration verification, not clinical validation. Unknown
  predictors stay unknown; the pre-existing Townsend demo placeholder remains a
  documented model-owner limitation.
