# English clinical pipeline migration

The migration is integrated with main's persisted nurse/physician workflows and
canonical-only demo selection. Unrelated uncommitted semantic-validator and compact
extraction experiments in the development checkout are not included in this change.
Clinical rule expressions, thresholds, SUO identifiers, machine statuses, QCancer
identities and risk-model mathematics are unchanged.

## Modified components

- Frontend clinical summaries, physician rule headings, limitations and source
  labels are English. Exact numeric display uses decimal points. The canonical
  patient registry now selects only the four English fixture identities.
- Every deterministic explanation template is English, including polarity,
  temporal status, uncertainty, unavailable outputs and QCancer limitations.
- Explanation contract **2.0** uses `language: en`, `summary_en` and `text_en`.
  The REST route prefix and clinical finding contracts remain unchanged.
- Stored explanation v1 is supported through a labelled, read-only deterministic
  adapter. It renders stored structured outputs without changing evidence or
  saved JSON, rerunning clinical rules, translating source notes or calling an LLM.
- English extraction prompt `clinical-extraction-en-3` and explanation prompt
  `en-explanation-plan-2` isolate old inference caches. Quotes remain verbatim.
- PostgreSQL lexical retrieval now uses English/simple dictionaries. RAG benchmark
  sources have new versioned English keys, preserving old stored observations.
- Tests, fixture references and active documentation use the English contracts.
  Original Finnish sources and historical evaluation reports remain archival.

## Dataset and evidence

[`manifest.en-v2.json`](../backend/app/db/demo_data/manifest.en-v2.json) describes
four synthetic patient histories (21 encounters, 41 observations) plus the paired
extraction scenario. Together they cover active symptoms, historical resolution,
completed and planned investigations, unknown completion, explicit negation,
conflicting investigation documentation and missing predictors.

All changed texts have new patient/encounter/observation UUIDs. The complete map
is [`en-v2-id-map.json`](../backend/app/db/demo_data/en-v2-id-map.json). Regression
tests compare unchanged values, units, clinical statuses and both timestamp axes.
“Does not currently smoke” remains distinct from “never smoked”. All sources are
explicitly synthetic; no translation inference step was added.

Seed is insert-only and rejects changed persisted fixture content transactionally.
Future content changes need a new version and identities. No old evidence or
analyses are overwritten. The configured local demo database was loaded with
**66 inserted, 0 updated** records during implementation. Canonical UI filtering
excludes old identities while their original API records remain available.

Schema review retained separate polarity, temporal state, uncertainty, missing
information and multiple evidence references because they carry distinct clinical
meaning. Patient identity and provenance are already assigned by Python.

## Verification

The isolated integration on current main passes **550 backend/PostgreSQL tests**;
the single skipped test requires explicitly authorized paid live inference.
The suite includes explanation, evidence, patient/time isolation, deterministic
rules, QCancer, persisted workflows, source preservation and legacy adapter tests.
Frontend typecheck and production webpack build pass. **24 frontend regression tests** and the **real PostgreSQL browser workflow**
pass, including persisted physician decisions, dismissals, queue reload and
canonical dataset isolation.
No paid model calls are made for this migration.

[`english-migration-evaluation.json`](english-migration-evaluation.json) replays
manually authored clinically equivalent Finnish-v1 and English-v2 responses through
the integrated pipeline. Both versions are schema-valid, validate all six evidence
references and retain all six expected clinical states: factual-state precision and
recall, negation recall and temporal recall are **100%** for this small replay.
Unknown smoking status stays unknown. This measures pipeline/fixture fidelity,
not live-model accuracy or clinical validity. The separate uncommitted semantic
validation experiment is deliberately outside this published comparison.

## Deployment and reproduction

Deploy backend and frontend together and restart/refresh both. No new SQL migration
is required for the explanation contract; apply main's existing migrations normally.
For an environment without the new English fixture, from `backend/`:

```sh
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.db.demo validate
.venv/bin/python -m app.db.demo seed
.venv/bin/python -m app.db.demo list
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate_english_migration.py
```

Seed existing rules if absent. Reindex the new identities when using dense/hybrid
retrieval; complete and lexical retrieval need no model download. Old evidence and
caches need not be deleted: identities and prompt versions isolate them.

From `frontend/`, after installing dependencies and Playwright Chromium (or setting
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed browser):

```sh
npm run typecheck
npm run build -- --webpack
npm test
../backend/.venv/bin/python tests/run_real_e2e.py
```

The database runner creates/migrates/seeds/drops only a uniquely named test database.
It verifies persisted physician decisions and dismissals as well as handoff and
reload. The shared development checkout and running application are not replaced.
